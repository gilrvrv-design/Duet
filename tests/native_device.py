"""The firmware as a Linux process (firmware/host/duet_device.cpp), for tests: its serial
link over TCP, and its device API and web app over HTTP, as on the ESP32."""

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass

from duet.profile import keyboard_profile, robot_profile
from duet.score import load_score
from duet.sim import RIG_CHANNELS
from duet.songs import CompiledSong, compile_song
from helpers import ROOT

FIRMWARE = ROOT / "firmware"
BINARY = FIRMWARE / "build" / "duet_device"  # built with the optional planner module
BASIC = FIRMWARE / "build" / "duet_device_basic"  # built without it


@dataclass
class NativeDevice:
    process: subprocess.Popen
    serial_url: str  # tcp://127.0.0.1:<port>, for the Hub's DeviceGateway
    http_url: str  # http://127.0.0.1:<port>, the device API and web app

    def api(
        self, method: str, path: str, body: dict | str | bytes | None = None
    ) -> tuple[int, dict]:
        """Call the device API: the status and the JSON answer. A str or bytes body goes
        as is; a dict as JSON."""
        data = json.dumps(body) if isinstance(body, dict) else body
        data = data.encode() if isinstance(data, str) else data
        request = urllib.request.Request(self.http_url + path, data=data, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as reply:
                return reply.status, json.load(reply)
        except urllib.error.HTTPError as refused:
            return refused.code, json.load(refused)

    def store(self, slot: int, song: CompiledSong) -> None:
        """Store a song through the device API, as the web app does."""
        assert self.api("PUT", f"/api/songs/{slot}", song.song_file()) == (200, {"ok": True})

    def store_example(self, slot: int) -> CompiledSong:
        """Store examples/rain-on-the-bottles.json, compiled for the rig."""
        score = load_score(ROOT / "examples" / "rain-on-the-bottles.json")
        song = compile_song(score, robot_profile(), keyboard_profile(), RIG_CHANNELS)
        self.store(slot, song)
        return song

    def stop(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()


def start(planner: bool = True) -> NativeDevice:
    built = subprocess.run(["make", "-s", "-C", str(FIRMWARE), "device"], capture_output=True)
    assert built.returncode == 0, built.stderr.decode()
    process = subprocess.Popen(
        [str(BINARY if planner else BASIC), "--port", "0", "--http-port", "0"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    serial = int(process.stdout.readline().split()[1])  # "listening <port>"
    http = int(process.stdout.readline().split()[1])  # "http <port>"
    return NativeDevice(process, f"tcp://127.0.0.1:{serial}", f"http://127.0.0.1:{http}")
