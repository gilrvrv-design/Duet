"""FastAPI application: duets, compositions and transcriptions (spec §6.1).

Errors use RFC 9457 problem details with stable codes (spec §6.3).
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError

from duet import __version__
from duet.api.store import MemoryStore, NotFound
from duet.compose import CompositionRequest, compose
from duet.compose.service import Composer, CompositionError
from duet.difficulty import check_pianist, pianist_difficulty
from duet.feasibility import check_robot
from duet.kinematics import reachability
from duet.midi_io import midi_to_score, score_to_midi_bytes
from duet.profile import keyboard_profile, robot_profile
from duet.repair import repair_robot
from duet.score import DuetScore

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MIDI = "audio/midi"


class Problem(Exception):
    def __init__(self, status: int, code: str, detail: str):
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


class ArrangementOptions(BaseModel):
    difficulty: int = Field(1, ge=1, le=5)
    title: str | None = None


def duet_view(record) -> dict:
    score: DuetScore = record.data
    robot = robot_profile(score.parts["robot"].instrument_profile)
    report = check_robot(score, robot)
    return {
        "id": record.id,
        "score": score.to_dict(),
        "bars": score.bar_count,
        "pianist_difficulty": pianist_difficulty(score),
        "robot_playable": report.ok,
        "robot_problems": report.feedback().splitlines(),
        "pianist_problems": check_pianist(score, keyboard_profile()),
        **record.meta,
    }


def create_app(
    composer_factory: Callable[[], Composer] | None = None, store: MemoryStore | None = None
) -> FastAPI:
    app = FastAPI(title="Duet", version=__version__)
    store = store or MemoryStore()
    app.state.store = store

    def get_composer() -> Composer:
        if composer_factory is not None:
            return composer_factory()
        from duet.compose.claude import ClaudeComposer

        return ClaudeComposer()

    @app.exception_handler(Problem)
    async def _problem(_: Request, exc: Problem):
        return JSONResponse(
            {
                "type": f"https://duet.dev/problems/{exc.code}",
                "title": exc.code,
                "status": exc.status,
                "detail": exc.detail,
                "code": exc.code,
            },
            status_code=exc.status,
            media_type="application/problem+json",
        )

    @app.exception_handler(NotFound)
    async def _not_found(request: Request, exc: NotFound):
        return await _problem(request, Problem(404, "NOT_FOUND", str(exc.args[0])))

    @app.get("/v1/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/v1/profiles/{profile_id}/reachability")
    def profile_reachability(profile_id: str):
        try:
            robot = robot_profile(profile_id)
        except (KeyError, TypeError) as exc:
            raise Problem(404, "NOT_FOUND", str(exc)) from exc
        matrix = reachability(robot)
        return {"pitches": list(matrix.pitches), "min_interval_s": matrix.seconds}

    # Duets -------------------------------------------------------------------
    @app.post("/v1/duets", status_code=201)
    def create_duet(score: dict):
        try:
            parsed = DuetScore.model_validate(score)
        except ValidationError as exc:
            raise Problem(422, "SCORE_INVALID", str(exc)) from exc
        return duet_view(store.add("duet", parsed, source="json"))

    @app.post("/v1/duets/import", status_code=201)
    async def import_midi(file: Annotated[UploadFile, File()]):
        data = await _read_upload(file)
        try:
            score = midi_to_score(data, title=Path(file.filename or "imported").stem)
        except (OSError, EOFError, ValueError) as exc:
            raise Problem(422, "MIDI_INVALID", f"cannot read MIDI: {exc}") from exc
        return duet_view(store.add("duet", score, source="midi"))

    @app.get("/v1/duets/{duet_id}")
    def get_duet(duet_id: str):
        return duet_view(store.get("duet", duet_id))

    @app.delete("/v1/duets/{duet_id}", status_code=204)
    def delete_duet(duet_id: str):
        store.delete("duet", duet_id)
        return Response(status_code=204)

    @app.get("/v1/duets/{duet_id}/midi")
    def duet_midi(duet_id: str):
        score = store.get("duet", duet_id).data
        return Response(score_to_midi_bytes(score), media_type=MIDI)

    @app.post("/v1/duets/{duet_id}/repair", status_code=201)
    def repair_duet(duet_id: str):
        score = store.get("duet", duet_id).data
        result = repair_robot(score, robot_profile(score.parts["robot"].instrument_profile))
        record = store.add("duet", result.score, source="repair", parent=duet_id)
        return {**duet_view(record), "changes": result.summary().splitlines()}

    # Compositions ------------------------------------------------------------
    @app.post("/v1/compositions", status_code=201)
    def create_composition(request: CompositionRequest):
        try:
            result = compose(request, get_composer())
        except CompositionError as exc:
            raise Problem(502, "COMPOSITION_FAILED", str(exc)) from exc
        except RuntimeError as exc:
            raise Problem(502, "LLM_ERROR", str(exc)) from exc
        record = store.add(
            "duet",
            result.score,
            source="composition",
            explanation=result.explanation,
            rounds=result.rounds,
            repairs=[f"{c.kind}: bar {c.bar} beat {c.beat:g}: {c.detail}" for c in result.repairs],
            warnings=result.warnings,
        )
        return duet_view(record)

    # Transcriptions ----------------------------------------------------------
    @app.post("/v1/transcriptions", status_code=201)
    async def create_transcription(
        file: Annotated[UploadFile, File()],
        rights_confirmed: Annotated[bool, Form()],
        route: Annotated[Literal["auto", "melody"], Form()] = "auto",
    ):
        if not rights_confirmed:
            raise Problem(
                422, "RIGHTS_NOT_CONFIRMED", "confirm you have the right to use this audio"
            )
        from duet.audio.io import AudioError
        from duet.audio.pipeline import transcribe_file

        data = await _read_upload(file)
        suffix = Path(file.filename or "upload.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:  # audio is not kept (FR-A10)
            tmp.write(data)
            tmp.flush()
            try:
                result = transcribe_file(tmp.name)
            except AudioError as exc:
                raise Problem(422, "AUDIO_INVALID", str(exc)) from exc
        record = store.add("transcription", result, filename=file.filename)
        return _transcription_view(record)

    @app.get("/v1/transcriptions/{tid}")
    def get_transcription(tid: str):
        return _transcription_view(store.get("transcription", tid))

    @app.get("/v1/transcriptions/{tid}/midi")
    def transcription_midi(tid: str, quantize: float = 1.0):
        import io

        from duet.audio.pipeline import transcription_to_midi

        buffer = io.BytesIO()
        transcription_to_midi(store.get("transcription", tid).data, strength=quantize).save(
            file=buffer
        )
        return Response(buffer.getvalue(), media_type=MIDI)

    @app.post("/v1/transcriptions/{tid}/arrangements", status_code=201)
    def create_arrangement(tid: str, options: ArrangementOptions | None = None):
        from duet.audio.arranger import arrange

        options = options or ArrangementOptions()
        record = store.get("transcription", tid)
        title = options.title or Path(record.meta.get("filename") or "Transcribed duet").stem
        arrangement = arrange(record.data, difficulty=options.difficulty, title=title)
        duet = store.add(
            "duet",
            arrangement.score,
            source="transcription",
            transcription=tid,
            transpose=arrangement.transpose,
            coverage_before=arrangement.coverage_before,
            coverage_after=arrangement.coverage_after,
            chords=arrangement.chords,
            retuning=[r.advice() for r in arrangement.retuning],
        )
        return duet_view(duet)

    return app


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise Problem(413, "FILE_TOO_LARGE", "uploads are limited to 200 MB")
    if not data:
        raise Problem(422, "FILE_EMPTY", "the uploaded file is empty")
    return data


def _transcription_view(record) -> dict:
    t = record.data
    return {
        "id": record.id,
        "filename": record.meta.get("filename"),
        "model": t.model,
        "route": t.route,
        "tempo_bpm": t.tempo_bpm,
        "key": t.key,
        "duration_s": t.duration_s,
        "notes": len(t.notes),
        "warnings": t.warnings,
    }
