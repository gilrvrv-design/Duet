"""Composition evaluation set and gate (spec §9.3).

Runs every case through the real composition pipeline and measures how well the
composer did before Duet's own repair had to step in. Results carry the prompt-pack id
(a hash of the exact prompts sent), so two runs are comparable only when they should be.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from duet.compose import CompositionRequest, compose
from duet.compose.draft import DRAFT_SCHEMA
from duet.compose.prompts import feedback_message, request_message, system_prompt
from duet.compose.service import Composer
from duet.difficulty import pianist_difficulty
from duet.profile import RobotProfile, robot_profile
from duet.score import MAX_LEVEL, MIN_LEVEL


def load_cases(path: str | Path) -> list[dict]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))["cases"]


def prompt_pack_id(robot: RobotProfile | None = None) -> str:
    """Hash of everything that shapes the composer's answer except the request itself."""
    robot = robot or robot_profile()
    # Every level's rules and the practice-focus wording are part of the prompts too.
    samples = [
        request_message(
            "x",
            difficulty=level,
            bars=1,
            lead="robot",
            pianist_range=("C4", "C5"),
            tempo_bpm=100,
            time_signature=(3, 4),
            focus="x" if level == MIN_LEVEL else None,
        )
        for level in range(MIN_LEVEL, MAX_LEVEL + 1)
    ]
    material = "\n".join(
        [
            system_prompt(robot),
            *samples,
            feedback_message(["x"]),
            json.dumps(DRAFT_SCHEMA, sort_keys=True),
        ]
    )
    return hashlib.sha256(material.encode()).hexdigest()[:12]


@dataclass
class CaseResult:
    id: str
    ok: bool  # a playable duet came out
    first_draft_ok: bool  # no feedback rounds and no repair needed
    rounds: int = 0
    repairs: int = 0
    difficulty_target: int = 0
    difficulty_actual: int = 0
    robot_notes: int = 0
    seconds: float = 0.0
    error: str | None = None

    @property
    def difficulty_ok(self) -> bool:
        return self.ok and self.difficulty_actual <= self.difficulty_target


def run_case(case: dict, composer_factory: Callable[[], Composer]) -> CaseResult:
    request = CompositionRequest(**{k: v for k, v in case.items() if k != "id"})
    started = time.monotonic()
    try:
        result = compose(request, composer_factory())
    except Exception as exc:  # one failing case must not stop the run
        return CaseResult(
            case["id"],
            False,
            False,
            difficulty_target=request.difficulty,
            seconds=round(time.monotonic() - started, 2),
            error=f"{type(exc).__name__}: {exc}",
        )
    return CaseResult(
        id=case["id"],
        ok=True,
        first_draft_ok=result.rounds == 1 and not result.repairs,
        rounds=result.rounds,
        repairs=len(result.repairs),
        difficulty_target=request.difficulty,
        difficulty_actual=pianist_difficulty(result.score),
        robot_notes=len(result.score.part_events("robot")),
        seconds=round(time.monotonic() - started, 2),
    )


def summarize(results: list[CaseResult]) -> dict:
    n = len(results) or 1
    return {
        "cases": len(results),
        "pass_rate": round(sum(r.ok for r in results) / n, 3),
        "first_draft_rate": round(sum(r.first_draft_ok for r in results) / n, 3),
        "difficulty_rate": round(sum(r.difficulty_ok for r in results) / n, 3),
        "mean_rounds": round(statistics.mean(r.rounds for r in results), 2) if results else 0,
        "mean_repairs": round(statistics.mean(r.repairs for r in results), 2) if results else 0,
        "mean_seconds": round(statistics.mean(r.seconds for r in results), 2) if results else 0,
    }


def run_eval(
    cases: list[dict], composer_factory: Callable[[], Composer], workers: int = 4, model: str = ""
) -> dict:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda c: run_case(c, composer_factory), cases))
    return {
        "prompt_pack": prompt_pack_id(),
        "model": model,
        "summary": summarize(results),
        "cases": [asdict(r) for r in results],
    }


# Gate: higher is better for these, and a run may not fall more than the margin below.
GATE = {"pass_rate": 0.02, "first_draft_rate": 0.05, "difficulty_rate": 0.05}


def gate(run: dict, baseline: dict) -> list[str]:
    """Regressions of ``run`` against ``baseline``; empty means the change may ship."""
    problems = []
    for metric, margin in GATE.items():
        new, old = run["summary"][metric], baseline["summary"][metric]
        if new < old - margin:
            problems.append(f"{metric} fell from {old:.0%} to {new:.0%}")
    old_cases = {c["id"]: c for c in baseline["cases"]}
    for case in run["cases"]:
        before = old_cases.get(case["id"])
        if before and before["ok"] and not case["ok"]:
            problems.append(f"case {case['id']} used to pass and now fails: {case['error']}")
    return problems
