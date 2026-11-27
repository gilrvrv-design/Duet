"""Progress reporting for long tasks (spec §6.2, FR-A5).

A long task takes an optional ``progress(stage, fraction)`` callback. ``fraction`` is
0..1 when known, else None. Tasks never depend on anyone listening.
"""

from __future__ import annotations

from collections.abc import Callable

Progress = Callable[[str, float | None], None]


def no_progress(stage: str, fraction: float | None = None) -> None:
    return None
