import pytest

from duet.timing import (
    bar_and_beat,
    beat_index,
    score_duration_s,
    seconds_per_beat,
    timed_events,
)
from helpers import make_score


def test_seconds_per_beat():
    assert seconds_per_beat(120) == 0.5
    with pytest.raises(ValueError):
        seconds_per_beat(0)


@pytest.mark.parametrize(
    ("bar", "beat", "per_bar", "index"),
    [(1, 1, 4, 0), (1, 2.5, 4, 1.5), (2, 1, 4, 4), (3, 3, 3, 8)],
)
def test_beat_index_and_inverse(bar, beat, per_bar, index):
    assert beat_index(bar, beat, per_bar) == index
    assert bar_and_beat(index, per_bar) == (bar, beat)


def test_bar_and_beat_rejects_negative():
    with pytest.raises(ValueError):
        bar_and_beat(-1, 4)


def test_timed_events_at_120_bpm():
    score = make_score(robot=[(2, 1, 1, "C5"), (1, 3, 0.5, "E5")], pianist=[(1, 1, 2, "C4")])
    timed = timed_events(score)
    assert [(t.event.pitch, t.start_s, t.end_s) for t in timed] == [
        (60, 0.0, 1.0),
        (76, 1.0, 1.25),
        (72, 2.0, 2.5),
    ]
    assert [t.event.part for t in timed_events(score, "robot")] == ["robot", "robot"]
    assert timed[1].duration_s == 0.25
    assert score_duration_s(score) == 2.5


def test_empty_score_duration():
    assert score_duration_s(make_score()) == 0.0
