"""Command line: check, repair, convert and play duets."""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

from duet.calibration import SWEEP_INTERVAL_S
from duet.conductor import RealClock, VirtualClock, one_rig, perform
from duet.instruments import Instrument
from duet.midi_io import midi_to_score, save_midi
from duet.performers import (
    Bot,
    human_difficulty,
    in_use,
    performers,
    repair_bots,
    score_problems,
)
from duet.profile import (
    RobotProfile,
    keyboard_profile,
    load_profile_file,
    robot_profile,
    save_profile_file,
)
from duet.score import DuetScore, Duo, LineUpError, load_score
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


def _in_use(args) -> dict[str, Instrument]:
    """The instruments this command plays, by id: ``--robot`` may be a calibrated file."""
    return in_use(_robot(args), keyboard_profile(args.piano))


def cmd_check(args) -> int:
    """Every part, by its performer; fails if a bot cannot play its part."""
    score = read_score(args.score)
    problems = score_problems(score, _in_use(args))
    print(f"{score.meta.title}: {score.bar_count} bars, level {human_difficulty(score)}")
    for part, found in problems.items():
        who = score.parts[part].performer
        print(f"{part} ({who}): " + (f"{len(found)} problem(s)" if found else "playable"))
        for line in found:
            print(f"  {line}")
    return 1 if any(problems[part] for part in score.parts_played_by("bot")) else 0


def _playable(score, args):
    """The score with every bot part repaired, saying so when something changed."""
    result = repair_bots(score, _in_use(args))
    if result.changes:
        print(f"repaired {len(result.changes)} problem(s) so the bots can play it")
    return result.score


def cmd_repair(args) -> int:
    result = repair_bots(read_score(args.score), _in_use(args))
    write_score(result.score, args.out)
    print(result.summary() or "nothing to repair")
    return 0


def cmd_convert(args) -> int:
    write_score(read_score(args.score), args.out)
    return 0


def cmd_play(args) -> int:
    robot = _robot(args)
    score = read_score(args.score)
    if args.only:
        score = score.only(args.only)
        print(f"playing the {args.only} part only ({len(score.events)} notes)")
    score = _playable(score, args)
    mode = "follow" if args.follow else "wait" if args.wait or args.midi_in or args.mic else "play"
    if args.device:
        return _play_on_device(score, robot, _in_use(args), args.device, mode, _keys(args))
    if not args.sim:
        print("choose --sim or --device ws://host:port", file=sys.stderr)
        return 2
    rig = SimulatedRig(robot)
    keys = _keys(args)
    live = args.midi_in or args.mic is not None
    clock = RealClock() if args.realtime or live else VirtualClock()
    perf = perform(
        score,
        one_rig(score, [rig]),
        clock,
        instruments=_in_use(args),
        keys=keys,
        mode="follow" if mode == "follow" else "wait",
    )
    rig.run()
    if keys is not None:
        from duet.listening import grade

        if args.follow:
            print(f"followed the pianist: tempo now {100 / perf.final_rate:.0f}% of written")
        else:
            print(f"waited {perf.waited_us / 1e6:.1f} s for the pianist")
        print(grade(perf.expected_pianist(), perf.played).feedback())
    all_played = True
    for bot in (p for p in performers(score, _in_use(args)) if isinstance(p, Bot)):
        planned = sorted(n.t_us for n in perf.planned if n.part == bot.part)
        heard = sorted(_heard(rig, bot))
        errors = [abs(h - t) for h, t in zip(heard, planned, strict=False)]
        print(
            f"{bot.part} (bot): {len(heard)}/{len(planned)} notes, "
            f"max timing error {max(errors, default=0)} us"
        )
        all_played &= len(heard) == len(planned)
    print(f"LED frames: {len(rig.led_frames)}, faults: {len(rig.faults)}")
    for fault in rig.faults:
        print(f"  {fault}")
    return 0 if not rig.faults and all_played else 1


def _heard(rig: SimulatedRig, bot: Bot) -> list[int]:
    """When the rig sounded the bot's notes: the carriage's strikes, or its MIDI note ons."""
    if bot.moves:  # one carriage on the rig, so every strike is this bot's
        return [s.t_us for s in rig.sounds]
    return [n.t_us for n in rig.notes if n.vel > 0 and n.midi == bot.mechanism.midi_channel]


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
    from duet.ensemble import Member, assign, build_score
    from duet.midi_io import midi_tracks
    from duet.pitch import name_to_midi

    tempo, signature, tracks = midi_tracks(args.midi)
    members = [Member(r, robot_profile(r)) for r in args.robots.split(",") if r]
    if args.pianist != "none":
        low, high = (name_to_midi(n) for n in args.pianist.split("-"))
        members.append(Member("pianist", low=low, high=high))
    plan = assign(tracks, members)
    print(f"transposed {plan.transpose:+d}")
    for name, (track, octave) in plan.parts.items():
        moved = f", {octave:+d} semitones" if octave else ""
        print(f"  {name}: {track} ({plan.fit[name]:.0%} playable{moved})")
    for track in plan.unused:
        print(f"  nobody plays: {track}")
    if not args.sim:
        print("only simulated rigs so far; add --sim", file=sys.stderr)
        return 2
    keyboard = keyboard_profile(args.piano)
    score, playing = build_score(tracks, members, plan, tempo, signature, keyboard.id)
    # One simulated rig per member: a robot's carriage, or the person's light strip.
    rigs = {m.name: SimulatedRig(m.robot or members[0].robot) for m in members}
    routes = {part: [rigs[part]] for part in score.parts}
    perform(score, routes, VirtualClock(), instruments={**playing, **in_use(keyboard)})
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
    report = grade_take(score, played, score.part_played_by("human"))
    for g in report.grades:
        if g.result != "hit":
            print(f"bar {g.expected.bar}: {g.result}")
    print(report.feedback())
    return 0


def describe(hello) -> str:
    """One line about a device: who it is, its board and what the board can do."""
    features = ", ".join(hello.features) or "no extras"
    return f"{hello.device_id} ({hello.board}: {features})"


def cmd_song(args) -> int:
    """Write a song file: the score made playable and compiled for the rig, for its web
    page to load with no server (docs/device-api.md, "Song files")."""
    from duet.sim import RIG_CHANNELS
    from duet.songs import SongError, compile_song

    robot = _robot(args)
    score = read_score(args.score)
    if args.only:
        score = score.only(args.only)
    score = _playable(score, args)
    try:
        song = compile_song(score, robot, keyboard_profile(args.piano), RIG_CHANNELS)
    except SongError as exc:
        print(f"cannot make a song of it: {exc}", file=sys.stderr)
        return 2
    Path(args.out).write_text(song.song_file(), encoding="utf-8")
    print(
        f"wrote {song.title!r} to {args.out}: {len(song.commands)} commands, "
        f"{song.duration_s:.1f} s; load it on the rig's page"
    )
    return 0


def cmd_upload(args) -> int:
    """Store a song on the device, to play without the Hub (press its play button)."""
    from duet.device.gateway import DeviceFault, DeviceGateway
    from duet.songs import SongError, check_slot, compile_song

    robot = _robot(args)
    score = read_score(args.score)
    if args.only:
        score = score.only(args.only)
    score = _playable(score, args)
    try:
        slot = check_slot(args.slot)
        with DeviceGateway(args.device, profile=robot) as gateway:
            print(f"connected to {describe(gateway.hello)}")
            song = compile_song(score, robot, keyboard_profile(args.piano), gateway.channels)
            gateway.upload(slot, song)
            print(
                f"stored {song.title!r} in slot {slot}: {len(song.commands)} commands, "
                f"{song.duration_s:.1f} s"
            )
            if args.play:
                gateway.play(slot)
                print("playing from memory")
    except SongError as exc:
        print(f"cannot store it: {exc}", file=sys.stderr)
        return 2
    except DeviceFault as exc:
        print(f"the device refused it: {exc}", file=sys.stderr)
        return 1
    return 0


def _play_on_device(score, robot, instruments, url: str, mode: str, keys) -> int:
    """A live performance on a rig (duet.live), in play, wait or follow mode."""
    from duet.device.gateway import DeviceFault
    from duet.live import StoppableClock, Stopped, play_live, summary

    def connected(gateway) -> None:
        sync = gateway.sync
        print(f"connected to {describe(gateway.hello)}")
        print(f"clock offset {sync.offset_us} us (+/- {sync.error_bound_us:.0f} us)")

    try:
        perf = play_live(
            score, url, robot, instruments, mode=mode, keys=keys, clock=StoppableClock(),
            on_connect=connected,
        )  # fmt: skip
    except (Stopped, KeyboardInterrupt):
        print("stopped; the rig is quiet")
        return 1
    except DeviceFault as exc:
        print(f"the rig refused it: {exc}", file=sys.stderr)
        return 1
    print(summary(perf, mode))
    return 0


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
    duo = Duo(bot_instrument=robot.id)
    events = [
        {
            "part": duo.bot,
            "bar": int(t // 4) + 1,
            "beat": t % 4 + 1,
            "dur": beat,
            "pitch": robot.notes[i].midi,
            "vel": 100,
        }
        for t, i in plan_sweep(robot, interval_s=beat)
    ]
    score = DuetScore.model_validate(
        {
            "meta": {"title": "Calibration sweep", "tempo_bpm": 60},
            "parts": duo.parts(),
            "events": events,
        }
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
    p.add_argument("--lead", choices=["bot", "human"], default="bot", help="who has the melody")
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
    p.add_argument(
        "--device", help="play on a device: ws://host:port (the rig) or tcp://host:port (serial)"
    )
    p.add_argument(
        "--only",
        metavar="PART",
        help="play one part alone, e.g. robot (the bottles solo) or pianist (practise alone)",
    )
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
    p.add_argument("--interval", type=float, default=SWEEP_INTERVAL_S)
    p.set_defaults(func=cmd_calibrate)

    p = sub.add_parser("upload", help="store a song on the device, to play without the Hub")
    p.add_argument("score")
    p.add_argument("--device", required=True, help="ws://host:port or tcp://host:port")
    p.add_argument("--slot", type=int, default=0, help="song slot 0-7 (default 0)")
    p.add_argument("--only", metavar="PART", help="store one part alone")
    p.add_argument("--play", action="store_true", help="play it right away")
    p.set_defaults(func=cmd_upload)

    p = sub.add_parser("song", help="write a song file for the rig's page to load")
    p.add_argument("score")
    p.add_argument("-o", "--out", required=True, help="the song file to write (say rain.song)")
    p.add_argument("--only", metavar="PART", help="one part alone")
    p.set_defaults(func=cmd_song)

    p = sub.add_parser("device-sim", help="run a simulated rig device on a WebSocket")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_device_sim)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except LineUpError as exc:  # asked for a part the score does not have, or the like
        print(f"duet {args.command}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
