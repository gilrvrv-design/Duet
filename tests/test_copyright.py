import json

import pytest

from duet.compose import CompositionRequest, compose
from duet.compose.service import CompositionError
from duet.copyright import CopyrightGuard, longest_run, melody_line
from helpers import ScriptedComposer, draft, make_score

# An invented "protected" melody for the tests (no real copyrighted tune is stored).
PROTECTED = {
    "melodies": [
        {
            "title": "Invented Hit",
            "notes": ["C4", "E4", "D4", "G4", "F4", "A4", "G4", "C5", "B4", "D5"],
        }
    ]
}


@pytest.fixture
def guard(tmp_path):
    path = tmp_path / "protected.yaml"
    path.write_text(json.dumps(PROTECTED))
    return CopyrightGuard.load(path)


def tune(pitches, part="robot", start_bar=1, tempo=100):
    notes = [(start_bar + i // 4, 1 + i % 4, 1, p) for i, p in enumerate(pitches)]
    return make_score(**{part: notes}, tempo=tempo)


def test_runs_ignore_scales_and_repeats():
    assert longest_run((2, 2, 1, 2, 2, 2, 1), (2, 2, 1, 2, 2, 2, 1)) == 0  # a plain scale
    assert longest_run((0, 0, 0, 0, 0), (0, 0, 0, 0, 0)) == 0
    assert longest_run((4, -2, 5, -2, 4), (9, 4, -2, 5, -2, 4, 1)) == 5


def test_public_domain_tunes_are_recognised_and_allowed(guard):
    twinkle = [72, 72, 79, 79, 81, 81, 79, 77, 77, 76, 76, 74, 74, 72]  # transposed up an octave
    verdict = guard.check(tune(twinkle))
    assert verdict.status == "public_domain"
    assert verdict.matches[0].title == "Twinkle Twinkle Little Star"
    assert verdict.problems() == []


def test_a_copied_melody_is_caught_transposed_and_at_any_tempo(guard):
    copied = [p + 5 for p in [60, 64, 62, 67, 65, 69, 67, 72, 71, 74]]  # in F, not C
    verdict = guard.check(tune(copied, part="pianist", tempo=150))
    assert verdict.status == "protected"
    assert 'copies 10 notes of "Invented Hit"' in verdict.problems()[0]
    partial = guard.check(tune([60, 64, 62, 67, 65, 69, 50]))
    assert partial.status == "review"  # 5 intervals: worth a look, not a block


def test_original_melodies_pass(guard):
    assert guard.check(tune([72, 76, 79, 77, 74, 72, 81, 79, 76, 84])).status == "original"
    assert melody_line(make_score(pianist=[(1, 1, 1, "C4"), (1, 1, 1, "E4")]), "pianist") == [64]


def test_composer_is_told_to_write_something_original(guard):
    names = ["C5", "E5", "D5", "G5", "F5", "A5", "G5", "C6"]
    copy = draft(
        [(1 + i // 2, 1 + (i % 2) * 2, 2, n) for i, n in enumerate(names)], [(1, 1, 4, "C4")]
    )
    original = draft([(1, 1, 2, "E5"), (1, 3, 2, "G5"), (2, 1, 4, "C6")], [(1, 1, 4, "C4")])
    request = CompositionRequest(prompt="a hit song", difficulty=1, bars=4)
    composer = ScriptedComposer(copy, original)
    result = compose(request, composer, guard=guard)
    assert result.rounds == 2
    assert "write an original melody" in result.feedback[0][-1]
    with pytest.raises(CompositionError, match="protected melody"):
        compose(request, ScriptedComposer(copy, copy, copy, copy), guard=guard)
