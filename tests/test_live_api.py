"""Practice from the rig's page, on the server's side (duet.live, /v1/live): the server
plays a library duet on the native device while it listens to a simulated pianist."""

import time

import pytest
from fastapi.testclient import TestClient

from duet.api.app import create_app
from duet.listening import SimulatedPianist
from duet.storage import MemoryStore
from helpers import ROOT, SIMULATED_PIANIST, eventually

PIANIST = SIMULATED_PIANIST


@pytest.fixture
def client():
    app = create_app(
        store=MemoryStore(),
        examples_dir=ROOT / "examples",
        live_inputs={PIANIST: lambda _robot: SimulatedPianist(reaction_s=0.2)},
    )
    with TestClient(app) as client:  # the lifespan stops any practice at the end
        yield client


def rain(client) -> str:
    return client.get("/v1/duets", params={"q": "Rain on the Bottles"}).json()[0]["id"]


def practise(client, device, **request) -> dict:
    body = {"duet_id": rain(client), "rig": device.serial_url, "profile": "bottles-v1"}
    reply = client.post("/v1/live", json=body | request)
    assert reply.status_code == 201, reply.text
    return reply.json()


def until_over(client, practice_id: str, timeout_s: float = 30) -> dict:
    seen = []

    def over():
        seen.append(client.get(f"/v1/live/{practice_id}").json())
        return seen[-1]["state"] in ("done", "stopped", "failed")

    assert eventually(over, timeout_s, every_s=0.1), f"still {seen[-1]['state']}"
    return seen[-1]


def test_the_server_offers_its_inputs(client):
    assert client.get("/v1/live/inputs").json() == {"inputs": [PIANIST]}


def test_a_practice_waits_for_the_pianist_and_grades_them(client, device):
    started = practise(client, device, mode="wait", input=PIANIST)
    assert started["state"] in ("connecting", "playing")
    assert started["title"] == "Rain on the Bottles"
    done = until_over(client, started["id"])
    assert done["state"] == "done", done["detail"]
    assert done["detail"].startswith("waited ")
    assert "notes" in done["detail"]  # the grade of what was heard


def test_one_practice_at_a_time_and_stop(client, device):
    first = practise(client, device, mode="play")
    busy = client.post(
        "/v1/live",
        json={"duet_id": rain(client), "rig": device.serial_url, "profile": "bottles-v1",
              "mode": "play"},
    )  # fmt: skip
    assert busy.status_code == 409 and busy.json()["code"] == "PRACTICE_BUSY"
    time.sleep(1)
    stopped = client.post(f"/v1/live/{first['id']}/stop").json()
    assert until_over(client, stopped["id"])["state"] == "stopped"
    second = practise(client, device, mode="play")  # the server and the rig are free again
    client.post(f"/v1/live/{second['id']}/stop")
    assert until_over(client, second["id"])["state"] == "stopped"


def test_what_cannot_start_says_why(client, device):
    duet = rain(client)
    base = {"duet_id": duet, "rig": device.serial_url, "profile": "bottles-v1"}
    no_input = client.post("/v1/live", json=base | {"mode": "follow"})
    assert no_input.status_code == 422 and no_input.json()["code"] == "LIVE_INVALID"
    assert PIANIST in no_input.json()["detail"]  # it says what it offers
    bad_rig = client.post("/v1/live", json=base | {"mode": "play", "rig": "http://x/"})
    assert bad_rig.status_code == 422
    assert client.get("/v1/live/nothing").status_code == 404


def test_a_rig_that_does_not_answer(client):
    started = client.post(
        "/v1/live",
        json={"duet_id": rain(client), "rig": "tcp://127.0.0.1:9", "profile": "bottles-v1",
              "mode": "play"},
    ).json()  # fmt: skip
    failed = until_over(client, started["id"])
    assert failed["state"] == "failed" and "tcp://127.0.0.1:9" in failed["detail"]
