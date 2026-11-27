"""FastAPI application: wiring only (spec §6.1). Routes live in ``duet.api.routes``.

Errors use RFC 9457 problem details with stable codes (spec §6.3).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request

from duet import __version__
from duet.api.codecs import store_from_env
from duet.api.context import AppContext
from duet.api.errors import Problem, problem_response
from duet.api.routes import compositions, duets, jobs, learning, system, transcriptions
from duet.compose.service import Composer
from duet.copyright import CopyrightGuard
from duet.jobs import JobRunner
from duet.library import seed_featured
from duet.storage import NotFound, Store


def _claude() -> Composer:
    from duet.compose.claude import ClaudeComposer

    return ClaudeComposer()


def create_app(
    composer_factory: Callable[[], Composer] | None = None,
    store: Store | None = None,
    guard: CopyrightGuard | None = None,
    examples_dir: Path | str | None = None,
) -> FastAPI:
    """Build the app. Everything it depends on can be passed in; the defaults read
    ``DUET_DB``, ``DUET_EXAMPLES`` and ``DUET_PROTECTED_MELODIES``."""
    store = store or store_from_env(os.environ.get("DUET_DB"))
    if examples_dir is None and os.environ.get("DUET_EXAMPLES"):
        examples_dir = os.environ["DUET_EXAMPLES"]
    seed_featured(store, Path(examples_dir) if examples_dir else None)
    ctx = AppContext(
        store=store,
        jobs=JobRunner(store),
        guard=guard or CopyrightGuard.load(),
        composer_factory=composer_factory or _claude,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        ctx.jobs.shutdown()

    app = FastAPI(title="Duet", version=__version__, lifespan=lifespan)
    app.state.ctx = ctx
    app.state.store = store  # kept for tools and tests that inspect the store
    app.state.jobs = ctx.jobs

    @app.exception_handler(Problem)
    async def _problem(_: Request, exc: Problem):
        return problem_response(exc)

    @app.exception_handler(NotFound)
    async def _not_found(_: Request, exc: NotFound):
        return problem_response(Problem("NOT_FOUND", str(exc.args[0])))

    for module in (system, duets, compositions, transcriptions, learning, jobs):
        app.include_router(module.router)
    return app
