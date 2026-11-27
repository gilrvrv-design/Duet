import pytest
from pydantic import ValidationError

from duet.score import DuetScore, load_score
from helpers import make_score

EXAMPLE = {
    "schema": "duetscore/1",
    "meta": {
        "title": "Rain on the Bottles",
        "key": "C major",
        "time_signature": [3, 4],
        "tempo_bpm": 84,
        "difficulty_target": 2,
    },
    "parts": {
        "robot": {"instrument_profile": "bottles-v1", "role": "melody"},
        "pianist": {
            "instrument_profile": "piano-88",
            "role": "accompaniment",
            "hand": "right",
            "range": ["C4", "C5"],
        },
    },
    "events": [
        {"part": "robot", "bar": 1, "beat": 1.0, "dur": 1.0, "pitch": "E5", "vel": 90},
        {"part": "pianist", "bar": 1, "beat": 1.0, "dur": 2.0, "pitch": "C4", "finger": 1},
        {"part": "robot", "bar": 2, "beat": 2.5, "dur": 0.5, "pitch": 79},
    ],
    "sections": [{"name": "A", "bars": [1, 2]}],
    "turns": [{"bars": [1, 1], "lead": "robot"}, {"bars": [2, 2], "lead": "pianist"}],
}


def test_example_loads_and_normalises_pitches():
    score = load_score(EXAMPLE)
    assert score.meta.beats_per_bar == 3
    assert [e.pitch for e in score.events] == [76, 60, 79]
    assert score.parts["pianist"].range == (60, 72)
    assert score.bar_count == 2


def test_json_round_trip_writes_pitch_names():
    score = load_score(EXAMPLE)
    text = score.to_json()
    assert '"E5"' in text and '"G5"' in text
    assert load_score(text) == score


def test_load_from_file(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(load_score(EXAMPLE).to_json())
    assert load_score(path).meta.title == "Rain on the Bottles"
    assert load_score(str(path)).meta.title == "Rain on the Bottles"


def test_defaults_fill_parts():
    score = DuetScore()
    assert set(score.parts) == {"robot", "pianist"}
    assert score.bar_count == 0


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"events": [{"part": "robot", "bar": 1, "beat": 4.0, "dur": 1, "pitch": "C5"}]}, "beat"),
        ({"events": [{"part": "robot", "bar": 0, "beat": 1, "dur": 1, "pitch": "C5"}]}, "bar"),
        ({"events": [{"part": "robot", "bar": 1, "beat": 1, "dur": 0, "pitch": "C5"}]}, "dur"),
        ({"events": [{"part": "robot", "bar": 1, "beat": 1, "dur": 1, "pitch": "H5"}]}, "pitch"),
        ({"events": [{"part": "drums", "bar": 1, "beat": 1, "dur": 1, "pitch": "C5"}]}, "part"),
        ({"sections": [{"name": "B", "bars": [2, 5]}]}, "sections"),
        ({"turns": [{"bars": [2, 1], "lead": "robot"}]}, "turns"),
        ({"meta": {"time_signature": [5, 3]}}, "time signature"),
        ({"meta": {"tempo_bpm": 5}}, "tempo_bpm"),
        ({"parts": {"robot": {"instrument_profile": "x"}}}, "missing parts"),
        ({"unknown": 1}, "unknown"),
    ],
)
def test_invalid_scores_rejected(change, message):
    with pytest.raises(ValidationError, match=message):
        load_score({**EXAMPLE, **change})


def test_part_events_sorted_and_helpers():
    score = make_score(robot=[(2, 1, 1, "C5"), (1, 3, 1, "D5")], pianist=[(1, 1, 4, "C4")])
    assert [e.bar for e in score.part_events("robot")] == [1, 2]
    assert score.with_tempo(90).meta.tempo_bpm == 90
    assert len(score.with_events(score.events[:1]).events) == 1


def test_bar_count_counts_ringing_notes():
    assert make_score(robot=[(1, 4, 1, "C5")]).bar_count == 1
    assert make_score(robot=[(1, 4, 1.5, "C5")]).bar_count == 2


def test_changed_copies_are_validated():
    score = make_score(robot=[(1, 1, 1, "C5")])
    bad = score.events[0].revised({"beat": 1.0}).model_copy(update={"beat": 9.0})
    with pytest.raises(ValidationError, match="outside a bar"):
        score.with_events([bad])
    with pytest.raises(ValidationError):
        score.with_tempo(1000)
    assert score.with_tempo(120).meta.tempo_bpm == 120
