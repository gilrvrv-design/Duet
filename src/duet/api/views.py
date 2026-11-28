"""How records are shown in API responses."""

from __future__ import annotations

from duet.copyright import CopyrightGuard
from duet.pedagogy import SkillModel, current_step
from duet.performers import human_difficulty, score_problems
from duet.score import DuetScore
from duet.storage import Record

# What a duet record's meta may say, by who wrote it: the library, then each source.
LINE_META = ("source", "featured", "version", "root", "parent", "forked_from", "visibility",
             "own_work", "instruction", "change")  # fmt: skip
DUET_META = LINE_META + (
    "explanation", "rounds", "repairs", "warnings",  # composition, MIDI
    "transcription", "transpose", "coverage_before", "coverage_after", "chords", "retuning",
)  # fmt: skip


def duet_view(record: Record, guard: CopyrightGuard) -> dict:
    score: DuetScore = record.data
    problems = score_problems(score)
    bots = set(score.parts_played_by("bot"))
    return {
        "id": record.id,
        "score": score.to_dict(),
        "bars": score.bar_count,
        "difficulty": human_difficulty(score),
        # Playable: every bot can play its part. People can try anything; their
        # problems say what is too hard or off the instrument.
        "playable": not any(problems[name] for name in bots),
        "parts": {
            name: {
                "instrument": info.instrument,
                "performer": info.performer,
                "problems": problems[name],
            }
            for name, info in score.parts.items()
        },
        "copyright": guard.check(score).status,
        **_meta(record, DUET_META),
    }


def summary_view(record: Record) -> dict:
    score: DuetScore = record.data
    return {
        "id": record.id,
        "title": score.meta.title,
        "bars": score.bar_count,
        "tempo_bpm": score.meta.tempo_bpm,
        "difficulty": human_difficulty(score),
        **_meta(record, LINE_META),
    }


def _meta(record: Record, keys: tuple[str, ...]) -> dict:
    return {k: record.meta[k] for k in keys if k in record.meta}


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
