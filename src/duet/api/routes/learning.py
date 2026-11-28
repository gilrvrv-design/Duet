"""Performances, skills and lessons (spec §5.8)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from duet import learning
from duet.api.context import Ctx, UserId
from duet.api.routes.compositions import run_composition
from duet.api.views import lesson_view, skills_view
from duet.compose import CompositionRequest
from duet.learning import USER_PATTERN
from duet.listening import PlayedNote, Report, grade_take
from duet.score import DuetScore, Level
from duet.storage import Store

router = APIRouter()

MAX_TAKE_NOTES = 20_000  # about 40 minutes of fast playing
MAX_TAKE_MS = 86_400_000  # a day


class PlayedIn(BaseModel):
    t_ms: float = Field(ge=0, le=MAX_TAKE_MS)
    pitch: int = Field(ge=0, le=127)
    velocity: int = Field(80, ge=1, le=127)


class Take(BaseModel):
    """What the pianist played, e.g. recorded by the app from a MIDI keyboard."""

    played: list[PlayedIn] = Field(max_length=MAX_TAKE_NOTES)
    user: str | None = Field(None, pattern=USER_PATTERN)


class PerformanceIn(Take):
    duet_id: str


class NextRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    bars: int = Field(8, ge=1, le=64)


class LessonOptions(BaseModel):
    target_level: Level = 3
    user: str | None = Field(None, pattern=USER_PATTERN)


def graded(score: DuetScore, take: Take) -> tuple[Report, dict]:
    played = [PlayedNote(round(p.t_ms * 1000), p.pitch, p.velocity) for p in take.played]
    report = grade_take(score, played, score.part_played_by("human"))
    return report, {
        "accuracy": round(report.accuracy, 3),
        "results": [g.result for g in report.grades],
        "hardest_bars": report.hardest_bars(),
        "feedback": report.feedback(),
    }


def learned(store: Store, user: str | None, score: DuetScore, report: Report) -> dict:
    if user is None:
        return {}
    model, newly = learning.learn(store, user, score, report)
    return {"newly_mastered": newly, **skills_view(model)}


@router.post("/v1/users/{user}/performances", status_code=201)
def add_performance(ctx: Ctx, user: UserId, body: PerformanceIn):
    score = ctx.store.get("duet", body.duet_id).data
    report, view = graded(score, body)
    return {**view, **learned(ctx.store, user, score, report)}


@router.get("/v1/users/{user}/skills")
def get_skills(ctx: Ctx, user: UserId):
    return skills_view(learning.skill_model(ctx.store, user))


@router.post("/v1/users/{user}/compositions", status_code=201)
def compose_next(ctx: Ctx, user: UserId, body: NextRequest, background: bool = False):
    difficulty, focus = learning.skill_model(ctx.store, user).next_request()
    request = CompositionRequest(
        prompt=body.prompt, bars=body.bars, difficulty=difficulty, focus=focus
    )
    return ctx.run_or_submit("composition", lambda p: run_composition(ctx, request, p), background)


@router.post("/v1/transcriptions/{tid}/lessons", status_code=201)
def create_lesson(ctx: Ctx, tid: str, options: LessonOptions | None = None):
    options = options or LessonOptions()
    return lesson_view(learning.create_lesson(ctx.store, tid, options.target_level, options.user))


@router.get("/v1/lessons/{lesson_id}")
def get_lesson(ctx: Ctx, lesson_id: str):
    return lesson_view(ctx.store.get("lesson", lesson_id))


@router.post("/v1/lessons/{lesson_id}/steps/{n}/attempts", status_code=201)
def attempt_step(ctx: Ctx, lesson_id: str, n: int, take: Take):
    steps = ctx.store.get("lesson", lesson_id).data["steps"]
    if not 0 <= n < len(steps):
        from duet.storage import NotFound

        raise NotFound(f"lesson {lesson_id} has no step {n}")
    score = ctx.store.get("duet", steps[n]["duet_id"]).data
    report, view = graded(score, take)
    lesson = learning.record_attempt(ctx.store, lesson_id, n, report)
    user = take.user or lesson.data.get("user")
    return {
        **view,
        "passed": lesson.data["steps"][n]["passed"],
        "lesson": lesson_view(lesson),
        **learned(ctx.store, user, score, report),
    }
