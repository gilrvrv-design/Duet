import pytest

from duet.cli import main
from helpers import ROOT


@pytest.mark.parametrize(
    ("only", "expect"),
    [("robot", "robot notes: 9/9"), ("piano", "robot notes: 0/0")],
)
def test_play_one_part_alone(only, expect, capsys):
    example = str(ROOT / "examples" / "rain-on-the-bottles.json")
    assert main(["play", example, "--sim", "--only", only]) == 0
    out = capsys.readouterr().out
    assert f"playing the {only} part only" in out and expect in out


def test_practise_the_piano_part_alone_in_wait_mode(capsys):
    example = str(ROOT / "examples" / "rain-on-the-bottles.json")
    assert main(["play", example, "--sim", "--only", "piano", "--wait"]) == 0
    assert "You played 4 of 4 notes right" in capsys.readouterr().out
