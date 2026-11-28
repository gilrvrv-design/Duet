"""Background jobs for long tasks: composition and transcription (spec §6.2).

A job is a store record of kind "job". Its meta holds the state, the progress events
and, at the end, the result or the error. Anyone can follow a job by reading the store,
so the same mechanism works with one process or many.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from enum import StrEnum
from typing import Any

from duet.errors import Problem
from duet.progress import Progress
from duet.storage import Record, Store


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


TERMINAL = frozenset({JobState.SUCCEEDED, JobState.FAILED})


Work = Callable[[Progress], dict]


class JobRunner:
    def __init__(self, store: Store, workers: int = 2) -> None:
        self.store = store
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="duet-job")

    def submit(self, job_type: str, work: Work) -> Record:
        """Start ``work(progress) -> result dict`` in the background; returns the job record."""
        record = self.store.add(
            "job", {"type": job_type}, type=job_type, state=JobState.QUEUED, events=[]
        )
        self._add_event(record.id, "queued", 0.0)
        self._pool.submit(self._run, record.id, work)
        return self.store.get("job", record.id)

    def _add_event(self, job_id: str, stage: str, fraction: float | None, **fields: Any) -> None:
        def append(job: Record) -> Record:
            events = job.meta["events"]
            event = {"seq": len(events), "stage": stage, "progress": fraction, "t": time.time()}
            return replace(job, meta={**job.meta, **fields, "events": [*events, event]})

        self.store.update("job", job_id, append)  # one step: no event is ever lost

    def _run(self, job_id: str, work: Work) -> None:
        self._add_event(job_id, "started", 0.0, state=JobState.RUNNING)
        try:
            result = work(lambda stage, fraction=None: self._add_event(job_id, stage, fraction))
        except Problem as exc:
            self._fail(job_id, exc.code, exc.detail)
        except Exception as exc:  # report every failure on the job, never lose it
            self._fail(job_id, "INTERNAL", f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
        else:
            self._add_event(job_id, "done", 1.0, state=JobState.SUCCEEDED, result=result)

    def _fail(self, job_id: str, code: str, detail: str) -> None:
        self._add_event(
            job_id, "failed", None, state=JobState.FAILED, error={"code": code, "detail": detail}
        )

    def wait(self, job_id: str, timeout_s: float = 30.0) -> Record:
        """Block until a job ends (for tests and the CLI)."""
        deadline = time.monotonic() + timeout_s
        while True:
            job = self.store.get("job", job_id)
            if job.meta["state"] in TERMINAL:
                return job
            if time.monotonic() > deadline:
                raise TimeoutError(f"job {job_id} still {job.meta['state']}")
            time.sleep(0.01)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)


def job_view(job: Record) -> dict:
    meta = job.meta
    view = {
        "id": job.id,
        "type": meta["type"],
        "state": meta["state"],
        "progress": next(
            (e["progress"] for e in reversed(meta["events"]) if e["progress"] is not None), 0.0
        ),
        "stage": meta["events"][-1]["stage"] if meta["events"] else None,
    }
    if "result" in meta:
        view["result"] = meta["result"]
    if "error" in meta:
        view["error"] = meta["error"]
    return view


__all__ = ["JobRunner", "JobState", "job_view"]
