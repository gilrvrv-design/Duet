import json

import pytest

from duet.compose import compose
from duet.compose.draft import DRAFT_SCHEMA, DraftError, draft_to_score, score_to_draft
from duet.compose.prompts import difficulty_rules, system_prompt
from duet.compose.service import CompositionError
from duet.feasibility import check_robot
from duet.profile import robot_profile
from duet.score import Duo
from helpers import GOOD, REQUEST, TOO_FAST, ScriptedComposer, draft


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
    assert check_robot(result.score, robot_profile(), part="robot").ok


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
    wrong_shapes = [
        ({"robot": "C5 D5"}, "robot must be a list"),
        ({"pianist": ["C4"]}, r"pianist\[0\] must be a note object"),
    ]
    for change, message in wrong_shapes:
        text = json.dumps({**json.loads(GOOD), **change})
        with pytest.raises(DraftError, match=message):
            draft_to_score(text, prompt="p", difficulty=1, pianist_range=("C4", "C5"))
    with pytest.raises(DraftError, match="JSON object"):
        draft_to_score("[]", prompt="p", difficulty=1, pianist_range=("C4", "C5"))


def test_drafts_are_written_for_a_duo():
    """The draft's two voices become the duo's parts, on the duo's instruments."""
    duo = Duo(bot="bells", bot_instrument="glock-v1", human="me", human_instrument="piano-61")
    score, _ = draft_to_score(GOOD, prompt="p", difficulty=1, pianist_range=("C4", "C5"), duo=duo)
    assert score.parts["bells"].instrument == "glock-v1"
    assert score.parts["bells"].performer == "bot"
    assert score.parts["me"].instrument == "piano-61"
    assert {e.part for e in score.events} == {"bells", "me"}


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
