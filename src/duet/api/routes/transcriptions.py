"""Audio to MIDI (spec §5.10) and arrangements of what was heard."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from duet.api.context import AppContext, Ctx, read_upload
from duet.api.errors import Problem
from duet.api.views import duet_view, transcription_view
from duet.library import add_duet
from duet.progress import Progress
from duet.score import Level

router = APIRouter()
Route = Literal["auto", "melody", "full"]


class ArrangementOptions(BaseModel):
    difficulty: Level = 1
    title: str | None = Field(None, max_length=200)


def run_transcription(
    ctx: AppContext, path: str, filename: str | None, route: Route, progress: Progress
) -> dict:
    from duet.audio.fullmix import RouteUnavailable, SeparationFailed
    from duet.audio.io import AudioError
    from duet.audio.pipeline import transcribe_file

    try:
        result = transcribe_file(path, route=route, progress=progress)
    except AudioError as exc:
        raise Problem("AUDIO_INVALID", str(exc)) from exc
    except RouteUnavailable as exc:
        raise Problem("ROUTE_UNAVAILABLE", str(exc)) from exc
    except SeparationFailed as exc:
        raise Problem("SEPARATION_FAILED", str(exc)) from exc
    finally:
        Path(path).unlink(missing_ok=True)  # audio is not kept (FR-A10)
    return transcription_view(ctx.store.add("transcription", result, filename=filename))


@router.post("/v1/transcriptions", status_code=201)
async def create_transcription(
    ctx: Ctx,
    file: Annotated[UploadFile, File()],
    rights_confirmed: Annotated[bool, Form()],
    route: Annotated[Route, Form()] = "auto",
    background: bool = False,
):
    if not rights_confirmed:
        raise Problem("RIGHTS_NOT_CONFIRMED", "confirm you have the right to use this audio")
    data = await read_upload(file)
    suffix = Path(file.filename or "upload.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)

    def work(progress: Progress) -> dict:
        return run_transcription(ctx, tmp.name, file.filename, route, progress)

    if background:
        return ctx.run_or_submit("transcription", work, background=True)
    from fastapi.concurrency import run_in_threadpool

    # Transcription takes seconds to minutes: keep it off the event loop.
    return await run_in_threadpool(ctx.run_or_submit, "transcription", work, False)


@router.get("/v1/transcriptions/{tid}")
def get_transcription(ctx: Ctx, tid: str):
    return transcription_view(ctx.store.get("transcription", tid))


@router.get("/v1/transcriptions/{tid}/midi")
def transcription_midi(ctx: Ctx, tid: str, quantize: Annotated[float, Query(ge=0, le=1)] = 1.0):
    from duet.audio.pipeline import transcription_to_midi

    buffer = io.BytesIO()
    transcription_to_midi(ctx.store.get("transcription", tid).data, strength=quantize).save(
        file=buffer
    )
    return Response(buffer.getvalue(), media_type="audio/midi")


@router.post("/v1/transcriptions/{tid}/arrangements", status_code=201)
def create_arrangement(ctx: Ctx, tid: str, options: ArrangementOptions | None = None):
    from duet.audio.arranger import arrange

    options = options or ArrangementOptions()
    record = ctx.store.get("transcription", tid)
    title = options.title or Path(record.meta.get("filename") or "Transcribed duet").stem
    arrangement = arrange(record.data, difficulty=options.difficulty, title=title)
    duet = add_duet(
        ctx.store,
        arrangement.score,
        source="transcription",
        transcription=tid,
        transpose=arrangement.transpose,
        coverage_before=arrangement.coverage_before,
        coverage_after=arrangement.coverage_after,
        chords=arrangement.chords,
        retuning=[r.advice() for r in arrangement.retuning],
    )
    return duet_view(duet, ctx.guard)
