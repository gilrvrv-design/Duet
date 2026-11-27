"""Background jobs and their progress stream (spec §6.2)."""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from duet.api.context import Ctx
from duet.jobs import TERMINAL, job_view
from duet.storage import NotFound

router = APIRouter()

POLL_S = 0.05
STREAM_LIMIT_S = 3600.0  # no job runs longer; a stream that outlives it is abandoned


@router.get("/v1/jobs/{job_id}")
def get_job(ctx: Ctx, job_id: str):
    return job_view(ctx.store.get("job", job_id))


@router.websocket("/v1/jobs/{job_id}/stream")
async def stream_job(websocket: WebSocket, job_id: str):
    store = websocket.app.state.ctx.store
    await websocket.accept()
    sent = 0
    deadline = time.monotonic() + STREAM_LIMIT_S
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
            if time.monotonic() > deadline:
                await websocket.send_json({"error": {"code": "INTERNAL", "detail": "timeout"}})
                break
            await asyncio.sleep(POLL_S)
    except WebSocketDisconnect:
        return
    await websocket.close()
