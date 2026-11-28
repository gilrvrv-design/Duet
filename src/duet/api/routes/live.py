"""Live practice on a rig, started from its page (docs/device-api.md, "Practice"): the
server plays a library duet on the rig while it listens to the pianist."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from duet.api.context import Ctx
from duet.api.errors import Problem
from duet.performers import in_use, repair_bots
from duet.profile import keyboard_profile, robot_profile

router = APIRouter()


class PracticeIn(BaseModel):
    duet_id: str
    rig: str = Field(pattern=r"^(ws|tcp)://[^\s/]+:\d+$")  # the rig's link, as its page says
    profile: str = Field(min_length=1, max_length=64)  # the rig's carriage instrument
    mode: Literal["play", "wait", "follow"]
    input: str | None = None  # how the server hears the pianist (GET /v1/live/inputs)


@router.get("/v1/live/inputs")
def live_inputs(ctx: Ctx):
    return {"inputs": list(ctx.live.inputs)}


@router.post("/v1/live", status_code=201)
def start_practice(ctx: Ctx, practice: PracticeIn):
    score = ctx.store.get("duet", practice.duet_id).data
    try:
        robot = robot_profile(practice.profile)
    except (KeyError, TypeError) as exc:
        raise Problem("LIVE_INVALID", f"no carriage instrument {practice.profile!r}") from exc
    playing = in_use(robot, keyboard_profile())
    started = ctx.live.start(
        repair_bots(score, playing).score,
        practice.rig,
        robot,
        playing,
        practice.mode,
        practice.input,
    )
    return started.view()


@router.get("/v1/live/{practice_id}")
def get_practice(ctx: Ctx, practice_id: str):
    return _practice(ctx, practice_id).view()


@router.post("/v1/live/{practice_id}/stop")
def stop_practice(ctx: Ctx, practice_id: str):
    _practice(ctx, practice_id)
    return ctx.live.stop(practice_id).view()


def _practice(ctx: Ctx, practice_id: str):
    try:
        return ctx.live.get(practice_id)
    except KeyError as exc:
        raise Problem("NOT_FOUND", f"no practice {practice_id!r}") from exc
