"""How each kind of record is stored as JSON. The API wires domain types to storage, so
``duet.storage`` itself knows nothing about duets or lessons."""

from __future__ import annotations

from duet.audio.pipeline import Transcription
from duet.pedagogy import SkillModel
from duet.score import DuetScore
from duet.storage import Codec, MemoryStore, SqliteStore, Store


def _same(value):
    return value


def default_codecs() -> dict[str, Codec]:
    return {
        "duet": (lambda s: s.to_dict(), DuetScore.model_validate),
        "transcription": (lambda t: t.to_dict(), Transcription.from_dict),
        "skills": (lambda m: m.model_dump(mode="json"), SkillModel.model_validate),
        "job": (_same, _same),
        "lesson": (_same, _same),
    }


def store_from_env(value: str | None) -> Store:
    """``DUET_DB`` unset or ``:memory:`` -> MemoryStore, else a SQLite file path."""
    if not value or value == ":memory:":
        return MemoryStore()
    return SqliteStore(value, default_codecs())
