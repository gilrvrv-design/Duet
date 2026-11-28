"""The device API over HTTP, on the native device: what the web app asks the rig."""

import time

from duet.midi_io import score_to_midi_bytes
from duet.profile import keyboard_profile, robot_profile
from duet.score import load_score
from duet.sim import RIG_CHANNELS
from duet.songs import compile_song
from helpers import ROOT


def wait_for_state(device, state, timeout_s=10):
    deadline = time.monotonic() + timeout_s
    while (info := device.api("GET", "/api/info")[1])["state"] != state:
        assert time.monotonic() < deadline, f"still {info['state']}"
        time.sleep(0.05)
    return info


def test_info_is_what_the_hub_hears(device):
    status, info = device.api("GET", "/api/info")
    assert status == 200
    assert info["hello"]["board"] == "native" and info["hello"]["protocol"] == 4
    assert [c["kind"] for c in info["channels"]] == ["carriage_striker", "led_strip", "midi_out"]
    assert info["channels"][0]["travel_steps"] == 48000
    assert (info["state"], info["slot"], info["estopped"]) == ("idle", -1, False)


def test_the_app_plays_a_stored_song_and_stops_it(device):
    assert device.api("GET", "/api/songs") == (200, {"slots": 8, "songs": []})
    device.store_example(4)
    assert device.api("GET", "/api/songs")[1]["songs"] == [
        {"slot": 4, "title": "Rain on the Bottles"}
    ]

    assert device.api("POST", "/api/songs/4/play") == (200, {"ok": True})
    info = wait_for_state(device, "playing")
    assert info["slot"] == 4
    assert device.api("POST", "/api/songs/4/play") == (409, {"error": "already playing"})
    assert device.api("POST", "/api/stop") == (200, {"ok": True})
    wait_for_state(device, "idle", timeout_s=1)


def test_the_app_can_stop_the_rig(device):
    device.store_example(0)
    assert device.api("POST", "/api/estop") == (200, {"ok": True})
    assert device.api("GET", "/api/info")[1]["estopped"] is True
    assert device.api("POST", "/api/songs/0/play") == (409, {"error": "emergency stop"})


def test_unknown_paths_and_wrong_methods(device):
    assert device.api("GET", "/api/nope") == (404, {"error": "no such path"})
    assert device.api("POST", "/api/info") == (405, {"error": "use GET"})
    assert device.api("GET", "/api/stop") == (405, {"error": "use POST"})


def test_wifi_setup(device):
    """A new board has no Wi-Fi: it serves its setup network until one is saved."""
    assert device.api("GET", "/api/info")[1]["network"] == "setup"
    assert device.api("GET", "/api/settings")[1] == {
        "wifi_ssid": "",
        "wifi_password_set": False,
        "servers": [],
    }
    home = {"wifi_ssid": "Home", "wifi_password": "correct horse", "servers": []}
    assert device.api("POST", "/api/settings", home) == (200, {"ok": True, "restart": True})
    assert device.api("GET", "/api/info")[1]["network"] == "station"  # restarted, joined
    servers = {"wifi_ssid": "Home", "servers": ["https://duet.example"]}
    assert device.api("POST", "/api/settings", servers) == (200, {"ok": True})  # no restart
    assert device.api("GET", "/api/settings")[1] == {
        "wifi_ssid": "Home",
        "wifi_password_set": True,  # kept, and never sent back
        "servers": ["https://duet.example"],
    }
    short = {"wifi_ssid": "Home", "wifi_password": "short", "servers": []}
    status, answer = device.api("POST", "/api/settings", short)
    assert status == 400 and "8-63 characters" in answer["error"]


def test_a_song_file_is_stored_through_the_api_and_plays(device):
    score = load_score(ROOT / "examples" / "rain-on-the-bottles.json")
    song = compile_song(score, robot_profile(), keyboard_profile(), RIG_CHANNELS)
    assert device.api("PUT", "/api/songs/7", song.song_file()) == (200, {"ok": True})
    assert device.api("GET", "/api/songs")[1]["songs"] == [
        {"slot": 7, "title": "Rain on the Bottles"}
    ]
    assert device.api("POST", "/api/songs/7/play") == (200, {"ok": True})
    wait_for_state(device, "playing")
    device.api("POST", "/api/stop")

    broken = song.song_file().replace('"t_us":', '"t_us":-1', 1)  # line 2: before 0
    assert device.api("PUT", "/api/songs/7", broken) == (400, {"error": "bad song line 2"})
    assert device.api("DELETE", "/api/songs/7") == (200, {"ok": True})
    assert device.api("GET", "/api/songs")[1]["songs"] == []


def test_a_midi_file_is_planned_on_a_board_with_the_planner(device, basic_device):
    rain = score_to_midi_bytes(load_score(ROOT / "examples" / "rain-on-the-bottles.json"))
    assert device.api("PUT", "/api/songs/2/midi?title=Rain%20%E2%99%AA", rain) == (
        200,
        {"ok": True, "warnings": []},
    )
    assert device.api("GET", "/api/songs")[1]["songs"] == [{"slot": 2, "title": "Rain ♪"}]
    assert device.api("POST", "/api/songs/2/play") == (200, {"ok": True})
    wait_for_state(device, "playing")
    assert "planner" in device.api("GET", "/api/info")[1]["hello"]["features"]

    assert basic_device.api("PUT", "/api/songs/2/midi?title=Rain", rain) == (
        404,
        {"error": "this board has no MIDI planner"},
    )
    assert "planner" not in basic_device.api("GET", "/api/info")[1]["hello"]["features"]
