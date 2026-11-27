"""Storage of records by kind and id (spec §4.2).

Two stores with the same methods: ``MemoryStore`` for tests and demos, ``SqliteStore``
for a Hub or a small server. A record is identified by its kind *and* its id, so a
user called "duet_abc" can never overwrite the duet with that id.

The store knows nothing about duets or lessons. Whoever creates a ``SqliteStore`` gives
it one codec per kind to turn domain objects into JSON and back.
"""

from __future__ import annotations

import copy
import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
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


Codec = tuple[Callable[[Any], Any], Callable[[Any], Any]]  # (encode, decode) via JSON values
Change = Callable[[Record], Record]  # takes a copy of the record, returns the new record


class Store(Protocol):
    def add(self, kind: str, data: Any, **meta) -> Record: ...
    def put(self, kind: str, record_id: str, data: Any, **meta) -> Record: ...
    def get(self, kind: str, record_id: str) -> Record: ...
    def list(self, kind: str) -> list[Record]: ...
    def delete(self, kind: str, record_id: str) -> None: ...
    def update(
        self, kind: str, record_id: str, change: Change, create: Callable[[], Any] | None = None
    ) -> Record: ...
    def update_meta(self, kind: str, record_id: str, **meta) -> Record: ...


def new_id(kind: str) -> str:
    return f"{kind[:3]}_{uuid.uuid4().hex[:12]}"


def _merge_meta(record: Record, meta: dict) -> Record:
    return replace(record, meta={**record.meta, **meta})


class MemoryStore:
    """Thread-safe and hands out copies, so callers cannot change stored records by
    accident (the same behaviour as SqliteStore)."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], Record] = {}
        self._lock = threading.RLock()

    def add(self, kind: str, data: Any, **meta) -> Record:
        return self.put(kind, new_id(kind), data, **meta)

    def put(self, kind: str, record_id: str, data: Any, **meta) -> Record:
        record = Record(record_id, kind, data, meta)
        with self._lock:
            self._items[(kind, record_id)] = copy.deepcopy(record)
        return record

    def get(self, kind: str, record_id: str) -> Record:
        with self._lock:
            record = self._items.get((kind, record_id))
            if record is None:
                raise NotFound(f"{kind} {record_id} not found")
            return copy.deepcopy(record)

    def list(self, kind: str) -> list[Record]:
        with self._lock:
            found = [copy.deepcopy(r) for (k, _), r in self._items.items() if k == kind]
        return sorted(found, key=lambda r: r.created_at)

    def delete(self, kind: str, record_id: str) -> None:
        with self._lock:
            if self._items.pop((kind, record_id), None) is None:
                raise NotFound(f"{kind} {record_id} not found")

    def update(self, kind, record_id, change, create=None) -> Record:
        """Read, change and write one record as a single step (no lost updates)."""
        with self._lock:
            current = self._items.get((kind, record_id))
            if current is None:
                if create is None:
                    raise NotFound(f"{kind} {record_id} not found")
                current = Record(record_id, kind, create())
            new = change(copy.deepcopy(current))
            self._items[(kind, record_id)] = copy.deepcopy(new)
            return new

    def update_meta(self, kind: str, record_id: str, **meta) -> Record:
        return self.update(kind, record_id, lambda r: _merge_meta(r, meta))


class SqliteStore:
    """One table of JSON records, keyed by (kind, id). Safe to share between threads."""

    def __init__(self, path: str | Path, codecs: dict[str, Codec]) -> None:
        self.path = str(path)
        self.codecs = codecs
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._migrate()

    def _migrate(self) -> None:
        """Create the table; move records from the first schema (id-only key) over."""
        with self._db:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS records_v2 ("
                " kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,"
                " meta TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY (kind, id))"
            )
            old = self._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='records'"
            ).fetchone()
            if old:
                self._db.execute(
                    "INSERT OR IGNORE INTO records_v2 SELECT kind, id, data, meta, created_at"
                    " FROM records"
                )
                self._db.execute("DROP TABLE records")

    def _codec(self, kind: str) -> Codec:
        if kind not in self.codecs:
            raise ValueError(f"no codec for record kind {kind!r}")
        return self.codecs[kind]

    def _row(self, record: Record) -> tuple:
        data = json.dumps(self._codec(record.kind)[0](record.data))
        return (record.kind, record.id, data, json.dumps(record.meta), record.created_at)

    def _read(self, kind: str, record_id: str) -> Record | None:
        row = self._db.execute(
            "SELECT data, meta, created_at FROM records_v2 WHERE kind = ? AND id = ?",
            (kind, record_id),
        ).fetchone()
        if row is None:
            return None
        data, meta, created = row
        return Record(
            record_id, kind, self._codec(kind)[1](json.loads(data)), json.loads(meta), created
        )

    def add(self, kind: str, data: Any, **meta) -> Record:
        return self.put(kind, new_id(kind), data, **meta)

    def put(self, kind: str, record_id: str, data: Any, **meta) -> Record:
        record = Record(record_id, kind, data, meta)
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO records_v2 VALUES (?, ?, ?, ?, ?)", self._row(record)
            )
        return record

    def get(self, kind: str, record_id: str) -> Record:
        with self._lock:
            record = self._read(kind, record_id)
        if record is None:
            raise NotFound(f"{kind} {record_id} not found")
        return record

    def list(self, kind: str) -> list[Record]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, data, meta, created_at FROM records_v2"
                " WHERE kind = ? ORDER BY created_at",
                (kind,),
            ).fetchall()
        decode = self._codec(kind)[1]
        return [Record(i, kind, decode(json.loads(d)), json.loads(m), c) for i, d, m, c in rows]

    def delete(self, kind: str, record_id: str) -> None:
        with self._lock, self._db:
            deleted = self._db.execute(
                "DELETE FROM records_v2 WHERE kind = ? AND id = ?", (kind, record_id)
            ).rowcount
        if not deleted:
            raise NotFound(f"{kind} {record_id} not found")

    def update(self, kind, record_id, change, create=None) -> Record:
        """Read, change and write one record in one transaction (no lost updates)."""
        with self._lock, self._db:
            current = self._read(kind, record_id)
            if current is None:
                if create is None:
                    raise NotFound(f"{kind} {record_id} not found")
                current = Record(record_id, kind, create())
            new = change(current)
            self._db.execute(
                "INSERT OR REPLACE INTO records_v2 VALUES (?, ?, ?, ?, ?)", self._row(new)
            )
            return new

    def update_meta(self, kind: str, record_id: str, **meta) -> Record:
        return self.update(kind, record_id, lambda r: _merge_meta(r, meta))

    def close(self) -> None:
        self._db.close()
