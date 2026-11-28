"""What every route needs: the store, the job runner, the copyright guard, the composer,
and the shared ways of running work and reading uploads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, UploadFile
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse

from duet.api.errors import Problem
from duet.compose.service import Composer
from duet.copyright import CopyrightGuard
from duet.jobs import JobFailure, JobRunner, Work, job_view
from duet.learning import USER_PATTERN
from duet.live import Practices
from duet.progress import no_progress
from duet.storage import Store

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


@dataclass
class AppContext:
    store: Store
    jobs: JobRunner
    guard: CopyrightGuard
    composer_factory: Callable[[], Composer]
    live: Practices

    def run_or_submit(self, kind: str, work: Work, background: bool):
        """Run ``work`` now (its failure becomes a problem response), or as a job."""
        if background:
            job = self.jobs.submit(kind, work)
            view = job_view(job)
            view["links"] = {"self": f"/v1/jobs/{job.id}", "stream": f"/v1/jobs/{job.id}/stream"}
            return JSONResponse(view, status_code=202)
        try:
            return work(no_progress)
        except JobFailure as exc:
            raise Problem(exc.code, exc.detail) from exc


def get_context(request: Request) -> AppContext:
    return request.app.state.ctx


Ctx = Annotated[AppContext, Depends(get_context)]
UserId = Annotated[str, PathParam(pattern=USER_PATTERN)]


async def read_upload(file: UploadFile) -> bytes:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise Problem("FILE_TOO_LARGE", f"uploads are limited to {MAX_UPLOAD_BYTES // 2**20} MB")
    if not data:
        raise Problem("FILE_EMPTY", "the uploaded file is empty")
    return data
