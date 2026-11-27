"""Compose a duet: ask the composer, check, give feedback, repeat, then repair (spec FR-C4).

The composer is anything with a ``write(system, messages) -> str`` method, so tests use
a scripted fake and production uses Claude (see :mod:`duet.compose.claude`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from duet.compose.draft import DraftError, draft_to_score, score_to_draft
from duet.compose.prompts import feedback_message, request_message, system_prompt
from duet.difficulty import check_pianist, pianist_difficulty
from duet.feasibility import check_robot
from duet.pitch import midi_to_name
from duet.profile import KeyboardProfile, RobotProfile, keyboard_profile, robot_profile
from duet.progress import Progress, no_progress
from duet.repair import Change, repair_robot
from duet.score import DuetScore

MAX_FEEDBACK_ROUNDS = 3


class Composer(Protocol):
    def write(self, system: str, messages: list[dict]) -> str:
        """Return the composer's answer (draft JSON text) to the conversation."""
        ...


class CompositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str = Field(min_length=1, max_length=2000)
    difficulty: int = Field(2, ge=1, le=5)
    bars: int = Field(8, ge=1, le=64)
    lead: Literal["robot", "pianist"] = "robot"
    pianist_range: tuple[str, str] = ("C4", "C5")
    tempo_bpm: float | None = Field(None, gt=20, le=300)
    time_signature: tuple[int, int] | None = None
    focus: str | None = Field(None, max_length=200)  # what the pianist should practise


@dataclass
class CompositionResult:
    score: DuetScore
    explanation: str
    rounds: int
    feedback: list[list[str]] = field(default_factory=list)
    repairs: list[Change] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def difficulty(self) -> int:
        return pianist_difficulty(self.score)


class CompositionError(RuntimeError):
    pass


def compose(
    request: CompositionRequest,
    composer: Composer,
    robot: RobotProfile | None = None,
    keyboard: KeyboardProfile | None = None,
    max_rounds: int = MAX_FEEDBACK_ROUNDS,
    progress: Progress = no_progress,
    guard=None,
) -> CompositionResult:
    """``guard``: an optional copyright guard; its problems are fed back too (FR-C5)."""
    robot = robot or robot_profile()
    keyboard = keyboard or keyboard_profile()
    return _converse(
        request, _request_text(request), composer, robot, keyboard, max_rounds, progress, guard
    )


def _request_text(request: CompositionRequest) -> str:
    return request_message(
        request.prompt,
        difficulty=request.difficulty,
        bars=request.bars,
        lead=request.lead,
        pianist_range=request.pianist_range,
        tempo_bpm=request.tempo_bpm,
        time_signature=request.time_signature,
        focus=request.focus,
    )


def revise(
    score: DuetScore,
    instruction: str,
    composer: Composer,
    robot: RobotProfile | None = None,
    keyboard: KeyboardProfile | None = None,
    difficulty: int | None = None,
    max_rounds: int = MAX_FEEDBACK_ROUNDS,
    progress: Progress = no_progress,
) -> CompositionResult:
    """Change an existing duet as asked (spec FR-C8): the composer edits the current
    draft instead of starting again, and the result is checked like a new composition."""
    robot = robot or robot_profile()
    keyboard = keyboard or keyboard_profile()
    pianist_range = score.parts["pianist"].range or (keyboard.low, keyboard.high)
    request = CompositionRequest(
        prompt=score.meta.prompt or score.meta.title,
        difficulty=difficulty or score.meta.difficulty_target or pianist_difficulty(score),
        bars=max(1, score.bar_count),
        pianist_range=tuple(midi_to_name(p) for p in pianist_range),
        tempo_bpm=score.meta.tempo_bpm,
        time_signature=score.meta.time_signature,
    )
    text = (
        f"{_request_text(request)}\n\nHere is the current duet:\n{score_to_draft(score)}\n\n"
        f"Change it: {instruction}. Keep everything you are not asked to change. "
        "Answer with the full JSON object."
    )
    return _converse(request, text, composer, robot, keyboard, max_rounds, progress)


def _converse(request, first_message, composer, robot, keyboard, max_rounds, progress, guard=None):
    """Ask, check, feed problems back, repeat; then repair deterministically."""
    system = system_prompt(robot)
    messages: list[dict] = [{"role": "user", "content": first_message}]
    best: tuple[DuetScore, str] | None = None
    history: list[list[str]] = []
    for round_no in range(1, max_rounds + 2):  # first draft plus feedback rounds
        total = max_rounds + 1
        progress("drafting" if round_no == 1 else f"revising:{round_no}", (round_no - 1) / total)
        text = composer.write(system, messages)
        progress("checking", (round_no - 0.5) / total)
        messages.append({"role": "assistant", "content": text})
        try:
            score, explanation = draft_to_score(
                text,
                prompt=request.prompt,
                difficulty=request.difficulty,
                pianist_range=request.pianist_range,
            )
        except DraftError as exc:
            problems = [str(exc)]
        else:
            best = (score, explanation)
            problems = check_robot(score, robot).feedback().splitlines()
            problems += check_pianist(score, keyboard)
            if guard is not None:
                problems += guard.check(score).problems()
            if not problems:
                progress("ready", 1.0)
                return CompositionResult(score, explanation, round_no, history)
            messages[-1]["content"] = score_to_draft(score, explanation)
        history.append(problems)
        if round_no <= max_rounds:
            messages.append({"role": "user", "content": feedback_message(problems)})
    if best is None:
        raise CompositionError(
            "the composer never produced a valid score:\n" + "\n".join(history[-1])
        )
    progress("repairing", None)
    result = _finish(best, robot, keyboard, rounds=max_rounds + 1, history=history)
    if guard is not None and guard.check(result.score).status == "protected":
        # Repair fixes physics, not authorship: never hand back a copied melody.
        raise CompositionError("the composer kept copying a protected melody")
    progress("ready", 1.0)
    return result


def _finish(best, robot, keyboard, rounds, history) -> CompositionResult:
    """Deterministic last resort: repair the robot part, drop unplayable pianist notes."""
    score, explanation = best
    repaired = repair_robot(score, robot)
    score = repaired.score
    low, high = score.parts["pianist"].range or (keyboard.low, keyboard.high)
    keep = [
        e
        for e in score.events
        if e.part == "robot" or (keyboard.contains(e.pitch) and low <= e.pitch <= high)
    ]
    warnings = []
    if len(keep) < len(score.events):
        warnings.append(f"dropped {len(score.events) - len(keep)} pianist note(s) out of range")
        score = score.with_events(keep)
    warnings += [p for p in check_pianist(score, keyboard) if p.startswith("too hard")]
    return CompositionResult(score, explanation, rounds, history, repaired.changes, warnings)
