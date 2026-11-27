import pytest

from duet.api.store import MemoryStore, NotFound, SqliteStore, store_from_env
from duet.audio.notes import NoteEvent
from duet.audio.pipeline import Transcription
from helpers import make_score


@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path):
    return MemoryStore() if request.param == "memory" else SqliteStore(tmp_path / "s.db")


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


def test_transcriptions_round_trip(store):
    t = Transcription([NoteEvent(0.0, 0.5, 72, 90, 0.9, "vocals")], 120.0, "C major", 1.0, "pyin")
    assert store.get("transcription", store.add("transcription", t).id).data == t


def test_sqlite_survives_reopening(tmp_path):
    path = tmp_path / "keep.db"
    record = SqliteStore(path).add("duet", make_score(robot=[(1, 1, 1, "E5")]))
    assert SqliteStore(path).get("duet", record.id).data.events[0].pitch == 76


def test_unknown_kind_and_env(tmp_path):
    with pytest.raises(ValueError, match="no codec"):
        SqliteStore(tmp_path / "x.db").add("kazoo", 1)
    assert isinstance(store_from_env(None), MemoryStore)
    assert isinstance(store_from_env(str(tmp_path / "e.db")), SqliteStore)
