import pytest

from duet.feasibility import Code, check_robot
from duet.profile import robot_profile
from helpers import make_score

BOTTLES = robot_profile()


def test_playable_score_passes():
    score = make_score(robot=[(1, 1, 1, "C5"), (1, 2, 1, "D5"), (2, 1, 1, "C6"), (3, 1, 1, "C5")])
    report = check_robot(score, BOTTLES)
    assert report.ok, report.feedback()


def test_pianist_notes_are_ignored():
    assert check_robot(make_score(pianist=[(1, 1, 1, "C#4"), (1, 1, 1, "E4")]), BOTTLES).ok


def test_note_without_a_bottle():
    report = check_robot(make_score(robot=[(1, 1, 1, "C#5"), (1, 3, 1, "C4")]), BOTTLES)
    assert report.codes() == [Code.NOT_ON_BOTTLE, Code.NOT_ON_BOTTLE]
    assert "no bottle for C#5" in report.feedback()
    assert report.violations[0].event_index == 0


def test_two_notes_at_once():
    report = check_robot(make_score(robot=[(1, 1, 1, "C5"), (1, 1, 1, "E5")]), BOTTLES)
    assert report.codes() == [Code.SIMULTANEOUS]


def test_jump_too_fast():
    # At 120 bpm an eighth note is 0.25 s; C5 to C6 needs about 1.28 s.
    report = check_robot(make_score(robot=[(1, 1, 0.5, "C5"), (1, 1.5, 0.5, "C6")]), BOTTLES)
    (violation,) = report.violations
    assert violation.code == Code.TOO_FAST
    assert violation.available_s == pytest.approx(0.25)
    assert violation.needed_s == pytest.approx(1.275)
    assert violation.shortfall_s == pytest.approx(1.025)
    assert (
        report.feedback()
        == ("bar 1 beat 1.5: robot needs 1.27 s to go from C5 to C6 but has 0.25 s")
        or "needs 1.28 s" in report.feedback()
    )


def test_neighbours_at_eighths_are_fine_but_sixteenths_are_not():
    eighths = [(1, 1 + i * 0.5, 0.5, "C5" if i % 2 == 0 else "D5") for i in range(8)]
    assert check_robot(make_score(robot=eighths, tempo=90), BOTTLES).ok
    sixteenths = [(1, 1 + i * 0.25, 0.25, "C5" if i % 2 == 0 else "D5") for i in range(4)]
    assert set(check_robot(make_score(robot=sixteenths), BOTTLES).codes()) == {Code.TOO_FAST}


def test_repeated_note_needs_recovery_only():
    fast_repeats = [(1, 1 + i * 0.25, 0.25, "E5") for i in range(16)]
    assert check_robot(make_score(robot=fast_repeats, tempo=120), BOTTLES).ok


def test_duty_cycle_limit():
    # 10 notes/s at 150 bpm, full velocity: 30 ms each = 30% duty, over the 20% limit.
    notes = [(1 + i // 16, 1 + (i % 16) * 0.25, 0.25, "E5") for i in range(160)]
    score = make_score(robot=notes, tempo=150)
    data = score.to_dict()
    for event in data["events"]:
        event["vel"] = 127
    from duet.score import load_score

    report = check_robot(load_score(data), BOTTLES)
    assert Code.DUTY_CYCLE in report.codes()
    assert all(c == Code.DUTY_CYCLE for c in report.codes())
