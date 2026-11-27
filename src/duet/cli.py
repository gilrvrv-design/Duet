"""Command line: check, repair, convert and play duets."""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

from duet.conductor import RealClock, VirtualClock, perform
from duet.difficulty import pianist_difficulty
from duet.feasibility import check_robot
from duet.midi_io import midi_to_score, save_midi
from duet.profile import (
    RobotProfile,
    keyboard_profile,
    load_profile_file,
    robot_profile,
    save_profile_file,
)
from duet.repair import repair_robot
from duet.score import DuetScore, load_score
from duet.sim import SimulatedRig


def _robot(args) -> RobotProfile:
    """``--robot`` is a built-in profile id or a calibrated profile file (.yaml)."""
    if str(args.robot).endswith((".yaml", ".yml")):
        profile = load_profile_file(args.robot)
        if not isinstance(profile, RobotProfile):
            raise SystemExit(f"{args.robot} is not a robot profile")
        return profile
    return robot_profile(args.robot)


def read_score(path: str) -> DuetScore:
    if Path(path).suffix.lower() in (".mid", ".midi"):
        return midi_to_score(path, title=Path(path).stem)
    return load_score(Path(path))


def write_score(score: DuetScore, path: str) -> None:
    if Path(path).suffix.lower() in (".mid", ".midi"):
        save_midi(score, path)
    else:
        Path(path).write_text(score.to_json(), encoding="utf-8")


def cmd_check(args) -> int:
    score = read_score(args.score)
    report = check_robot(score, _robot(args))
    print(f"{score.meta.title}: {score.bar_count} bars, pianist level {pianist_difficulty(score)}")
    if report.ok:
        print("robot part: playable")
        return 0
    print(f"robot part: {len(report.violations)} problem(s)")
    print(report.feedback())
    return 1


def cmd_repair(args) -> int:
    result = repair_robot(read_score(args.score), _robot(args))
    write_score(result.score, args.out)
    print(result.summary() or "nothing to repair")
    return 0


def cmd_convert(args) -> int:
    write_score(read_score(args.score), args.out)
    return 0


def cmd_play(args) -> int:
    robot = _robot(args)
    score = read_score(args.score)
    if not check_robot(score, robot).ok:
        result = repair_robot(score, robot)
        print(f"repaired {len(result.changes)} problem(s) so the robot can play it")
        score = result.score
    if args.device:
        return _play_on_device(score, robot, keyboard_profile(args.piano), args.device)
    if not args.sim:
        print("choose --sim or --device ws://host:port", file=sys.stderr)
        return 2
    rig = SimulatedRig(robot)
    keys = _keys(args)
    live = args.midi_in or args.mic is not None
    clock = RealClock() if args.realtime or live else VirtualClock()
    mode = "follow" if args.follow else "wait"
    perf = perform(score, robot, keyboard_profile(args.piano), [rig], clock, keys=keys, mode=mode)
    rig.run()
    if keys is not None:
        from duet.listening import grade

        if args.follow:
            print(f"followed the pianist: tempo now {100 / perf.final_rate:.0f}% of written")
        else:
            print(f"waited {perf.waited_us / 1e6:.1f} s for the pianist")
        print(grade(perf.expected_pianist(), perf.played).feedback())
    planned = [p for p in perf.planned if p.part == "robot"]
    errors = [abs(s.t_us - p.t_us) for s, p in zip(rig.sounds, planned, strict=False)]
    print(f"robot notes: {len(rig.sounds)}/{len(planned)}, LED frames: {len(rig.led_frames)}")
    print(f"max timing error: {max(errors, default=0)} us, faults: {len(rig.faults)}")
    for fault in rig.faults:
        print("  " + fault)
    return 0 if not rig.faults and len(rig.sounds) == len(planned) else 1


def _keys(args):
    """Wait and follow modes need someone at the keys: a MIDI keyboard or a simulated pianist."""
    if args.mic is not None:
        from duet.mic import MicKeys, MicListener, SoundDeviceSource

        device = None if args.mic == "default" else args.mic
        return MicKeys(MicListener(22050, robot=_robot(args)), SoundDeviceSource(device=device))
    if args.midi_in:
        import mido

        from duet.listening import MidiKeys

        return MidiKeys(mido.open_input(args.midi_in))
    if args.follow:
        from duet.follow import TempoPianist

        return TempoPianist(stretch=args.stretch)
    if args.wait:
        from duet.listening import SimulatedPianist

        return SimulatedPianist(reaction_s=args.reaction)
    return None


DEMO_PHRASES = [
    [(0, 60), (1, 64), (2, 67), (4, 72)],
    [(0, 67), (1, 65), (2, 64), (3, 62), (6, 60)],
    [(0, 64), (0.5, 65), (1, 67), (3, 64)],
    [(0, 72), (2, 67), (4, 64), (6, 60)],
]


def cmd_vary(args) -> int:
    from functools import partial

    from duet.variations import is_built_in, vary

    edit = None
    if not is_built_in(args.instruction):
        from duet.compose.claude import ClaudeComposer
        from duet.compose.service import revise
        from duet.copyright import CopyrightGuard

        edit = partial(revise, composer=ClaudeComposer(), guard=CopyrightGuard.load())
    score, note = vary(read_score(args.score), args.instruction, edit, _robot(args))
    write_score(score, args.out)
    print(note)
    return 0


def cmd_ensemble(args) -> int:
    """Play a multi-track MIDI file with several robots and the pianist."""
    from duet.ensemble import Instrument, assign, build_players, perform_ensemble
    from duet.midi_io import midi_tracks
    from duet.pitch import name_to_midi

    tempo, signature, tracks = midi_tracks(args.midi)
    instruments = [Instrument(r, robot_profile(r)) for r in args.robots.split(",") if r]
    if args.pianist != "none":
        low, high = (name_to_midi(n) for n in args.pianist.split("-"))
        instruments.append(Instrument("pianist", low=low, high=high))
    plan = assign(tracks, instruments)
    print(f"transposed {plan.transpose:+d}")
    for name, (track, octave) in plan.parts.items():
        moved = f", {octave:+d} semitones" if octave else ""
        print(f"  {name}: {track} ({plan.fit[name]:.0%} playable{moved})")
    for track in plan.unused:
        print(f"  nobody plays: {track}")
    if not args.sim:
        print("only simulated rigs so far; add --sim", file=sys.stderr)
        return 2
    rigs = {i.name: SimulatedRig(i.robot or instruments[0].robot) for i in instruments}
    players = build_players(
        tracks, instruments, plan, tempo, signature, {k: [v] for k, v in rigs.items()}
    )
    perform_ensemble(players, keyboard_profile(args.piano), VirtualClock())
    faults = 0
    for name, rig in rigs.items():
        rig.run()
        faults += len(rig.faults)
        if rig.sounds:
            print(f"  {name} played {len(rig.sounds)} notes")
    print(f"faults: {faults}")
    return 0 if not faults else 1


def cmd_teach(args) -> int:
    """ "Teach me this song": a lesson path of duets from an audio recording."""
    from duet.audio.pipeline import transcribe_file
    from duet.pedagogy import teach_song

    title = Path(args.audio).stem
    path = teach_song(transcribe_file(args.audio), args.target, title)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for i, step in enumerate(path.steps, start=1):
        file = out / f"{i:02d}-level{step.difficulty}-{round(step.tempo_factor * 100)}pct.json"
        write_score(step.score, str(file))
        print(f"step {i}: {step.title} ({step.score.meta.tempo_bpm:g} bpm) -> {file}")
    print("play each step with --wait until you get 90% right, then move on")
    return 0


def cmd_jam(args) -> int:
    """Call and response: you play a phrase, the robot answers."""
    from duet.device.clock import hub_now_us
    from duet.pitch import midi_to_name as pitch_name
    from duet.session import PhrasePianist, call_and_response

    robot = _robot(args)
    live = args.midi_in or args.mic is not None
    keys = _keys(args) if live else PhrasePianist(DEMO_PHRASES, args.tempo)
    rig = SimulatedRig(robot)
    clock = RealClock() if live else VirtualClock(hub_now_us())
    session = call_and_response(
        robot,
        keyboard_profile(args.piano),
        [rig],
        clock,
        keys,
        tempo_bpm=args.tempo,
        bars_per_turn=args.bars,
        turns=args.turns,
    )
    rig.run()
    for i, turn in enumerate(session.turns, start=1):
        heard = " ".join(pitch_name(n.pitch) for n in turn.phrase) or "(nothing)"
        reply = " ".join(pitch_name(n.pitch) for n in turn.reply) or "(rest)"
        wait_ms = (turn.reply_start_us - turn.pianist_end_us) / 1000
        print(f"turn {i}: you {heard} -> robot {turn.kind}: {reply} ({wait_ms:.0f} ms later)")
    print(f"faults: {len(rig.faults)}")
    return 0 if not rig.faults else 1


def cmd_grade(args) -> int:
    """Grade a recorded MIDI performance of the pianist part against the score."""
    import mido

    from duet.listening import PlayedNote, grade_take

    score = read_score(args.score)
    now, played = 0.0, []
    for msg in mido.MidiFile(args.played):  # iterating gives times in seconds
        now += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            played.append(PlayedNote(round(now * 1e6), msg.note, msg.velocity))
    report = grade_take(score, played)
    for g in report.grades:
        if g.result != "hit":
            print(f"bar {g.expected.bar}: {g.result}")
    print(report.feedback())
    return 0


def _play_on_device(score, robot, keyboard, url: str) -> int:
    from duet.device.gateway import DeviceGateway

    with DeviceGateway(url, profile=robot) as gateway:
        sync = gateway.sync
        print(
            f"connected to {gateway.hello.device_id}: clock offset {sync.offset_us} us "
            f"(+/- {sync.error_bound_us:.0f} us)"
        )
        perf = perform(score, robot, keyboard, [gateway], RealClock())
        gateway.wait_acked()
        print(f"sent {perf.messages_sent} commands, errors: {len(gateway.errors)}")
        return 0 if not gateway.errors else 1


def cmd_device_sim(args) -> int:
    import asyncio

    from duet.device.sim_server import SimulatedDevice

    device = SimulatedDevice(_robot(args))
    print(f"simulated device listening on ws://{args.host}:{args.port}")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(device.serve(args.host, args.port))
    return 0


def cmd_eval(args) -> int:
    import json

    from duet.compose.claude import ClaudeComposer
    from duet.evaluation import gate, load_cases, run_eval

    cases = load_cases(args.cases)[: args.limit or None]
    model = ClaudeComposer(model=args.model).model
    run = run_eval(cases, lambda: ClaudeComposer(model=args.model), args.workers, model)
    s = run["summary"]
    print(
        f"{s['cases']} cases, prompt pack {run['prompt_pack']}, model {model}: "
        f"pass {s['pass_rate']:.0%}, first draft {s['first_draft_rate']:.0%}, "
        f"difficulty {s['difficulty_rate']:.0%}, {s['mean_rounds']} rounds, {s['mean_seconds']} s"
    )
    if args.out:
        Path(args.out).write_text(json.dumps(run, indent=2), encoding="utf-8")
    if args.baseline:
        problems = gate(run, json.loads(Path(args.baseline).read_text(encoding="utf-8")))
        for problem in problems:
            print("gate: " + problem)
        if problems:
            return 1
        print("gate: ok")
    return 0


def cmd_sweep(args) -> int:
    from duet.calibration import plan_sweep

    robot = _robot(args)
    beat = 1.0  # one strike per second at 60 bpm
    events = [
        {
            "part": "robot",
            "bar": int(t // 4) + 1,
            "beat": t % 4 + 1,
            "dur": beat,
            "pitch": robot.notes[i].midi,
            "vel": 100,
        }
        for t, i in plan_sweep(robot, interval_s=beat)
    ]
    score = DuetScore.model_validate(
        {"meta": {"title": "Calibration sweep", "tempo_bpm": 60}, "events": events}
    )
    write_score(score, args.out)
    print(f"play {args.out} on the rig and record it, then run: duet calibrate <recording>")
    return 0


def cmd_calibrate(args) -> int:
    from duet.audio.io import load_audio
    from duet.calibration import calibrate_from_sweep, first_onset

    robot = _robot(args)
    audio, sr = load_audio(args.recording)
    first = args.first
    if first is None:  # start the first window a little before the first strike is heard
        heard = first_onset(audio, sr)
        if heard is None:
            print("the recording is silent", file=sys.stderr)
            return 1
        first = max(0.0, heard - 0.05)
    result = calibrate_from_sweep(audio, sr, robot, first_s=first, interval_s=args.interval)
    save_profile_file(result.profile, args.out)
    for m in result.bottles:
        if m.heard:
            print(f"bottle {m.index + 1} {m.name}: {m.hz:.1f} Hz, latency {m.latency_ms:g} ms")
    for warning in result.warnings:
        print("warning: " + warning)
    print(f"saved calibration v{result.profile.calibration.version} to {args.out}")
    return 0


def cmd_compose(args) -> int:
    from duet.compose import CompositionRequest, compose
    from duet.compose.claude import ClaudeComposer

    request = CompositionRequest(
        prompt=args.prompt, difficulty=args.difficulty, bars=args.bars, lead=args.lead
    )
    result = compose(request, ClaudeComposer(model=args.model))
    write_score(result.score, args.out)
    print(f"{result.score.meta.title}: {result.score.bar_count} bars in {result.rounds} round(s)")
    print(result.explanation)
    for warning in result.warnings:
        print("warning: " + warning)
    return 0


def cmd_transcribe(args) -> int:
    from duet.audio.pipeline import transcribe_file, transcription_to_midi

    result = transcribe_file(args.audio, route=args.route)
    transcription_to_midi(result, strength=args.quantize).save(args.out)
    print(
        f"{len(result.notes)} notes, {result.tempo_bpm:g} bpm, {result.key}, "
        f"{result.duration_s:g} s ({result.model})"
    )
    for warning in result.warnings:
        print("warning: " + warning)
    if args.duet:
        from duet.audio.arranger import arrange

        arrangement = arrange(result, difficulty=args.difficulty, title=Path(args.audio).stem)
        write_score(arrangement.score, args.duet)
        print(
            f"duet: transposed {arrangement.transpose:+d}, melody on bottles "
            f"{arrangement.coverage_before:.0%} -> {arrangement.coverage_after:.0%}, "
            f"chords {' '.join(arrangement.chords)}, {len(arrangement.repairs)} repair(s)"
        )
        for tip in arrangement.retuning:
            print("tip: " + tip.advice())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="duet", description=__doc__)
    parser.add_argument(
        "--robot", default="bottles-v1", help="robot profile id or calibrated .yaml file"
    )
    parser.add_argument("--piano", default="piano-88", help="keyboard profile")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="can the robot play this score?")
    p.add_argument("score")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("repair", help="make the robot part playable")
    p.add_argument("score")
    p.add_argument("out")
    p.set_defaults(func=cmd_repair)

    p = sub.add_parser("convert", help="convert between DuetScore JSON and MIDI")
    p.add_argument("score")
    p.add_argument("out")
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("compose", help="write a duet from a text request (needs Claude)")
    p.add_argument("prompt")
    p.add_argument("out", help="output .json or .mid")
    p.add_argument("--difficulty", type=int, default=2)
    p.add_argument("--bars", type=int, default=8)
    p.add_argument("--lead", choices=["robot", "pianist"], default="robot")
    p.add_argument("--model", default=None, help="Claude model id (default: DUET_MODEL or Opus)")
    p.set_defaults(func=cmd_compose)

    p = sub.add_parser("transcribe", help="audio file (wav, mp3, m4a, video...) to MIDI")
    p.add_argument("audio")
    p.add_argument("out", help="output .mid")
    p.add_argument("--quantize", type=float, default=1.0, help="0 = as played, 1 = on the grid")
    p.add_argument("--route", choices=["auto", "melody", "full"], default="auto")
    p.add_argument("--duet", help="also arrange a playable duet into this .json or .mid file")
    p.add_argument("--difficulty", type=int, default=1, help="pianist level for --duet")
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("play", help="perform a score")
    p.add_argument("score")
    p.add_argument("--sim", action="store_true", help="use the simulated rig")
    p.add_argument("--realtime", action="store_true", help="run the clock in real time")
    p.add_argument("--device", help="play on a device at this WebSocket URL")
    p.add_argument("--wait", action="store_true", help="wait mode: pause for each pianist note")
    p.add_argument("--follow", action="store_true", help="follow mode: robot keeps your tempo")
    p.add_argument("--stretch", type=float, default=1.1, help="simulated pianist tempo factor")
    p.add_argument("--midi-in", help="MIDI keyboard port (default: a simulated pianist)")
    p.add_argument(
        "--mic", nargs="?", const="default", help="listen to an acoustic piano (input device)"
    )
    p.add_argument("--reaction", type=float, default=0.3, help="simulated pianist delay (s)")
    p.set_defaults(func=cmd_play)
    p = sub.add_parser("eval", help="run the composition evaluation set (calls Claude)")
    p.add_argument("cases", nargs="?", default="evals/prompts.yaml")
    p.add_argument("--out", help="save results (JSON), e.g. as the next baseline")
    p.add_argument("--baseline", help="fail if results regress against this run")
    p.add_argument("--limit", type=int, default=0, help="only the first N cases")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--model", default=None)
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("vary", help="a variation: slower, faster, easier, swap, or any request")
    p.add_argument("score")
    p.add_argument("instruction", help="built in: slower faster easier swap; else asks Claude")
    p.add_argument("out")
    p.set_defaults(func=cmd_vary)

    p = sub.add_parser("ensemble", help="play a multi-track MIDI file with several robots")
    p.add_argument("midi")
    p.add_argument(
        "--robots", default="bottles-v1,glock-v1", help="robot profile ids, comma separated"
    )
    p.add_argument("--pianist", default="C2-C5", help="the pianist's range, or none")
    p.add_argument("--sim", action="store_true")
    p.set_defaults(func=cmd_ensemble)

    p = sub.add_parser("teach", help="teach me this song: lesson steps from a recording")
    p.add_argument("audio")
    p.add_argument("--target", type=int, default=3, help="the level to reach")
    p.add_argument("--out", default="lesson")
    p.set_defaults(func=cmd_teach)

    p = sub.add_parser("jam", help="call and response: you play, the robot answers")
    p.add_argument("--turns", type=int, default=4)
    p.add_argument("--bars", type=int, default=2, help="bars per turn")
    p.add_argument("--tempo", type=float, default=90)
    p.add_argument("--midi-in", help="MIDI keyboard port (default: a simulated pianist)")
    p.add_argument("--mic", nargs="?", const="default", help="listen to an acoustic piano")
    p.set_defaults(func=cmd_jam, wait=False, follow=False)

    p = sub.add_parser("grade", help="grade a recorded pianist performance (MIDI)")
    p.add_argument("score")
    p.add_argument("played", help="MIDI file of what the pianist played")
    p.set_defaults(func=cmd_grade)

    p = sub.add_parser("sweep", help="write the calibration sweep score")
    p.add_argument("out")
    p.set_defaults(func=cmd_sweep)

    p = sub.add_parser("calibrate", help="new robot profile from a sweep recording")
    p.add_argument("recording")
    p.add_argument("--out", default="calibrated.yaml")
    p.add_argument("--first", type=float, help="seconds into the recording of the first strike")
    p.add_argument("--interval", type=float, default=1.0)
    p.set_defaults(func=cmd_calibrate)

    p = sub.add_parser("device-sim", help="run a simulated rig device on a WebSocket")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_device_sim)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
