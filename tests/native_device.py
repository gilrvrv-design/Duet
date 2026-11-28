"""The firmware as a Linux process (firmware/host/duet_device.cpp), for tests: its serial
link over TCP, and its device API and web app over HTTP, as on the ESP32."""

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass

from helpers import ROOT

FIRMWARE = ROOT / "firmware"
BINARY = FIRMWARE / "build" / "duet_device"


@dataclass
class NativeDevice:
    process: subprocess.Popen
    serial_url: str  # tcp://127.0.0.1:<port>, for the Hub's DeviceGateway
    http_url: str  # http://127.0.0.1:<port>, the device API and web app

    def press(self) -> None:
        """Press the play button."""
        self.process.stdin.write("press\n")
        self.process.stdin.flush()

    def api(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        """Call the device API: the status and the JSON answer."""
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.http_url + path, data=data, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as reply:
                return reply.status, json.load(reply)
        except urllib.error.HTTPError as refused:
            return refused.code, json.load(refused)

    def stop(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()


def start() -> NativeDevice:
    built = subprocess.run(["make", "-s", "-C", str(FIRMWARE), "device"], capture_output=True)
    assert built.returncode == 0, built.stderr.decode()
    process = subprocess.Popen(
        [str(BINARY), "--port", "0", "--http-port", "0"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    serial = int(process.stdout.readline().split()[1])  # "listening <port>"
    http = int(process.stdout.readline().split()[1])  # "http <port>"
    return NativeDevice(process, f"tcp://127.0.0.1:{serial}", f"http://127.0.0.1:{http}")
