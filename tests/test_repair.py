from duet.feasibility import check_robot
from duet.profile import robot_profile
from duet.repair import repair_robot
from helpers import make_score

BOTTLES = robot_profile()


def robot_notes(score):
    return [(e.bar, e.beat, e.pitch) for e in score.part_events("robot")]


def test_playable_score_is_unchanged():
    score = make_score(robot=[(1, 1, 1, "C5"), (1, 2, 1, "D5")], pianist=[(1, 1, 2, "C4")])
    result = repair_robot(score, BOTTLES)
    assert result.changes == []
    assert result.score == score


def test_octave_fold_and_nearest_bottle():
    score = make_score(robot=[(1, 1, 1, "E4"), (2, 1, 1, "C7"), (3, 1, 1, "F#5")])
    result = repair_robot(score, BOTTLES)
    assert robot_notes(result.score) == [(1, 1, 76), (2, 1, 84), (3, 1, 77)]
    assert result.count("fold") == 3
    assert "E4 -> E5" in result.summary()


def test_simultaneous_keeps_highest():
    score = make_score(robot=[(1, 1, 1, "C5"), (1, 1, 1, "E5")])
    result = repair_robot(score, BOTTLES)
    assert robot_notes(result.score) == [(1, 1, 76)]
    assert result.count("drop") == 1


def test_small_shift_instead_of_drop():
    # C5 -> E5 needs 0.38 s; at 120 bpm an eighth note gives 0.25 s; next grid point is 0.75 beat.
    score = make_score(robot=[(1, 1, 1, "C5"), (1, 1.5, 1, "E5"), (2, 1, 1, "C5")])
    result = repair_robot(score, BOTTLES)
    assert robot_notes(result.score) == [(1, 1, 72), (1, 2.0, 76), (2, 1, 72)]
    assert result.count("shift") == 1
    assert result.score.part_events("robot")[1].dur == 0.5


def test_big_jump_is_dropped():
    score = make_score(
        robot=[
            (1, 1, 1, "C5"),
            (1, 1.5, 1, "C6"),
            (1, 3, 1, "D5"),
            (2, 1, 1, "E5"),
            (3, 1, 1, "F5"),
        ]
    )
    result = repair_robot(score, BOTTLES)
    assert (1, 1.5, 84) not in robot_notes(result.score)
    assert result.count("drop") == 1
    assert check_robot(result.score, BOTTLES).ok


def test_tempo_lowered_when_too_much_would_be_dropped():
    # A fast arpeggio over the full span: dropping would lose most notes, so slow down.
    pitches = ["C5", "C6"] * 4
    score = make_score(robot=[(1, 1 + i * 0.5, 0.5, p) for i, p in enumerate(pitches)])
    result = repair_robot(score, BOTTLES)
    assert result.changes[0].kind == "tempo"
    assert result.score.meta.tempo_bpm < 120
    assert result.count("drop") < 4
    assert check_robot(result.score, BOTTLES).ok


def test_repair_always_ends_feasible():
    import random

    rng = random.Random(7)
    for _ in range(30):
        notes = [
            (1 + i // 8, 1 + (i % 8) * 0.5, 0.5, rng.choice(["C4", "C5", "G5", "C6", "A#5", "E6"]))
            for i in range(rng.randint(1, 40))
        ]
        score = make_score(robot=notes, tempo=rng.choice([60, 100, 140, 200]))
        assert check_robot(repair_robot(score, BOTTLES).score, BOTTLES).ok
