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


def wait_for(client, job_id, timeout=30):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/v1/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_background_composition_with_stream(client):
    accepted = client.post(
        "/v1/compositions?background=true", json={"prompt": "happy", "difficulty": 1, "bars": 2}
    )
    assert accepted.status_code == 202
    job = accepted.json()
    assert job["links"]["stream"] == f"/v1/jobs/{job['id']}/stream"
    with client.websocket_connect(job["links"]["stream"]) as ws:
        messages = []
        while True:
            message = ws.receive_json()
            messages.append(message)
            if "job" in message:
                break
    stages = [m["event"]["stage"] for m in messages if "event" in m]
    assert stages[:2] == ["queued", "started"] and stages[-1] == "done"
    assert "drafting" in stages and "checking" in stages and "ready" in stages
    assert [m["event"]["seq"] for m in messages if "event" in m] == list(range(len(stages)))
    final = messages[-1]["job"]
    assert final["state"] == "succeeded" and final["progress"] == 1.0
    duet_id = final["result"]["id"]
    assert client.get(f"/v1/duets/{duet_id}").json()["robot_playable"]


def test_background_transcription_and_failure(client):
    buffer = io.BytesIO()
    soundfile.write(buffer, synth([(72, 0, 0.4), (76, 0.5, 0.4)]), 22050, format="WAV")
    files = {"file": ("two.wav", buffer.getvalue(), "audio/wav")}
    data = {"rights_confirmed": "true", "route": "melody"}
    job = client.post("/v1/transcriptions?background=true", files=files, data=data).json()
    done = wait_for(client, job["id"])
    assert done["state"] == "succeeded" and done["result"]["notes"] == 2

    junk = {"file": ("junk.mp3", b"not audio", "audio/mpeg")}
    job = client.post("/v1/transcriptions?background=true", files=junk, data=data).json()
    failed = wait_for(client, job["id"])
    assert failed["state"] == "failed" and failed["error"]["code"] == "AUDIO_INVALID"


def test_unknown_job(client):
    assert client.get("/v1/jobs/job_missing").status_code == 404
    with client.websocket_connect("/v1/jobs/job_missing/stream") as ws:
        assert ws.receive_json()["error"]["code"] == "NOT_FOUND"


def take_for(score_dict, results_ok=True, user=None):
    """Play every pianist note on time (or a wrong key each time)."""
    from duet.score import load_score
    from duet.timing import timed_events

    score = load_score(score_dict)
    played = [
        {
            "t_ms": t.start_s * 1000 + 500,
            "pitch": t.event.pitch if results_ok else t.event.pitch + 1,
        }
        for t in timed_events(score, "pianist")
    ]
    return {"played": played, **({"user": user} if user else {})}


def test_learning_endpoints(client):
    duet = client.post(
        "/v1/duets", content=EXAMPLE, headers={"content-type": "application/json"}
    ).json()
    assert client.get("/v1/users/ana/skills").json()["level"] == 1
    for _ in range(2):
        body = {"duet_id": duet["id"], **take_for(duet["score"])}
        result = client.post("/v1/users/ana/performances", json=body).json()
    assert result["accuracy"] == 1.0 and result["feedback"].startswith("You played 4 of 4")
    skills = client.get("/v1/users/ana/skills").json()
    assert skills["performances"] == 2 and skills["skills"]["steps"]["known"]
    assert skills["next"]["difficulty"] == 2
    composed = client.post("/v1/users/ana/compositions", json={"prompt": "happy", "bars": 2})
    assert composed.status_code == 201


def test_lessons_from_a_transcription(client):
    buffer = io.BytesIO()
    tune = [(p, i * 0.5, 0.45) for i, p in enumerate([60, 64, 67, 72, 67, 64, 60, 62])]
    soundfile.write(buffer, synth(tune), 22050, format="WAV")
    files = {"file": ("song.wav", buffer.getvalue(), "audio/wav")}
    t = client.post("/v1/transcriptions", files=files, data={"rights_confirmed": "true"}).json()
    lesson = client.post(
        f"/v1/transcriptions/{t['id']}/lessons", json={"target_level": 2, "user": "ben"}
    ).json()
    assert [s["title"] for s in lesson["steps"]] == [
        "Level 1 slowly",
        "Level 1 at full speed",
        "Level 2 slowly",
        "Level 2 at full speed",
    ]
    assert lesson["current_step"] == 0
    step = client.get(f"/v1/duets/{lesson['steps'][0]['duet_id']}").json()
    bad = client.post(
        f"/v1/lessons/{lesson['id']}/steps/0/attempts", json=take_for(step["score"], False)
    ).json()
    assert not bad["passed"] and bad["lesson"]["current_step"] == 0
    good = client.post(
        f"/v1/lessons/{lesson['id']}/steps/0/attempts", json=take_for(step["score"])
    ).json()
    assert good["passed"] and good["lesson"]["current_step"] == 1
    assert good["performances"] == 2  # the lesson's user learned from both attempts
    assert (
        client.post(f"/v1/lessons/{lesson['id']}/steps/9/attempts", json={"played": []}).status_code
        == 404
    )
