import io

import pytest
import soundfile
from fastapi.testclient import TestClient

from duet.api import create_app
from duet.api.store import MemoryStore, SqliteStore
from duet.audio.fullmix import full_mix_available
from duet.midi_io import midi_to_score, score_to_midi_bytes
from helpers import ROOT, make_score, synth
from test_compose import GOOD, ScriptedComposer

EXAMPLE = (ROOT / "examples" / "rain-on-the-bottles.json").read_text()


@pytest.fixture(params=["memory", "sqlite"])
def client(request, tmp_path):
    store = MemoryStore() if request.param == "memory" else SqliteStore(tmp_path / "duet.db")
    return TestClient(create_app(composer_factory=lambda: ScriptedComposer(GOOD), store=store))


def test_health_and_reachability(client):
    assert client.get("/v1/health").json()["status"] == "ok"
    body = client.get("/v1/profiles/bottles-v1/reachability").json()
    assert len(body["min_interval_s"]) == 8
    problem = client.get("/v1/profiles/kazoo/reachability")
    assert problem.status_code == 404
    assert problem.headers["content-type"] == "application/problem+json"
    assert problem.json()["code"] == "NOT_FOUND"


def test_duet_lifecycle(client):
    created = client.post(
        "/v1/duets", content=EXAMPLE, headers={"content-type": "application/json"}
    )
    assert created.status_code == 201
    duet = created.json()
    assert duet["robot_playable"] and duet["bars"] == 4
    assert client.get(f"/v1/duets/{duet['id']}").json()["score"] == duet["score"]
    midi = client.get(f"/v1/duets/{duet['id']}/midi")
    assert midi.headers["content-type"] == "audio/midi"
    assert len(midi_to_score(midi.content).events) == 13
    assert client.delete(f"/v1/duets/{duet['id']}").status_code == 204
    assert client.get(f"/v1/duets/{duet['id']}").status_code == 404


def test_invalid_score(client):
    response = client.post("/v1/duets", json={"events": [{"part": "drums"}]})
    assert response.status_code == 422 and response.json()["code"] == "SCORE_INVALID"


def test_import_and_repair(client):
    hard = make_score(robot=[(1, 1, 0.5, "C5"), (1, 1.5, 0.5, "C6")])
    files = {"file": ("hard.mid", score_to_midi_bytes(hard), "audio/midi")}
    duet = client.post("/v1/duets/import", files=files).json()
    assert not duet["robot_playable"] and duet["robot_problems"]
    fixed = client.post(f"/v1/duets/{duet['id']}/repair").json()
    assert fixed["robot_playable"] and fixed["parent"] == duet["id"] and fixed["changes"]
    bad = client.post("/v1/duets/import", files={"file": ("x.mid", b"nope", "audio/midi")})
    assert bad.status_code == 422 and bad.json()["code"] == "MIDI_INVALID"


def test_composition(client):
    response = client.post("/v1/compositions", json={"prompt": "happy", "difficulty": 1, "bars": 2})
    assert response.status_code == 201
    body = response.json()
    assert body["robot_playable"] and body["rounds"] == 1
    assert body["explanation"].startswith("The robot sings")
    assert client.post("/v1/compositions", json={"prompt": ""}).status_code == 422


def test_transcription_and_arrangement(client):
    buffer = io.BytesIO()
    tune = [(p, i * 0.5, 0.45) for i, p in enumerate([60, 64, 67, 72, 67, 64, 60])]
    soundfile.write(buffer, synth(tune), 22050, format="WAV")
    files = {"file": ("hum.wav", buffer.getvalue(), "audio/wav")}

    refused = client.post("/v1/transcriptions", files=files, data={"rights_confirmed": "false"})
    assert refused.json()["code"] == "RIGHTS_NOT_CONFIRMED"

    t = client.post("/v1/transcriptions", files=files, data={"rights_confirmed": "true"}).json()
    assert t["notes"] == 7 and t["model"] == "pyin"
    assert client.get(f"/v1/transcriptions/{t['id']}").json() == t
    midi = client.get(f"/v1/transcriptions/{t['id']}/midi")
    assert midi.status_code == 200 and midi.content.startswith(b"MThd")

    duet = client.post(f"/v1/transcriptions/{t['id']}/arrangements", json={"difficulty": 2}).json()
    assert duet["robot_playable"] and duet["coverage_after"] == 1.0
    assert duet["score"]["meta"]["title"] == "hum"

    if not full_mix_available():
        data = {"rights_confirmed": "true", "route": "full"}
        unavailable = client.post("/v1/transcriptions", files=files, data=data)
        assert unavailable.json()["code"] == "ROUTE_UNAVAILABLE"

    junk = {"file": ("junk.mp3", b"not audio", "audio/mpeg")}
    bad = client.post("/v1/transcriptions", files=junk, data={"rights_confirmed": "true"})
    assert bad.status_code == 422 and bad.json()["code"] == "AUDIO_INVALID"
