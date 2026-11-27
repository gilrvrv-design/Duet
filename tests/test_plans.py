import pytest

from duet.plans import (
    InfeasibleScoreError,
    led_count,
    led_plan,
    led_span,
    robot_plan,
)
from duet.profile import keyboard_profile, robot_profile
from helpers import make_score

BOTTLES = robot_profile()
PIANO = keyboard_profile()


def test_robot_plan_moves_just_in_time():
    score = make_score(robot=[(1, 1, 1, "C5"), (1, 3, 1, "E5"), (2, 1, 1, "E5")])
    plan = robot_plan(score, BOTTLES)
    first, second, third = plan.commands
    assert first.sound_s == 0 and first.fire_s == pytest.approx(-0.012)
    assert first.move_start_s < first.fire_s
    assert plan.preroll_s == pytest.approx(-first.move_start_s)
    assert second.target_steps == 14000
    assert second.move_start_s == pytest.approx(second.fire_s - second.move_s)
    assert second.move_start_s > first.fire_s + first.pulse_us / 1e6
    assert third.move_s == 0


def test_robot_plan_refuses_infeasible_scores():
    with pytest.raises(InfeasibleScoreError, match="no bottle"):
        robot_plan(make_score(robot=[(1, 1, 1, "C#5")]), BOTTLES)


def test_led_strip_covers_keyboard():
    assert led_count(PIANO) == 176  # 52 white keys * 23.5 mm at 144/m


def test_led_spans_are_about_two_per_semitone_and_ordered():
    spans = [led_span(m, PIANO) for m in range(21, 109)]
    assert all(1 <= count <= 3 for _, count in spans)
    starts = [first for first, _ in spans]
    assert starts == sorted(starts)
    assert spans[-1][0] + spans[-1][1] <= led_count(PIANO)
    assert sum(c for _, c in spans) == pytest.approx(176, abs=4)
    with pytest.raises(ValueError):
        led_span(10, PIANO)


def test_led_plan_cues():
    score = make_score(pianist=[(1, 1, 1, "C4"), (1, 3, 2, "E4")], tempo=120)
    cues = led_plan(score, PIANO)
    kinds = [c.kind for c in cues]
    assert kinds.count("count_in") == 4
    assert kinds.count("now") == 2 and kinds.count("pre") == 2
    now = [c for c in cues if c.kind == "now"]
    assert (now[1].on_s, now[1].off_s) == (1.0, 2.0)
    pre = [c for c in cues if c.kind == "pre"]
    assert pre[1].on_s == 0.5 and pre[1].off_s == 1.0
    assert cues[0].on_s == -2.0
