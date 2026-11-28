"""Compose a duet: ask the composer, check, give feedback, repeat, then repair (spec FR-C4).

The composer is anything with a ``write(system, messages) -> str`` method, so tests use
a scripted fake and production uses Claude (see :mod:`duet.compose.claude`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from duet.compose.draft import DraftError, draft_to_score, score_to_draft
from duet.compose.prompts import feedback_message, request_message, system_prompt
from duet.copyright import CopyrightGuard
from duet.difficulty import level_problems
from duet.performers import human_difficulty, in_use, repair_bots, score_problems
from duet.pitch import midi_to_name
from duet.profile import KeyboardProfile, RobotProfile, keyboard_profile, robot_profile
from duet.progress import Progress, no_progress
from duet.repair import Change
from duet.score import DuetScore, Duo, Level, PerformerKind, Tempo

MAX_FEEDBACK_ROUNDS = 3


class Composer(Protocol):
    def write(self, system: str, messages: list[dict]) -> str:
        """Return the composer's answer (draft JSON text) to the conversation."""
        ...


class CompositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str = Field(min_length=1, max_length=2000)
    difficulty: Level = 2
    bars: int = Field(8, ge=1, le=64)
    lead: PerformerKind = "bot"  # who has the melody
    pianist_range: tuple[str, str] = ("C4", "C5")
    tempo_bpm: Tempo | None = None
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
        return human_difficulty(self.score)


class CompositionError(Exception):
    """The composer answered, but no acceptable duet came out of it."""


class ComposerError(Exception):
    """The composer itself failed: unreachable, refused, or answered badly."""


def compose(
    request: CompositionRequest,
    composer: Composer,
    robot: RobotProfile | None = None,
    keyboard: KeyboardProfile | None = None,
    max_rounds: int = MAX_FEEDBACK_ROUNDS,
    progress: Progress = no_progress,
    guard: CopyrightGuard | None = None,
) -> CompositionResult:
    """``guard``: an optional copyright guard; its problems are fed back too (FR-C5)."""
    robot, keyboard = robot or robot_profile(), keyboard or keyboard_profile()
    talk = _Conversation(request, composer, robot, keyboard, guard, progress, max_rounds)
    return talk.run(_request_text(request))


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
    guard: CopyrightGuard | None = None,
) -> CompositionResult:
    """Change an existing duet as asked (spec FR-C8): the composer edits the current
    draft instead of starting again, and the result is checked like a new composition."""
    robot = robot or robot_profile()
    keyboard = keyboard or keyboard_profile()
    pianist_range = score.parts[score.part_played_by("human")].range or (
        keyboard.low,
        keyboard.high,
    )
    request = CompositionRequest(
        prompt=score.meta.prompt or score.meta.title,
        difficulty=difficulty or score.meta.difficulty_target or human_difficulty(score),
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
    talk = _Conversation(request, composer, robot, keyboard, guard, progress, max_rounds)
    return talk.run(text)


@dataclass
class _Conversation:
    """Ask the composer, check its draft, feed the problems back, repeat; then, if it
    never gets there, repair its best draft deterministically."""

    request: CompositionRequest
    composer: Composer
    robot: RobotProfile
    keyboard: KeyboardProfile
    guard: CopyrightGuard | None
    progress: Progress
    max_rounds: int

    def run(self, first_message: str) -> CompositionResult:
        messages: list[dict] = [{"role": "user", "content": first_message}]
        best: tuple[DuetScore, str] | None = None
        history: list[list[str]] = []
        total = self.max_rounds + 1  # the first draft, then the feedback rounds
        for round_no in range(1, total + 1):
            stage = "drafting" if round_no == 1 else f"revising:{round_no}"
            self.progress(stage, (round_no - 1) / total)
            text = self.composer.write(system_prompt(self.robot), messages)
            self.progress("checking", (round_no - 0.5) / total)
            messages.append({"role": "assistant", "content": text})
            draft, problems = self._check(text)
            if draft is not None:
                best = draft
                if not problems:
                    self.progress("ready", 1.0)
                    return CompositionResult(*draft, round_no, history)
                messages[-1]["content"] = score_to_draft(*draft)
            history.append(problems)
            if round_no < total:
                messages.append({"role": "user", "content": feedback_message(problems)})
        return self._last_resort(best, history)

    def _check(self, text: str) -> tuple[tuple[DuetScore, str] | None, list[str]]:
        """The draft read from the composer's answer (None if it is not one), and its
        problems: what the performers cannot play, and protected melodies."""
        try:
            score, explanation = draft_to_score(
                text,
                prompt=self.request.prompt,
                difficulty=self.request.difficulty,
                pianist_range=self.request.pianist_range,
                duo=_duo(self.robot, self.keyboard),
            )
        except DraftError as exc:
            return None, [str(exc)]
        found = score_problems(score, in_use(self.robot, self.keyboard)).values()
        problems = [p for part_problems in found for p in part_problems]
        if self.guard is not None:
            problems += self.guard.check(score).problems()
        return (score, explanation), problems

    def _last_resort(self, best, history: list[list[str]]) -> CompositionResult:
        if best is None:
            raise CompositionError(
                "the composer never produced a valid score:\n" + "\n".join(history[-1])
            )
        self.progress("repairing", None)
        result = _finish(best, self.robot, self.keyboard, self.max_rounds + 1, history)
        if self.guard is not None and self.guard.check(result.score).status == "protected":
            # Repair fixes physics, not authorship: never hand back a copied melody.
            raise CompositionError("the composer kept copying a protected melody")
        self.progress("ready", 1.0)
        return result


def _duo(robot: RobotProfile, keyboard: KeyboardProfile) -> Duo:
    """The line-up a composition is for: the rig's two parts, on these instruments."""
    return Duo(bot_instrument=robot.id, human_instrument=keyboard.id)


def _finish(best, robot, keyboard, rounds: int, history) -> CompositionResult:
    """Deterministic last resort: repair the bot's part, drop the person's notes that are
    off the keyboard or out of their range."""
    score, explanation = best
    repaired = repair_bots(score, in_use(robot, keyboard))
    score = repaired.score
    human = score.part_played_by("human")
    low, high = score.parts[human].range or (keyboard.low, keyboard.high)
    keep = [
        e
        for e in score.events
        if e.part != human or (keyboard.contains(e.pitch) and low <= e.pitch <= high)
    ]
    warnings = []
    if len(keep) < len(score.events):
        warnings.append(f"dropped {len(score.events) - len(keep)} {human} note(s) out of range")
        score = score.with_events(keep)
    if level := score.meta.difficulty_target:
        warnings += level_problems(score, part=human, level=level)
    return CompositionResult(score, explanation, rounds, history, repaired.changes, warnings)
