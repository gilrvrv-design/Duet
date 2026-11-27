import pytest

from duet.pitch import (
    PitchError,
    cents_between,
    hz_to_midi,
    is_black_key,
    midi_to_hz,
    midi_to_name,
    name_to_midi,
    to_midi,
)


@pytest.mark.parametrize(
    ("name", "midi"),
    [("C4", 60), ("A4", 69), ("C-1", 0), ("G9", 127), ("F#5", 78), ("Bb3", 58), ("c5", 72)],
)
def test_name_to_midi(name, midi):
    assert name_to_midi(name) == midi


def test_round_trip_all_midi_numbers():
    for midi in range(128):
        assert name_to_midi(midi_to_name(midi)) == midi


@pytest.mark.parametrize("bad", ["H4", "C", "C#", "", "Cx4", "G#9", "Cb-1"])
def test_bad_names_rejected(bad):
    with pytest.raises(PitchError):
        name_to_midi(bad)


def test_to_midi_accepts_both_forms():
    assert to_midi("E4") == 64
    assert to_midi(64) == 64
    with pytest.raises(PitchError):
        to_midi(200)
    with pytest.raises(PitchError):
        to_midi(True)


def test_frequency_conversions():
    assert midi_to_hz(69) == pytest.approx(440.0)
    assert midi_to_hz(60) == pytest.approx(261.6256, rel=1e-5)
    assert hz_to_midi(880.0) == pytest.approx(81.0)
    with pytest.raises(PitchError):
        hz_to_midi(0)


def test_cents():
    assert cents_between(440.0, 880.0) == pytest.approx(1200.0)
    assert cents_between(440.0, midi_to_hz(69.5)) == pytest.approx(50.0)


def test_black_keys():
    assert [m for m in range(60, 72) if is_black_key(m)] == [61, 63, 66, 68, 70]
