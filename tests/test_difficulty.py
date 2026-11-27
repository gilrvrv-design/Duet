from duet.difficulty import check_pianist, pianist_difficulty, pianist_stats
from duet.profile import keyboard_profile
from duet.score import load_score
from helpers import make_score

PIANO = keyboard_profile()


def test_empty_part_is_level_1():
    assert pianist_difficulty(make_score()) == 1


def test_whole_notes_on_white_keys_are_level_1():
    score = make_score(pianist=[(1, 1, 4, "C4"), (2, 1, 4, "E4"), (3, 1, 4, "D4")], tempo=60)
    assert pianist_difficulty(score) == 1


def test_levels_rise_with_features():
    offbeat = make_score(pianist=[(1, 1, 1.5, "C4"), (1, 2.5, 1.5, "D4")], tempo=60)
    assert pianist_difficulty(offbeat) == 2
    black = make_score(pianist=[(1, 1, 2, "C4"), (1, 3, 2, "F#4")], tempo=60)
    assert pianist_difficulty(black) == 3
    chord = make_score(pianist=[(1, 1, 2, "C4"), (1, 1, 2, "E4"), (1, 1, 2, "G4")], tempo=60)
    assert pianist_difficulty(chord) == 4
    fast = make_score(pianist=[(1, 1 + i * 0.25, 0.25, "C4") for i in range(16)], tempo=120)
    assert pianist_difficulty(fast) == 5


def test_stats():
    score = make_score(pianist=[(1, 1, 1, "C4"), (1, 2, 1, "G4"), (1, 3, 2, "E4")], tempo=60)
    stats = pianist_stats(score)
    assert (stats.notes, stats.max_jump, stats.max_polyphony) == (3, 7, 1)
    assert stats.notes_per_s == 1.0  # onsets at 0, 1 and 2 s
    assert (stats.low, stats.high) == (60, 67)


def test_check_pianist_range_and_level():
    data = make_score(pianist=[(1, 1, 1, "C4"), (1, 2, 1, "C6"), (1, 3, 1, "C9")]).to_dict()
    data["parts"]["pianist"]["range"] = ["C4", "C5"]
    data["meta"]["difficulty_target"] = 1
    problems = check_pianist(load_score(data), PIANO)
    assert "bar 1 beat 2: C6 is outside C4-C5" in problems
    assert "bar 1 beat 3: C9 is not on the keyboard" in problems
    assert any(p.startswith("too hard for level 1: a jump of") for p in problems)
    assert check_pianist(make_score(pianist=[(1, 1, 4, "C4")]), PIANO) == []
