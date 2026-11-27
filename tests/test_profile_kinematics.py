import pytest
from pydantic import ValidationError

from duet.kinematics import move_time_s, reachability, strike_interval_s, travel_time_s
from duet.profile import (
    KeyboardProfile,
    RobotProfile,
    keyboard_profile,
    load_profile,
    load_profile_file,
    robot_profile,
)


def test_builtin_profiles_load():
    bottles = robot_profile()
    assert bottles.pitches == [72, 74, 76, 77, 79, 81, 83, 84]
    piano = keyboard_profile()
    assert (piano.low, piano.high) == (21, 108)
    assert piano.contains(60) and not piano.contains(110)
    with pytest.raises(KeyError):
        load_profile("kazoo")
    with pytest.raises(TypeError):
        robot_profile("piano-88")


def test_profile_from_file(tmp_path):
    path = tmp_path / "p.yaml"
    path.write_text(
        "id: k\nkind: keyboard\nlow: C4\nhigh: C5\nled: {leds_per_m: 60, white_key_mm: 23}\n"
    )
    assert isinstance(load_profile_file(path), KeyboardProfile)


def test_bottle_lookup_uses_measured_pitch():
    bottles = robot_profile()
    assert bottles.bottle_index(72) == 0
    assert bottles.bottle_index(84) == 7
    assert bottles.bottle_index(73) is None  # C#5 is not a bottle
    detuned = bottles.model_copy(
        update={"notes": (bottles.notes[0].model_copy(update={"hz": 540.0}), *bottles.notes[1:])}
    )
    assert detuned.bottle_index(72) is None  # 55 cents sharp
    assert detuned.bottle_index(72, tolerance_cents=60) == 0


def test_robot_profile_rejects_bad_positions():
    data = robot_profile().model_dump(mode="json")
    data["notes"][1]["steps"] = 0
    with pytest.raises(ValidationError, match="increasing"):
        RobotProfile.model_validate(data)


def test_velocity_to_pulse():
    striker = robot_profile().striker
    assert striker.pulse_for_velocity(1) == 15000
    assert striker.pulse_for_velocity(127) == 30000


def test_travel_time_trapezoid_and_triangle():
    # v=500 mm/s, a=5000 mm/s2: top speed reached after 50 mm of accel+decel.
    assert travel_time_s(80, 500, 5000) == pytest.approx(0.26)
    assert travel_time_s(560, 500, 5000) == pytest.approx(1.22)
    assert travel_time_s(20, 500, 5000) == pytest.approx(2 * (20 / 5000) ** 0.5)
    assert travel_time_s(-80, 500, 5000) == travel_time_s(80, 500, 5000)
    assert travel_time_s(0, 500, 5000) == 0


def test_move_time_adds_settle():
    kin = robot_profile().kinematics
    assert move_time_s(1200, 7600, kin) == pytest.approx(0.26 + 0.015)
    assert move_time_s(100, 100, kin) == 0


def test_reachability_matrix():
    bottles = robot_profile()
    matrix = reachability(bottles)
    assert matrix.min_interval(0, 0) == pytest.approx(0.06)
    assert matrix.min_interval(0, 1) == pytest.approx(0.03 + 0.26 + 0.015)
    assert matrix.min_interval(0, 7) == pytest.approx(0.03 + 1.22 + 0.015)
    assert matrix.min_interval(3, 5) == matrix.min_interval(5, 3)
    assert matrix.min_interval(0, 1) == strike_interval_s(bottles, 0, 1)
    table = matrix.as_table()
    assert table.splitlines()[0].split()[1:] == ["C5", "D5", "E5", "F5", "G5", "A5", "B5", "C6"]
    assert "1265" in table
