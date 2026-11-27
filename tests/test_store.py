import json
import sqlite3
import threading
from dataclasses import replace

import pytest

from duet.api.codecs import default_codecs, store_from_env
from duet.audio.notes import NoteEvent
from duet.audio.pipeline import Transcription
from duet.storage import MemoryStore, NotFound, SqliteStore
from helpers import make_score


def sqlite(path):
    return SqliteStore(path, default_codecs())


@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path):
    return MemoryStore() if request.param == "memory" else sqlite(tmp_path / "s.db")


def test_add_get_update_delete(store):
    score = make_score(robot=[(1, 1, 1, "C5")])
    record = store.add("duet", score, source="test")
    again = store.get("duet", record.id)
    assert again.data == score and again.meta == {"source": "test"}
    assert store.update_meta("duet", record.id, rounds=2).meta == {"source": "test", "rounds": 2}
    assert store.get("duet", record.id).meta["rounds"] == 2
    with pytest.raises(NotFound):
        store.get("transcription", record.id)  # wrong kind
    store.delete("duet", record.id)
    with pytest.raises(NotFound):
        store.get("duet", record.id)
    with pytest.raises(NotFound):
        store.delete("duet", record.id)


def test_same_id_in_two_kinds_never_collides(store):
    """A user may be called like a duet's id; neither record may overwrite the other."""
    duet = store.add("duet", make_score(robot=[(1, 1, 1, "C5")]))
    store.put("lesson", duet.id, {"steps": []})
    assert store.get("duet", duet.id).data.events[0].pitch == 72
    assert store.get("lesson", duet.id).data == {"steps": []}
    store.delete("lesson", duet.id)
    assert store.get("duet", duet.id)


def test_records_are_copies(store):
    store.put("lesson", "l1", {"steps": [1]})
    store.get("lesson", "l1").data["steps"].append(2)
    assert store.get("lesson", "l1").data == {"steps": [1]}


def test_concurrent_updates_are_not_lost(store):
    store.put("lesson", "count", {"n": 0})

    def bump(record):
        return replace(record, data={"n": record.data["n"] + 1})

    def worker():
        for _ in range(50):
            store.update("lesson", "count", bump)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert store.get("lesson", "count").data == {"n": 200}


def test_update_creates_or_refuses(store):
    with pytest.raises(NotFound):
        store.update("lesson", "nope", lambda r: r)
    made = store.update("lesson", "new", lambda r: r, create=lambda: {"steps": []})
    assert store.get("lesson", "new").data == made.data == {"steps": []}


def test_a_failed_change_writes_nothing(store):
    store.put("lesson", "l1", {"n": 1})

    def boom(record):
        record.data["n"] = 99
        raise RuntimeError("no")

    with pytest.raises(RuntimeError):
        store.update("lesson", "l1", boom)
    assert store.get("lesson", "l1").data == {"n": 1}


def test_transcriptions_round_trip(store):
    t = Transcription([NoteEvent(0.0, 0.5, 72, 90, 0.9, "vocals")], 120.0, "C major", 1.0, "pyin")
    assert store.get("transcription", store.add("transcription", t).id).data == t


def test_sqlite_survives_reopening(tmp_path):
    path = tmp_path / "keep.db"
    record = sqlite(path).add("duet", make_score(robot=[(1, 1, 1, "E5")]))
    assert sqlite(path).get("duet", record.id).data.events[0].pitch == 76


def test_sqlite_moves_records_from_the_first_schema(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL,"
        " meta TEXT NOT NULL, created_at REAL NOT NULL)"
    )
    db.execute(
        "INSERT INTO records VALUES (?, ?, ?, ?, ?)",
        ("les_1", "lesson", json.dumps({"steps": []}), json.dumps({"x": 1}), 1.0),
    )
    db.commit()
    db.close()
    moved = sqlite(path).get("lesson", "les_1")
    assert moved.data == {"steps": []} and moved.meta == {"x": 1}


def test_unknown_kind_and_env(tmp_path):
    with pytest.raises(ValueError, match="no codec"):
        sqlite(tmp_path / "x.db").add("kazoo", 1)
    assert isinstance(store_from_env(None), MemoryStore)
    assert isinstance(store_from_env(str(tmp_path / "e.db")), SqliteStore)
