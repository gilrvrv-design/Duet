from duet.cli import main
from duet.conductor import State, VirtualClock, build_messages, perform
from duet.profile import keyboard_profile, robot_profile
from duet.protocol import Home, MoveAt, StrikeAt, message_time_us
from duet.score import load_score
from duet.sim import SimulatedRig
from helpers import ROOT, make_score

BOTTLES = robot_profile()
PIANO = keyboard_profile()
EXAMPLE = ROOT / "examples" / "rain-on-the-bottles.json"


def test_messages_are_sorted_numbered_and_serialisable():
    score = make_score(robot=[(1, 1, 1, "C5"), (1, 3, 1, "G5")], pianist=[(1, 1, 2, "C4")])
    messages, planned = build_messages(score, BOTTLES, PIANO, start_us=5_000_000)
    times = [message_time_us(m) for m in messages]
    assert times == sorted(times)
    assert [m.seq for m in messages] == list(range(len(messages)))
    assert sum(isinstance(m, StrikeAt) for m in messages) == 2
    assert sum(isinstance(m, MoveAt) for m in messages) == 2
    assert '"type":"strike_at"' in next(m for m in messages if isinstance(m, StrikeAt)).to_json()
    assert [(p.part, p.pitch) for p in planned] == [("pianist", 60), ("robot", 72), ("robot", 79)]


def test_simulated_performance_plays_every_note_on_time():
    score = load_score(EXAMPLE)
    rig = SimulatedRig(BOTTLES)
    perf = perform(score, BOTTLES, PIANO, [rig], VirtualClock())
    rig.run()
    assert rig.faults == []
    robot_planned = [p for p in perf.planned if p.part == "robot"]
    assert [s.pitch for s in rig.sounds] == [p.pitch for p in robot_planned]
    assert all(abs(s.t_us - p.t_us) <= 1 for s, p in zip(rig.sounds, robot_planned, strict=True))
    assert perf.states == [
        State.IDLE,
        State.PREPARING,
        State.COUNT_IN,
        State.PLAYING,
        State.ENDING,
        State.REVIEW,
    ]
    assert isinstance(rig.received, list)


def test_simulator_catches_a_bad_plan():
    rig = SimulatedRig(BOTTLES)
    for msg in (Home(), MoveAt(0, 46000, 500, 5000, seq=1), StrikeAt(100_000, 20000, seq=2)):
        rig.send(msg)
    rig.run()
    assert rig.fault_codes == ["NOT_ARRIVED"]
    assert str(rig.faults[0]) == "t=100000: NOT_ARRIVED: strike before the carriage arrived"
    assert rig.sounds == []


def test_cli_check_play_convert_repair(tmp_path, capsys):
    assert main(["check", str(EXAMPLE)]) == 0
    assert "robot part: playable" in capsys.readouterr().out
    midi = tmp_path / "rain.mid"
    assert main(["convert", str(EXAMPLE), str(midi)]) == 0
    assert main(["play", str(midi), "--sim"]) == 0
    assert "robot notes: 9/9" in capsys.readouterr().out

    hard = tmp_path / "hard.json"
    hard.write_text(make_score(robot=[(1, 1, 0.5, "C5"), (1, 1.5, 0.5, "C6")]).to_json())
    assert main(["check", str(hard)]) == 1
    fixed = tmp_path / "fixed.json"
    assert main(["repair", str(hard), str(fixed)]) == 0
    assert main(["check", str(fixed)]) == 0
    assert main(["play", str(hard), "--sim"]) == 0
    assert main(["play", str(hard)]) == 2
