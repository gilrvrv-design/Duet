"""Composing with the LLM (spec §5.1)."""

from __future__ import annotations

from fastapi import APIRouter

from duet.api.context import AppContext, Ctx
from duet.api.errors import composer_problems
from duet.api.views import duet_view
from duet.compose import CompositionRequest, compose
from duet.library import add_duet
from duet.progress import Progress

router = APIRouter()


def run_composition(ctx: AppContext, request: CompositionRequest, progress: Progress) -> dict:
    with composer_problems():
        result = compose(request, ctx.composer_factory(), progress=progress, guard=ctx.guard)
    record = add_duet(
        ctx.store,
        result.score,
        source="composition",
        explanation=result.explanation,
        rounds=result.rounds,
        repairs=[f"{c.kind}: bar {c.bar} beat {c.beat:g}: {c.detail}" for c in result.repairs],
        warnings=result.warnings,
    )
    return duet_view(record, ctx.guard)


@router.post("/v1/compositions", status_code=201)
def create_composition(ctx: Ctx, request: CompositionRequest, background: bool = False):
    return ctx.run_or_submit("composition", lambda p: run_composition(ctx, request, p), background)
