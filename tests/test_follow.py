import statistics

import pytest

from duet.conductor import VirtualClock, perform
from duet.follow import Follower, TempoPianist, max_speed_up
from duet.listening import Expected, PlayedNote
from duet.profile import keyboard_profile, robot_profile
from duet.sim import SimulatedRig
from helpers import make_score

ROBOT, PIANO = robot_profile(), keyboard_profile()
# Robot and pianist play together on every beat for 8 bars.
SCORE = make_score(
    robot=[(b, beat, 1, "E5" if beat % 2 else "G5") for b in range(1, 9) for beat in (1, 2, 3, 4)],
    pianist=[(b, beat, 1, "C4") for b in range(1, 9) for beat in (1, 2, 3, 4)],
    tempo=90,
)


def test_follower_learns_tempo_and_phase():
    expected = [Expected(i * 500_000, 60, 1) for i in range(8)]
    f = Follower(expected)
    for i in range(8):  # the pianist plays 20% slower
        assert f.hear(PlayedNote(round(i * 600_000), 60))
    assert f.rate == pytest.approx(1.2, abs=0.01)
    assert f.to_clock(8 * 500_000) == pytest.approx(8 * 600_000, abs=2000)
    assert not f.hear(PlayedNote(99_000_000, 60))  # nothing left to match


def test_follower_limits_and_wrong_notes():
    expected = [Expected(i * 500_000, 60 + i, 1) for i in range(6)]
    f = Follower(expected, min_rate=0.9)
    for i in range(6):  # rushing at twice the speed is capped
        f.hear(PlayedNote(i * 250_000, 60 + i))
    assert f.rate == pytest.approx(0.9)
    g = Follower(expected)
    assert g.hear(PlayedNote(10_000, 99))  # wrong key, right time: still advances
    assert g.position == 1


def test_max_speed_up_comes_from_robot_slack():
    # C5 -> C6 needs 1.275 s with margin; at 47 bpm a beat is 1.277 s: almost no slack.
    tight = make_score(robot=[(1, 1, 1, "C5"), (1, 2, 1, "C6")], tempo=47)
    assert max_speed_up(tight, ROBOT) == pytest.approx(1.0, abs=0.01)
    # E5 -> G5 needs 0.475 s; a beat at 90 bpm is 0.667 s, so the robot can go 1.40x faster.
    assert max_speed_up(SCORE, ROBOT) == pytest.approx(1.40, abs=0.01)


def perform_with(pianist):
    rig = SimulatedRig(ROBOT)
    perf = perform(SCORE, ROBOT, PIANO, [rig], VirtualClock(1_000_000), keys=pianist, mode="follow")
    rig.run()
    return perf, rig


@pytest.mark.parametrize("args", [{"stretch": 1.15}, {"stretch": 0.9}, {"accelerate": -0.01}])
def test_robot_stays_with_a_pianist_who_changes_tempo(args):
    pianist = TempoPianist(**args)
    perf, rig = perform_with(pianist)
    assert rig.faults == []
    robot = [s.t_us for s in rig.sounds]
    piano = [p.t_us for p in pianist.played]
    assert len(robot) == len(piano) == 32
    errors = [abs(r - p) for r, p in zip(robot[4:], piano[4:], strict=True)]  # after 1 bar
    assert statistics.median(errors) < 40_000, errors
    assert max(errors) < 120_000


def test_without_follow_the_robot_drifts_away():
    rig = SimulatedRig(ROBOT)
    perf = perform(SCORE, ROBOT, PIANO, [rig], VirtualClock(1_000_000))
    rig.run()
    pianist = TempoPianist(stretch=1.15)
    pianist.begin(perf.expected_pianist())
    drift = abs(rig.sounds[-1].t_us - pianist.schedule[-1].t_us)
    assert drift > 2_000_000  # over 2 s apart by the end of 8 bars


def test_cli_follow(tmp_path, capsys):
    from duet.cli import main

    score = tmp_path / "s.json"
    score.write_text(SCORE.to_json())
    assert main(["play", str(score), "--sim", "--follow", "--stretch", "1.25"]) == 0
    out = capsys.readouterr().out
    assert "tempo now 8" in out and "faults: 0" in out  # about 80% of written
