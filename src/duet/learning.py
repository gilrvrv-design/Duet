"""Learning records (spec §5.8): skill models per user and lessons, kept in a store.

Each change is one atomic store update, so two performances arriving together are both
counted.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from duet.library import add_duet
from duet.listening import Report
from duet.pedagogy import SkillModel, step_passes, teach_song
from duet.score import DuetScore
from duet.storage import NotFound, Record, Store

USER_PATTERN = r"^[A-Za-z0-9_.-]{1,64}$"  # user ids are path segments: keep them plain


def skill_model(store: Store, user: str) -> SkillModel:
    try:
        return store.get("skills", user).data
    except NotFound:
        return SkillModel()


def learn(
    store: Store, user: str, score: DuetScore, report: Report
) -> tuple[SkillModel, list[str]]:
    """Update a user's skills from one graded performance; returns (model, newly mastered)."""
    newly: list[str] = []

    def change(record: Record) -> Record:
        model = record.data
        newly.extend(model.update(score, report))
        return replace(record, data=model)

    record = store.update("skills", user, change, create=SkillModel)
    return record.data, newly


def create_lesson(
    store: Store, transcription_id: str, target_level: int, user: str | None
) -> Record:
    """'Teach me this song' (FR-A26): every step's duet goes into the library."""
    record = store.get("transcription", transcription_id)
    title = Path(record.meta.get("filename") or "Your song").stem
    steps = []
    for step in teach_song(record.data, target_level, title).steps:
        duet = add_duet(store, step.score, source="lesson", transcription=transcription_id)
        steps.append(
            {
                "title": step.title,
                "difficulty": step.difficulty,
                "tempo_factor": step.tempo_factor,
                "duet_id": duet.id,
                "passed": False,
            }
        )
    return store.add("lesson", {"title": title, "user": user, "steps": steps})


def record_attempt(store: Store, lesson_id: str, step: int, report: Report) -> Record:
    """Mark a step passed if this attempt passes (it never un-passes)."""

    def change(record: Record) -> Record:
        lesson = record.data
        if not 0 <= step < len(lesson["steps"]):
            raise NotFound(f"lesson {lesson_id} has no step {step}")
        lesson["steps"][step]["passed"] = lesson["steps"][step]["passed"] or step_passes(report)
        return replace(record, data=lesson)

    return store.update("lesson", lesson_id, change)
