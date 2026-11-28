"""API errors (spec §6.3): RFC 9457 problem details. The codes and the coded error
itself are duet.errors.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.responses import JSONResponse

from duet.compose.service import ComposerError, CompositionError
from duet.errors import STATUS, Problem

__all__ = ["STATUS", "Problem", "composer_problems", "problem_response"]


@contextmanager
def composer_problems() -> Iterator[None]:
    """What a composer (the LLM) can fail with, as problems: a draft that never became
    playable, or the composer itself failing."""
    try:
        yield
    except CompositionError as exc:
        raise Problem("COMPOSITION_FAILED", str(exc)) from exc
    except ComposerError as exc:
        raise Problem("LLM_ERROR", str(exc)) from exc


def problem_response(exc: Problem) -> JSONResponse:
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
