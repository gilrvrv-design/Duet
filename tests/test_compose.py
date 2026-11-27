import json

import pytest

from duet.compose import CompositionRequest, compose
from duet.compose.draft import DRAFT_SCHEMA, DraftError, draft_to_score, score_to_draft
from duet.compose.prompts import difficulty_rules, system_prompt
from duet.compose.service import CompositionError
from duet.feasibility import check_robot
from duet.profile import robot_profile


def draft(robot, pianist, **meta):
    note = lambda b, bt, d, p: {"bar": b, "beat": bt, "dur": d, "pitch": p, "vel": 80}  # noqa: E731
    return json.dumps(
        {
            "title": "Test",
            "key": "C major",
            "beats_per_bar": 4,
            "beat_unit": 4,
            "tempo_bpm": 100,
            "robot": [note(*n) for n in robot],
            "pianist": [note(*n) for n in pianist],
            "explanation": "The robot sings, you hold the bass.",
            **meta,
        }
    )


GOOD = draft(
    [(1, 1, 2, "E5"), (1, 3, 2, "G5"), (2, 1, 4, "C6")], [(1, 1, 4, "C4"), (2, 1, 4, "E4")]
)
TOO_FAST = draft([(1, 1, 0.5, "C5"), (1, 1.5, 0.5, "C6")], [(1, 1, 4, "C4")])


class ScriptedComposer:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def write(self, system, messages):
        self.calls.append((system, [dict(m) for m in messages]))
        return self.answers.pop(0)


REQUEST = CompositionRequest(prompt="a happy tune", difficulty=1, bars=2)


def test_good_first_draft():
    composer = ScriptedComposer(GOOD)
    result = compose(REQUEST, composer)
    assert result.rounds == 1 and result.repairs == [] and result.warnings == []
    assert result.score.meta.prompt == "a happy tune"
    assert result.explanation.startswith("The robot sings")
    system, messages = composer.calls[0]
    assert "C5, D5, E5, F5, G5, A5, B5, C6" in system
    assert "Pianist difficulty level 1" in messages[0]["content"]


def test_feedback_round_fixes_problem():
    composer = ScriptedComposer(TOO_FAST, GOOD)
    result = compose(REQUEST, composer)
    assert result.rounds == 2
    assert "needs" in result.feedback[0][0]
    _, messages = composer.calls[1]
    assert messages[-1]["role"] == "user" and "Fix only these problems" in messages[-1]["content"]
    assert messages[-2]["role"] == "assistant"


def test_invalid_json_is_fed_back():
    composer = ScriptedComposer("not json", GOOD)
    result = compose(REQUEST, composer)
    assert result.rounds == 2
    assert "not valid JSON" in result.feedback[0][0]


def test_falls_back_to_deterministic_repair():
    composer = ScriptedComposer(TOO_FAST, TOO_FAST, TOO_FAST, TOO_FAST)
    result = compose(REQUEST, composer)
    assert result.rounds == 4 and len(composer.calls) == 4
    assert result.repairs
    assert check_robot(result.score, robot_profile()).ok


def test_out_of_range_pianist_notes_dropped_at_the_end():
    bad = draft([(1, 1, 4, "C5")], [(1, 1, 4, "C2"), (1, 1, 4, "C4")])
    result = compose(REQUEST, ScriptedComposer(bad, bad, bad, bad))
    assert [e.pitch for e in result.score.part_events("pianist")] == [60]
    assert "dropped 1 pianist note(s) out of range" in result.warnings


def test_never_valid_raises():
    with pytest.raises(CompositionError):
        compose(REQUEST, ScriptedComposer("x", "y"), max_rounds=1)


def test_draft_round_trip_and_errors():
    score, explanation = draft_to_score(GOOD, prompt="p", difficulty=2, pianist_range=("C4", "C5"))
    again, _ = draft_to_score(
        score_to_draft(score, explanation), prompt="p", difficulty=2, pianist_range=("C4", "C5")
    )
    assert again == score
    with pytest.raises(DraftError, match="missing fields"):
        draft_to_score("{}", prompt="p", difficulty=1, pianist_range=("C4", "C5"))
    with pytest.raises(DraftError, match="invalid score"):
        draft_to_score(
            draft([(1, 9, 1, "C5")], []), prompt="p", difficulty=1, pianist_range=("C4", "C5")
        )


def test_schema_is_strict_friendly():
    def check(schema):
        if schema.get("type") == "object":
            assert schema["additionalProperties"] is False
            assert set(schema["required"]) == set(schema["properties"])
            for sub in schema["properties"].values():
                check(sub)
        if schema.get("type") == "array":
            check(schema["items"])

    check(DRAFT_SCHEMA)


def test_prompts_mention_rules():
    assert "1265" in system_prompt(robot_profile())  # reachability table is included
    assert "white keys only" in difficulty_rules(1)
    assert "any speed" in difficulty_rules(5)
