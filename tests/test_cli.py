import json

import mido
import pytest

from duet.cli import main
from helpers import ROOT


@pytest.mark.parametrize(
    ("only", "expect"),
    [("robot", "robot (bot): 9/9 notes"), ("pianist", "LED frames: ")],
)
def test_play_one_part_alone(only, expect, capsys):
    example = str(ROOT / "examples" / "rain-on-the-bottles.json")
    assert main(["play", example, "--sim", "--only", only]) == 0
    out = capsys.readouterr().out
    assert f"playing the {only} part only" in out and expect in out


def test_practise_the_piano_part_alone_in_wait_mode(capsys):
    example = str(ROOT / "examples" / "rain-on-the-bottles.json")
    assert main(["play", example, "--sim", "--only", "pianist", "--wait"]) == 0
    assert "You played 4 of 4 notes right" in capsys.readouterr().out


def test_a_part_the_score_does_not_have_is_reported(capsys):
    example = str(ROOT / "examples" / "rain-on-the-bottles.json")
    assert main(["play", example, "--sim", "--only", "drums"]) == 2
    assert "no part named 'drums'; the score has ['robot', 'pianist']" in capsys.readouterr().err


def test_play_with_a_bot_on_the_piano(tmp_path, capsys):
    score = json.loads((ROOT / "examples" / "rain-on-the-bottles.json").read_text())
    score["parts"]["pianist"]["performer"] = "bot"  # the digital piano, over MIDI
    path = tmp_path / "two-bots.json"
    path.write_text(json.dumps(score))
    assert main(["play", str(path), "--sim"]) == 0
    out = capsys.readouterr().out
    assert "robot (bot): 9/9 notes, max timing error 0 us" in out
    assert "pianist (bot): 4/4 notes, max timing error 0 us" in out


def test_a_midi_import_says_what_it_ignored(tmp_path, capsys):
    midi = mido.MidiFile()
    track = mido.MidiTrack()
    track += [
        mido.Message("note_on", note=72, velocity=80, time=0),
        mido.Message("note_off", note=72, time=480),
        mido.Message("note_on", note=74, velocity=80, time=0),  # never released
    ]
    midi.tracks.append(track)
    path = tmp_path / "tune.mid"
    midi.save(path)
    assert main(["check", str(path)]) == 0
    assert "warning: 1 note(s) never released were left out" in capsys.readouterr().err
