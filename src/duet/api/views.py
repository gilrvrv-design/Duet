"""How records are shown in API responses."""

from __future__ import annotations

from duet.copyright import CopyrightGuard
from duet.difficulty import check_pianist, pianist_difficulty
from duet.feasibility import check_robot
from duet.jobs import job_view
from duet.pedagogy import SkillModel, current_step
from duet.profile import keyboard_profile, robot_profile
from duet.score import DuetScore
from duet.storage import Record

__all__ = ["duet_view", "job_view", "lesson_view", "skills_view", "summary_view"]


def duet_view(record: Record, guard: CopyrightGuard) -> dict:
    score: DuetScore = record.data
    robot = robot_profile(score.parts["robot"].instrument_profile)
    keyboard = keyboard_profile(score.parts["pianist"].instrument_profile)
    report = check_robot(score, robot)
    return {
        "id": record.id,
        "score": score.to_dict(),
        "bars": score.bar_count,
        "pianist_difficulty": pianist_difficulty(score),
        "robot_playable": report.ok,
        "robot_problems": report.feedback().splitlines(),
        "pianist_problems": check_pianist(score, keyboard),
        "copyright": guard.check(score).status,
        **record.meta,
    }


def summary_view(record: Record) -> dict:
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


def lesson_view(record: Record) -> dict:
    lesson = record.data
    current = current_step([s["passed"] for s in lesson["steps"]])
    return {"id": record.id, **lesson, "current_step": current, "done": current is None}


def transcription_view(record: Record) -> dict:
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
