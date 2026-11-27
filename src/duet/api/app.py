"""FastAPI application: duets, compositions and transcriptions (spec §6.1).

Errors use RFC 9457 problem details with stable codes (spec §6.3).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError

from duet import __version__
from duet.api.store import NotFound, Store, store_from_env
from duet.compose import CompositionRequest, compose
from duet.compose.service import Composer, CompositionError
from duet.difficulty import check_pianist, pianist_difficulty
from duet.feasibility import check_robot
from duet.jobs import TERMINAL, JobFailure, JobRunner, job_view
from duet.kinematics import reachability
from duet.listening import PlayedNote, grade_take
from duet.midi_io import midi_to_score, score_to_midi_bytes
from duet.pedagogy import PASS_ACCURACY, SkillModel, teach_song
from duet.profile import keyboard_profile, robot_profile
from duet.progress import Progress, no_progress
from duet.repair import repair_robot
from duet.score import DuetScore
from duet.variations import BUILT_IN, vary

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MIDI = "audio/midi"


class Problem(Exception):
    def __init__(self, status: int, code: str, detail: str):
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


class ArrangementOptions(BaseModel):
    difficulty: int = Field(1, ge=1, le=5)
    title: str | None = None


class PlayedIn(BaseModel):
    t_ms: float
    pitch: int = Field(ge=0, le=127)
    velocity: int = Field(80, ge=1, le=127)


class Take(BaseModel):
    """What the pianist played, e.g. recorded by the app from a MIDI keyboard."""

    played: list[PlayedIn]
    user: str | None = None


class PerformanceIn(Take):
    duet_id: str


class NextRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    bars: int = Field(8, ge=1, le=64)


class VariationIn(BaseModel):
    instruction: str = Field(min_length=1, max_length=500)


class LessonOptions(BaseModel):
    target_level: int = Field(3, ge=1, le=5)
    user: str | None = None


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
    composer_factory: Callable[[], Composer] | None = None, store: Store | None = None
) -> FastAPI:
    app = FastAPI(title="Duet", version=__version__)
    store = store or store_from_env(os.environ.get("DUET_DB"))
    app.state.store = store
    jobs = JobRunner(store)
    app.state.jobs = jobs

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

    # Library (spec §5.9) -----------------------------------------------------
    def add_duet(score: DuetScore, **meta):
        """Every duet starts its own line (root) at version 1 unless told otherwise."""
        record = store.add("duet", score, **meta)
        if "root" not in meta:
            store.update_meta("duet", record.id, root=record.id, version=1)
        return store.get("duet", record.id)

    def featured() -> None:
        examples = Path(__file__).resolve().parents[3] / "examples"
        if any(r.meta.get("featured") for r in store.list("duet")):
            return
        for path in sorted(examples.glob("*.json")) if examples.is_dir() else []:
            add_duet(
                DuetScore.model_validate_json(path.read_text()), source="example", featured=True
            )

    featured()

    @app.get("/v1/duets")
    def search_duets(
        q: str = "",
        difficulty: int | None = None,
        max_bars: int | None = None,
        featured: bool | None = None,
        limit: int = 20,
    ):
        words = [w for w in q.lower().split() if w]
        hits = []
        for record in store.list("duet"):
            score: DuetScore = record.data
            if difficulty is not None and pianist_difficulty(score) != difficulty:
                continue
            if max_bars is not None and score.bar_count > max_bars:
                continue
            if featured is not None and bool(record.meta.get("featured")) != featured:
                continue
            text = " ".join(
                [score.meta.title, score.meta.prompt or "", score.meta.key, *score.meta.style_tags]
            ).lower()
            matched = sum(w in text for w in words)
            if words and not matched:
                continue
            hits.append((matched, record.created_at, record))
        hits.sort(key=lambda h: (-h[0], -h[1]))
        return [summary_view(r) for _, _, r in hits[:limit]]

    @app.post("/v1/duets/{duet_id}/variations", status_code=201)
    def create_variation(duet_id: str, body: VariationIn, background: bool = False):
        parent = store.get("duet", duet_id)

        def work(progress):
            word = body.instruction.strip().lower()
            composer = None if word in BUILT_IN else get_composer()
            try:
                score, note = vary(parent.data, body.instruction, composer)
            except ValueError as exc:
                raise JobFailure("VARIATION_INVALID", str(exc)) from exc
            except RuntimeError as exc:
                raise JobFailure("LLM_ERROR", str(exc)) from exc
            record = add_duet(
                score,
                source="variation",
                parent=duet_id,
                instruction=body.instruction,
                change=note,
                root=parent.meta.get("root", duet_id),
                version=parent.meta.get("version", 1) + 1,
            )
            return duet_view(record)

        if background:
            return _accepted(jobs.submit("variation", work))
        return _sync(lambda: work(no_progress))

    @app.get("/v1/duets/{duet_id}/versions")
    def duet_versions(duet_id: str):
        root = store.get("duet", duet_id).meta.get("root", duet_id)
        line = [r for r in store.list("duet") if r.meta.get("root") == root]
        return [summary_view(r) for r in sorted(line, key=lambda r: r.meta.get("version", 1))]

    @app.post("/v1/duets/{duet_id}/fork", status_code=201)
    def fork_duet(duet_id: str):
        original = store.get("duet", duet_id)
        return duet_view(add_duet(original.data, source="fork", forked_from=duet_id))

    # Duets -------------------------------------------------------------------
    @app.post("/v1/duets", status_code=201)
    def create_duet(score: dict):
        try:
            parsed = DuetScore.model_validate(score)
        except ValidationError as exc:
            raise Problem(422, "SCORE_INVALID", str(exc)) from exc
        return duet_view(add_duet(parsed, source="json"))

    @app.post("/v1/duets/import", status_code=201)
    async def import_midi(file: Annotated[UploadFile, File()]):
        data = await _read_upload(file)
        try:
            score = midi_to_score(data, title=Path(file.filename or "imported").stem)
        except (OSError, EOFError, ValueError) as exc:
            raise Problem(422, "MIDI_INVALID", f"cannot read MIDI: {exc}") from exc
        return duet_view(add_duet(score, source="midi"))

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
        parent = store.get("duet", duet_id)
        record = add_duet(
            result.score,
            source="repair",
            parent=duet_id,
            root=parent.meta.get("root", duet_id),
            version=parent.meta.get("version", 1) + 1,
        )
        return {**duet_view(record), "changes": result.summary().splitlines()}

    # Compositions ------------------------------------------------------------
    def run_composition(request: CompositionRequest, progress: Progress) -> dict:
        try:
            result = compose(request, get_composer(), progress=progress)
        except CompositionError as exc:
            raise JobFailure("COMPOSITION_FAILED", str(exc)) from exc
        except RuntimeError as exc:
            raise JobFailure("LLM_ERROR", str(exc)) from exc
        record = add_duet(
            result.score,
            source="composition",
            explanation=result.explanation,
            rounds=result.rounds,
            repairs=[f"{c.kind}: bar {c.bar} beat {c.beat:g}: {c.detail}" for c in result.repairs],
            warnings=result.warnings,
        )
        return duet_view(record)

    @app.post("/v1/compositions", status_code=201)
    def create_composition(request: CompositionRequest, background: bool = False):
        if background:
            return _accepted(jobs.submit("composition", lambda p: run_composition(request, p)))
        return _sync(lambda: run_composition(request, no_progress))

    # Transcriptions ----------------------------------------------------------
    def run_transcription(path: str, filename: str | None, route: str, progress: Progress) -> dict:
        from duet.audio.io import AudioError
        from duet.audio.pipeline import transcribe_file

        try:
            result = transcribe_file(path, route=route, progress=progress)
        except AudioError as exc:
            raise JobFailure("AUDIO_INVALID", str(exc)) from exc
        except RuntimeError as exc:
            raise JobFailure("ROUTE_UNAVAILABLE", str(exc)) from exc
        finally:
            Path(path).unlink(missing_ok=True)  # audio is not kept (FR-A10)
        return _transcription_view(store.add("transcription", result, filename=filename))

    @app.post("/v1/transcriptions", status_code=201)
    async def create_transcription(
        file: Annotated[UploadFile, File()],
        rights_confirmed: Annotated[bool, Form()],
        route: Annotated[Literal["auto", "melody", "full"], Form()] = "auto",
        background: bool = False,
    ):
        if not rights_confirmed:
            raise Problem(
                422, "RIGHTS_NOT_CONFIRMED", "confirm you have the right to use this audio"
            )
        data = await _read_upload(file)
        suffix = Path(file.filename or "upload.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)

        def work(progress):
            return run_transcription(tmp.name, file.filename, route, progress)

        if background:
            return _accepted(jobs.submit("transcription", work))
        return _sync(lambda: work(no_progress))

    # Learning (spec §5.8) --------------------------------------------------
    def skill_model(user: str) -> SkillModel:
        try:
            return store.get("skills", user).data
        except NotFound:
            return SkillModel()

    def learn(user: str | None, score: DuetScore, report) -> dict:
        if user is None:
            return {}
        model = skill_model(user)
        newly = model.update(score, report)
        store.put("skills", user, model)
        return {"newly_mastered": newly, **skills_view(model)}

    def graded(score: DuetScore, take: Take):
        played = [PlayedNote(round(p.t_ms * 1000), p.pitch, p.velocity) for p in take.played]
        report = grade_take(score, played)
        return report, {
            "accuracy": round(report.accuracy, 3),
            "results": [g.result for g in report.grades],
            "hardest_bars": report.hardest_bars(),
            "feedback": report.feedback(),
        }

    @app.post("/v1/users/{user}/performances", status_code=201)
    def add_performance(user: str, body: PerformanceIn):
        score = store.get("duet", body.duet_id).data
        report, view = graded(score, body)
        return {**view, **learn(user, score, report)}

    @app.get("/v1/users/{user}/skills")
    def get_skills(user: str):
        return skills_view(skill_model(user))

    @app.post("/v1/users/{user}/compositions", status_code=201)
    def compose_next(user: str, body: NextRequest, background: bool = False):
        difficulty, focus = skill_model(user).next_request()
        request = CompositionRequest(
            prompt=body.prompt, bars=body.bars, difficulty=difficulty, focus=focus
        )
        if background:
            return _accepted(jobs.submit("composition", lambda p: run_composition(request, p)))
        return _sync(lambda: run_composition(request, no_progress))

    @app.post("/v1/transcriptions/{tid}/lessons", status_code=201)
    def create_lesson(tid: str, options: LessonOptions | None = None):
        options = options or LessonOptions()
        record = store.get("transcription", tid)
        title = Path(record.meta.get("filename") or "Your song").stem
        path = teach_song(record.data, options.target_level, title)
        steps = []
        for step in path.steps:
            duet = add_duet(step.score, source="lesson", transcription=tid)
            steps.append(
                {
                    "title": step.title,
                    "difficulty": step.difficulty,
                    "tempo_factor": step.tempo_factor,
                    "duet_id": duet.id,
                    "passed": False,
                }
            )
        lesson = store.add("lesson", {"title": title, "user": options.user, "steps": steps})
        return lesson_view(lesson)

    @app.get("/v1/lessons/{lesson_id}")
    def get_lesson(lesson_id: str):
        return lesson_view(store.get("lesson", lesson_id))

    @app.post("/v1/lessons/{lesson_id}/steps/{n}/attempts", status_code=201)
    def attempt_step(lesson_id: str, n: int, take: Take):
        record = store.get("lesson", lesson_id)
        lesson = record.data
        if not 0 <= n < len(lesson["steps"]):
            raise Problem(404, "NOT_FOUND", f"lesson {lesson_id} has no step {n}")
        step = lesson["steps"][n]
        score = store.get("duet", step["duet_id"]).data
        report, view = graded(score, take)
        step["passed"] = step["passed"] or report.accuracy >= PASS_ACCURACY
        store.put("lesson", lesson_id, lesson)
        user = take.user or lesson.get("user")
        return {
            **view,
            "passed": step["passed"],
            "lesson": lesson_view(store.get("lesson", lesson_id)),
            **learn(user, score, report),
        }

    # Jobs --------------------------------------------------------------------
    @app.get("/v1/jobs/{job_id}")
    def get_job(job_id: str):
        return job_view(store.get("job", job_id))

    @app.websocket("/v1/jobs/{job_id}/stream")
    async def stream_job(websocket: WebSocket, job_id: str):
        await websocket.accept()
        sent = 0
        try:
            while True:
                try:
                    job = store.get("job", job_id)
                except NotFound:
                    await websocket.send_json({"error": {"code": "NOT_FOUND", "detail": job_id}})
                    break
                for event in job.meta["events"][sent:]:
                    await websocket.send_json({"event": event})
                sent = len(job.meta["events"])
                if job.meta["state"] in TERMINAL:
                    await websocket.send_json({"job": job_view(job)})
                    break
                await asyncio.sleep(0.05)
        except WebSocketDisconnect:
            return
        await websocket.close()

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
        duet = add_duet(
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


SYNC_STATUS = {"AUDIO_INVALID": 422, "ROUTE_UNAVAILABLE": 422}


def _sync(work):
    """Run a job's work inline and turn its failure into a problem response."""
    try:
        return work()
    except JobFailure as exc:
        raise Problem(SYNC_STATUS.get(exc.code, 502), exc.code, exc.detail) from exc


def _accepted(job) -> JSONResponse:
    view = job_view(job)
    view["links"] = {"self": f"/v1/jobs/{job.id}", "stream": f"/v1/jobs/{job.id}/stream"}
    return JSONResponse(view, status_code=202)


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise Problem(413, "FILE_TOO_LARGE", "uploads are limited to 200 MB")
    if not data:
        raise Problem(422, "FILE_EMPTY", "the uploaded file is empty")
    return data


def summary_view(record) -> dict:
    score: DuetScore = record.data
    keep = ("source", "featured", "version", "root", "parent", "instruction", "change")
    return {
        "id": record.id,
        "title": score.meta.title,
        "bars": score.bar_count,
        "tempo_bpm": score.meta.tempo_bpm,
        "pianist_difficulty": pianist_difficulty(score),
        **{k: record.meta[k] for k in keep if k in record.meta},
    }


def skills_view(model: SkillModel) -> dict:
    difficulty, focus = model.next_request()
    return {
        "level": model.level,
        "performances": model.performances,
        "skills": {
            name: {"mastery": round(s.mastery, 3), "tries": s.tries, "known": s.known}
            for name, s in sorted(model.skills.items())
        },
        "next": {"difficulty": difficulty, "focus": focus},
    }


def lesson_view(record) -> dict:
    lesson = record.data
    current = next((i for i, s in enumerate(lesson["steps"]) if not s["passed"]), None)
    return {"id": record.id, **lesson, "current_step": current, "done": current is None}


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
