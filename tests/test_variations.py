import json
from functools import partial

import pytest

from duet.compose.service import revise
from duet.difficulty import pianist_difficulty
from duet.feasibility import check_robot
from duet.profile import keyboard_profile, robot_profile
from duet.score import load_score
from duet.variations import vary
from helpers import ROOT, make_score

ROBOT, PIANO = robot_profile(), keyboard_profile()
EXAMPLE = load_score(ROOT / "examples" / "rain-on-the-bottles.json")
HARD = make_score(
    robot=[(b, 1, 2, "E5") for b in range(1, 5)],
    pianist=[
        (b, beat, 0.5, p)
        for b in range(1, 5)
        for beat, p in ((1, "C4"), (1, "E4"), (1.5, "F#4"), (2, "C5"), (3, "G3"), (3.5, "A4"))
    ],
    tempo=100,
)


def test_slower_and_faster():
    slow, note = vary(EXAMPLE, "slower")
    assert slow.meta.tempo_bpm == pytest.approx(84 * 0.85, abs=0.1) and "84 ->" in note
    fast, _ = vary(EXAMPLE, "Faster")
    assert fast.meta.tempo_bpm > 84 and check_robot(fast, ROBOT).ok


def test_faster_never_breaks_the_robot():
    tight = make_score(robot=[(1, 1, 1, "C5"), (1, 2, 1, "C6")], tempo=47)
    fast, _ = vary(tight, "faster")
    assert check_robot(fast, ROBOT).ok and fast.meta.tempo_bpm == pytest.approx(47, abs=0.5)


def test_easier_steps_down_until_it_fits():
    assert pianist_difficulty(HARD) == 5
    level = 5
    score = HARD
    while level > 1:
        score, note = vary(score, "easier")
        assert pianist_difficulty(score) < level, note
        level = pianist_difficulty(score)
    assert score.part_events("robot") == HARD.part_events("robot")  # the robot part is untouched


def test_swap_puts_each_part_on_its_instrument():
    swapped, _ = vary(EXAMPLE, "swap")
    assert check_robot(swapped, ROBOT).ok
    robot_pitches = [e.pitch for e in swapped.part_events("robot")]
    assert all(p in ROBOT.pitches for p in robot_pitches)
    assert len(swapped.part_events("pianist")) == len(EXAMPLE.part_events("robot"))
    low, high = EXAMPLE.parts["pianist"].range
    assert all(low - 12 <= e.pitch <= high + 12 for e in swapped.part_events("pianist"))


class EditComposer:
    """Returns the current draft from the message, in a minor key (A instead of C)."""

    def write(self, system, messages):
        text = messages[0]["content"]
        draft = json.loads(text.split("Here is the current duet:\n")[1].split("\n\nChange it:")[0])
        draft["key"] = "A minor"
        for note in draft["pianist"]:
            if note["pitch"] == "C4":
                note["pitch"] = "A3"
        draft["explanation"] = "Moved to A minor."
        assert "Change it: in a minor key" in text
        return json.dumps(draft)


def test_other_instructions_go_to_the_composer_as_an_edit():
    data = EXAMPLE.to_dict()
    data["parts"]["pianist"]["range"] = ["A3", "C5"]
    score = load_score(data)
    new, note = vary(score, "in a minor key", edit=partial(revise, composer=EditComposer()))
    assert new.meta.key == "A minor" and note == "Moved to A minor."
    assert [e.pitch for e in new.part_events("robot")] == [
        e.pitch for e in score.part_events("robot")
    ]
    with pytest.raises(ValueError, match="needs the composer"):
        vary(score, "add a bridge")


def test_easier_always_lowers_the_level_on_random_parts():
    import random

    rng = random.Random(3)
    names = ["C3", "E3", "G3", "A#3", "C4", "D4", "F#4", "G4", "B4", "C5", "E5", "A5"]
    for _ in range(40):
        notes = [
            (rng.randint(1, 4), rng.choice([1, 1.5, 2, 2.5, 3, 3.5, 4]), 0.5, rng.choice(names))
            for _ in range(rng.randint(4, 24))
        ]
        score = make_score(robot=[(1, 1, 1, "C5")], pianist=notes, tempo=rng.choice([60, 100, 140]))
        level = pianist_difficulty(score)
        while level > 1:
            score, note = vary(score, "easier")
            new = pianist_difficulty(score)
            assert new < level, (note, notes)
            level = new


def test_cli_vary(tmp_path, capsys):
    from duet.cli import main

    out = tmp_path / "slow.json"
    example = str(ROOT / "examples" / "rain-on-the-bottles.json")
    assert main(["vary", example, "slower", str(out)]) == 0
    assert "tempo 84 -> 71.4 bpm" in capsys.readouterr().out
    assert load_score(out).meta.tempo_bpm == 71.4
