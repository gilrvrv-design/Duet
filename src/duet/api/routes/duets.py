"""Duets and the library (spec §5.9)."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError

from duet import library
from duet.api.context import Ctx, read_upload
from duet.api.errors import Problem
from duet.api.views import duet_view, summary_view
from duet.compose.service import ComposerError, CompositionError, revise
from duet.jobs import JobFailure
from duet.midi_io import midi_to_score, score_to_midi_bytes
from duet.profile import robot_profile
from duet.repair import repair_robot
from duet.score import MAX_LEVEL, MIN_LEVEL, DuetScore
from duet.variations import VariationError, is_built_in, vary

router = APIRouter()
MIDI = "audio/midi"


class VariationIn(BaseModel):
    instruction: str = Field(min_length=1, max_length=500)


class PublishIn(BaseModel):
    own_work: bool = False  # the user wrote this music or holds the rights


@router.get("/v1/duets")
def search_duets(
    ctx: Ctx,
    q: Annotated[str, Query(max_length=200)] = "",
    difficulty: Annotated[int | None, Query(ge=MIN_LEVEL, le=MAX_LEVEL)] = None,
    max_bars: Annotated[int | None, Query(ge=1)] = None,
    featured: bool | None = None,
    public: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    found = library.search(ctx.store, q, difficulty, max_bars, featured, public, limit)
    return [summary_view(r) for r in found]


@router.post("/v1/duets", status_code=201)
def create_duet(ctx: Ctx, score: dict):
    try:
        parsed = DuetScore.model_validate(score)
    except ValidationError as exc:
        raise Problem("SCORE_INVALID", str(exc)) from exc
    return duet_view(library.add_duet(ctx.store, parsed, source="json"), ctx.guard)


@router.post("/v1/duets/import", status_code=201)
async def import_midi(ctx: Ctx, file: Annotated[UploadFile, File()]):
    data = await read_upload(file)
    title = Path(file.filename or "imported").stem

    def work():
        try:
            score = midi_to_score(data, title=title)
        except (OSError, EOFError, ValueError) as exc:
            raise Problem("MIDI_INVALID", f"cannot read MIDI: {exc}") from exc
        return duet_view(library.add_duet(ctx.store, score, source="midi"), ctx.guard)

    return await run_in_threadpool(work)  # parsing must not block other requests


@router.get("/v1/duets/{duet_id}")
def get_duet(ctx: Ctx, duet_id: str):
    return duet_view(ctx.store.get("duet", duet_id), ctx.guard)


@router.delete("/v1/duets/{duet_id}", status_code=204)
def delete_duet(ctx: Ctx, duet_id: str):
    ctx.store.delete("duet", duet_id)
    return Response(status_code=204)


@router.get("/v1/duets/{duet_id}/midi")
def duet_midi(ctx: Ctx, duet_id: str):
    return Response(score_to_midi_bytes(ctx.store.get("duet", duet_id).data), media_type=MIDI)


@router.post("/v1/duets/{duet_id}/repair", status_code=201)
def repair_duet(ctx: Ctx, duet_id: str):
    score = ctx.store.get("duet", duet_id).data
    result = repair_robot(score, robot_profile(score.parts["robot"].instrument_profile))
    record = library.add_version(ctx.store, duet_id, result.score, source="repair")
    return {**duet_view(record, ctx.guard), "changes": result.summary().splitlines()}


@router.post("/v1/duets/{duet_id}/variations", status_code=201)
def create_variation(ctx: Ctx, duet_id: str, body: VariationIn, background: bool = False):
    parent = ctx.store.get("duet", duet_id)

    def work(progress):
        edit = None
        if not is_built_in(body.instruction):
            edit = partial(revise, composer=ctx.composer_factory(), guard=ctx.guard)
        try:
            score, note = vary(parent.data, body.instruction, edit=edit)
        except VariationError as exc:
            raise JobFailure("VARIATION_INVALID", str(exc)) from exc
        except CompositionError as exc:
            raise JobFailure("COMPOSITION_FAILED", str(exc)) from exc
        except ComposerError as exc:
            raise JobFailure("LLM_ERROR", str(exc)) from exc
        record = library.add_version(
            ctx.store, duet_id, score, source="variation", instruction=body.instruction, change=note
        )
        return duet_view(record, ctx.guard)

    return ctx.run_or_submit("variation", work, background)


@router.get("/v1/duets/{duet_id}/versions")
def duet_versions(ctx: Ctx, duet_id: str):
    return [summary_view(r) for r in library.versions(ctx.store, duet_id)]


@router.post("/v1/duets/{duet_id}/publish")
def publish_duet(ctx: Ctx, duet_id: str, body: PublishIn | None = None):
    """Make a duet public (spec FR-B2, FR-C5, FR-A11)."""
    body = body or PublishIn()
    record = ctx.store.get("duet", duet_id)
    status = ctx.guard.check(record.data).status
    if status == "protected" and not body.own_work:
        raise Problem("COPYRIGHT_MATCH", "this melody matches a protected work")
    from_recording = record.meta.get("source") == "transcription"
    if from_recording and status != "public_domain" and not body.own_work:
        raise Problem(
            "RIGHTS_NOT_CONFIRMED",
            "arrangements of recordings can be shared only as your own work or a "
            "public-domain tune",
        )
    record = ctx.store.update_meta("duet", duet_id, visibility="public", own_work=body.own_work)
    return duet_view(record, ctx.guard)


@router.post("/v1/duets/{duet_id}/fork", status_code=201)
def fork_duet(ctx: Ctx, duet_id: str):
    original = ctx.store.get("duet", duet_id)
    record = library.add_duet(ctx.store, original.data, source="fork", forked_from=duet_id)
    return duet_view(record, ctx.guard)
