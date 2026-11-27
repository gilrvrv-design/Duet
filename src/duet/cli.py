"""Command line: check, repair, convert and play duets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from duet.conductor import RealClock, VirtualClock, perform
from duet.difficulty import pianist_difficulty
from duet.feasibility import check_robot
from duet.midi_io import midi_to_score, save_midi
from duet.profile import keyboard_profile, robot_profile
from duet.repair import repair_robot
from duet.score import DuetScore, load_score
from duet.sim import SimulatedRig


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
    report = check_robot(score, robot_profile(args.robot))
    print(f"{score.meta.title}: {score.bar_count} bars, pianist level {pianist_difficulty(score)}")
    if report.ok:
        print("robot part: playable")
        return 0
    print(f"robot part: {len(report.violations)} problem(s)")
    print(report.feedback())
    return 1


def cmd_repair(args) -> int:
    result = repair_robot(read_score(args.score), robot_profile(args.robot))
    write_score(result.score, args.out)
    print(result.summary() or "nothing to repair")
    return 0


def cmd_convert(args) -> int:
    write_score(read_score(args.score), args.out)
    return 0


def cmd_play(args) -> int:
    robot = robot_profile(args.robot)
    score = read_score(args.score)
    if not check_robot(score, robot).ok:
        result = repair_robot(score, robot)
        print(f"repaired {len(result.changes)} problem(s) so the robot can play it")
        score = result.score
    if not args.sim:
        print("only the simulated rig is available so far; use --sim", file=sys.stderr)
        return 2
    rig = SimulatedRig(robot)
    clock = RealClock() if args.realtime else VirtualClock()
    perf = perform(score, robot, keyboard_profile(args.piano), [rig], clock)
    rig.run()
    planned = [p for p in perf.planned if p.part == "robot"]
    errors = [abs(s.t_us - p.t_us) for s, p in zip(rig.sounds, planned, strict=False)]
    print(f"robot notes: {len(rig.sounds)}/{len(planned)}, LED frames: {len(rig.led_frames)}")
    print(f"max timing error: {max(errors, default=0)} us, faults: {len(rig.faults)}")
    for fault in rig.faults:
        print("  " + fault)
    return 0 if not rig.faults and len(rig.sounds) == len(planned) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="duet", description=__doc__)
    parser.add_argument("--robot", default="bottles-v1", help="robot instrument profile")
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

    p = sub.add_parser("play", help="perform a score")
    p.add_argument("score")
    p.add_argument("--sim", action="store_true", help="use the simulated rig")
    p.add_argument("--realtime", action="store_true", help="run the clock in real time")
    p.set_defaults(func=cmd_play)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
