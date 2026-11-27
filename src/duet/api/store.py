"""Storage behind the API (spec §4.2).

Two stores with the same methods: ``MemoryStore`` for tests and demos, ``SqliteStore``
for a Hub or a small server. A Postgres store can implement the same three methods.
Records hold domain objects; codecs turn them into JSON for storage.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class Record:
    id: str
    kind: str
    data: Any
    meta: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class NotFound(KeyError):
    pass


class Store(Protocol):
    def add(self, kind: str, data: Any, **meta) -> Record: ...
    def put(self, kind: str, record_id: str, data: Any, **meta) -> Record: ...
    def get(self, kind: str, record_id: str) -> Record: ...
    def delete(self, kind: str, record_id: str) -> None: ...
    def list(self, kind: str) -> list[Record]: ...
    def update_meta(self, kind: str, record_id: str, **meta) -> Record: ...


def _new_id(kind: str) -> str:
    return f"{kind[:3]}_{uuid.uuid4().hex[:12]}"


class MemoryStore:
    def __init__(self) -> None:
        self._items: dict[str, Record] = {}
        self._lock = threading.Lock()

    def add(self, kind: str, data: Any, **meta) -> Record:
        record = Record(_new_id(kind), kind, data, meta)
        with self._lock:
            self._items[record.id] = record
        return record

    def put(self, kind: str, record_id: str, data: Any, **meta) -> Record:
        """Create or replace a record with a known id (for example one per user)."""
        record = Record(record_id, kind, data, meta)
        with self._lock:
            self._items[record_id] = record
        return record

    def get(self, kind: str, record_id: str) -> Record:
        record = self._items.get(record_id)
        if record is None or record.kind != kind:
            raise NotFound(f"{kind} {record_id} not found")
        return record

    def delete(self, kind: str, record_id: str) -> None:
        self.get(kind, record_id)
        with self._lock:
            del self._items[record_id]

    def list(self, kind: str) -> list[Record]:
        with self._lock:
            return sorted(
                (r for r in self._items.values() if r.kind == kind), key=lambda r: r.created_at
            )

    def update_meta(self, kind: str, record_id: str, **meta) -> Record:
        record = self.get(kind, record_id)
        with self._lock:
            record.meta.update(meta)
        return record


Codec = tuple[Callable[[Any], Any], Callable[[Any], Any]]  # (encode, decode) via JSON values


def default_codecs() -> dict[str, Codec]:
    from duet.score import DuetScore

    def transcription_decode(data):
        from duet.audio.pipeline import Transcription

        return Transcription.from_dict(data)

    return {
        "duet": (lambda s: s.to_dict(), DuetScore.model_validate),
        "transcription": (lambda t: t.to_dict(), transcription_decode),
        "job": (lambda j: j, lambda j: j),
        "skills": (lambda m: m.model_dump(mode="json"), _skills_decode),
        "lesson": (lambda d: d, lambda d: d),
    }


def _skills_decode(data):
    from duet.pedagogy import SkillModel

    return SkillModel.model_validate(data)


class SqliteStore:
    """One table of JSON records. Safe to share between threads."""

    def __init__(self, path: str | Path, codecs: dict[str, Codec] | None = None) -> None:
        self.path = str(path)
        self.codecs = codecs or default_codecs()
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS records ("
            " id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL,"
            " meta TEXT NOT NULL, created_at REAL NOT NULL)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS records_kind ON records(kind)")
        self._db.commit()

    def _codec(self, kind: str) -> Codec:
        if kind not in self.codecs:
            raise ValueError(f"no codec for record kind {kind!r}")
        return self.codecs[kind]

    def add(self, kind: str, data: Any, **meta) -> Record:
        record = Record(_new_id(kind), kind, data, meta)
        encoded = json.dumps(self._codec(kind)[0](data))
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO records VALUES (?, ?, ?, ?, ?)",
                (record.id, kind, encoded, json.dumps(meta), record.created_at),
            )
        return record

    def put(self, kind: str, record_id: str, data: Any, **meta) -> Record:
        """Create or replace a record with a known id (for example one per user)."""
        record = Record(record_id, kind, data, meta)
        encoded = json.dumps(self._codec(kind)[0](data))
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO records VALUES (?, ?, ?, ?, ?)",
                (record_id, kind, encoded, json.dumps(meta), record.created_at),
            )
        return record

    def get(self, kind: str, record_id: str) -> Record:
        with self._lock:
            row = self._db.execute(
                "SELECT data, meta, created_at FROM records WHERE id = ? AND kind = ?",
                (record_id, kind),
            ).fetchone()
        if row is None:
            raise NotFound(f"{kind} {record_id} not found")
        data, meta, created = row
        return Record(
            record_id, kind, self._codec(kind)[1](json.loads(data)), json.loads(meta), created
        )

    def delete(self, kind: str, record_id: str) -> None:
        with self._lock, self._db:
            deleted = self._db.execute(
                "DELETE FROM records WHERE id = ? AND kind = ?", (record_id, kind)
            ).rowcount
        if not deleted:
            raise NotFound(f"{kind} {record_id} not found")

    def list(self, kind: str) -> list[Record]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, data, meta, created_at FROM records WHERE kind = ? ORDER BY created_at",
                (kind,),
            ).fetchall()
        decode = self._codec(kind)[1]
        return [Record(i, kind, decode(json.loads(d)), json.loads(m), c) for i, d, m, c in rows]

    def update_meta(self, kind: str, record_id: str, **meta) -> Record:
        record = self.get(kind, record_id)
        record.meta.update(meta)
        with self._lock, self._db:
            self._db.execute(
                "UPDATE records SET meta = ? WHERE id = ?", (json.dumps(record.meta), record_id)
            )
        return record

    def close(self) -> None:
        self._db.close()


def store_from_env(value: str | None) -> Store:
    """``DUET_DB`` unset or ``:memory:`` -> MemoryStore, else a SQLite file path."""
    if not value or value == ":memory:":
        return MemoryStore()
    return SqliteStore(value)
