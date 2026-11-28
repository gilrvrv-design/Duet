import pytest

from duet.instruments import Instrument, instrument
from duet.performers import (
    Bot,
    Human,
    human_difficulty,
    performer,
    performers,
    repair_bots,
    score_problems,
)
from duet.score import LineUpError
from helpers import make_score

PLAYABLE = make_score(robot=[(1, 1, 1, "C5"), (1, 3, 1, "E5")], pianist=[(1, 1, 4, "C4")])
TOO_FAST = make_score(robot=[(1, 1, 0.25, "C5"), (1, 1.25, 0.25, "C6")], pianist=[])


def test_each_part_gets_its_performer():
    bot, human = performers(PLAYABLE)
    assert isinstance(bot, Bot) and bot.part == "robot" and bot.instrument.id == "bottles-v1"
    assert isinstance(human, Human) and human.part == "pianist"
    assert human.instrument.id == "piano-88"


def test_each_performer_judges_its_own_part():
    assert score_problems(PLAYABLE) == {"robot": [], "pianist": []}
    problems = score_problems(TOO_FAST)
    assert problems["pianist"] == [] and "needs" in problems["robot"][0]
    hard = make_score(pianist=[(1, 1, 1, "C#4")], difficulty_target=1)
    assert score_problems(hard)["pianist"] == ["too hard for level 1: black keys"]
    assert human_difficulty(hard) >= 3


def test_repair_fixes_every_bot_part_and_leaves_people_alone():
    result = repair_bots(TOO_FAST)
    assert result.changes and score_problems(result.score)["robot"] == []
    assert result.score.part_events("pianist") == TOO_FAST.part_events("pianist")


def test_the_instruments_in_use_come_before_the_built_in_ones():
    """A rig's calibrated bottles: here one bottle drifted and was renamed C#5."""
    data = instrument("bottles-v1").model_dump(mode="json", by_alias=True, exclude_none=True)
    data["notes"][0] = {"name": "C#5", "hz": 554.37}
    calibrated = Instrument.model_validate(data)
    in_use = {"bottles-v1": calibrated}
    assert performer(PLAYABLE, "robot", in_use).instrument == calibrated
    assert score_problems(PLAYABLE)["robot"] == []
    assert "no bottle for C5" in score_problems(PLAYABLE, in_use)["robot"][0]


def test_a_performer_the_instrument_cannot_have_is_refused():
    data = PLAYABLE.to_dict()
    data["parts"]["robot"]["performer"] = "human"  # nobody plays bottles by hand yet
    with pytest.raises(LineUpError, match="cannot be played by a human"):
        performers(PLAYABLE.revised({"parts": data["parts"]}))
