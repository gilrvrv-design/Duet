"""Storage behind the API. In memory for now; a database can implement the same methods."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Record:
    id: str
    kind: str
    data: Any
    meta: dict = field(default_factory=dict)


class NotFound(KeyError):
    pass


class MemoryStore:
    def __init__(self) -> None:
        self._items: dict[str, Record] = {}
        self._lock = threading.Lock()

    def add(self, kind: str, data: Any, **meta) -> Record:
        record = Record(f"{kind[:3]}_{uuid.uuid4().hex[:12]}", kind, data, meta)
        with self._lock:
            self._items[record.id] = record
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
