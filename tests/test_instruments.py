import pytest
from pydantic import ValidationError

from duet.instruments import Instrument, instrument, load_instrument_file, save_instrument_file
from duet.profile import KeyboardProfile, RobotProfile, keyboard_profile, robot_profile

BOTTLES = instrument("bottles-v1")


def data(**changes) -> dict:
    return {**BOTTLES.model_dump(mode="json", by_alias=True, exclude_none=True), **changes}


def test_built_in_instruments_and_who_can_play_them():
    assert BOTTLES.name == "Glass bottles" and BOTTLES.pitches == [72, 74, 76, 77, 79, 81, 83, 84]
    assert BOTTLES.performers == ("bot",)
    piano = instrument("piano-88")
    assert piano.performers == ("human",)
    assert piano.pitches[0] == 21 and piano.pitches[-1] == 108 and len(piano.pitches) == 88
    assert instrument("glock-v1").performers == ("bot",)
    with pytest.raises(KeyError, match="unknown instrument: kazoo"):
        instrument("kazoo")


def without(key: str) -> dict:
    raw = data()
    del raw[key]
    return raw


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (data(range=["C4", "C5"]), "either notes or a range"),
        ({**without("notes"), "range": ["C5", "C4"]}, "low note is above the high note"),
        (without("bot"), "nothing can play it"),
        (data(notes=[{"name": "C5"}, {"name": "C5"}]), "share a pitch"),
        (data(notes=[{"name": "C5", "hz": 540.0}]), "cents off its name"),
    ],
)
def test_an_instrument_breaking_a_rule_is_refused(raw, message):
    with pytest.raises(ValidationError, match=message):
        Instrument.model_validate(raw)


def test_a_bot_needs_a_position_for_every_note():
    raw = data()
    raw["bot"] = {**raw["bot"], "positions": raw["bot"]["positions"][:-1]}
    with pytest.raises(ValidationError, match="one position per note"):
        Instrument.model_validate(raw)
    raw = data()
    raw["bot"] = {**raw["bot"], "positions": list(reversed(raw["bot"]["positions"]))}
    with pytest.raises(ValidationError, match="strictly increasing"):
        Instrument.model_validate(raw)


def test_files_round_trip(tmp_path):
    for name in ("bottles-v1", "glock-v1", "piano-88"):
        path = tmp_path / f"{name}.yaml"
        save_instrument_file(instrument(name), path)
        assert load_instrument_file(path) == instrument(name)


def test_profiles_are_read_only_views_of_an_instrument():
    """Every fact and rule is the instrument's; a profile only presents it."""
    view = robot_profile()
    assert view.instrument == BOTTLES
    assert view.notes[2].steps == BOTTLES.bot.positions[2]
    assert view.notes[2].hz == BOTTLES.notes[2].hz and view.striker == BOTTLES.bot.striker
    piano = instrument("piano-88")
    assert KeyboardProfile(piano).instrument == piano
    assert keyboard_profile().led.leds_per_m == 144
    with pytest.raises(TypeError, match="not played by a carriage-striker bot"):
        RobotProfile(piano)
    with pytest.raises(TypeError, match="not a keyboard"):
        KeyboardProfile(BOTTLES)
