"""The real firmware on an emulated ESP32 (Espressif's QEMU), driven by the Hub.

This runs the compiled ESP32 image (firmware/src/main_qemu.cpp: the real core on the
chip's own CPU, clock and serial port, with simulated motor, solenoid and LEDs) and plays
a score through the same DeviceGateway the rig uses, over the emulated serial port.

Needs two things, so it is skipped without them (see firmware/QEMU.md):
- the image:  make -C firmware qemu-image
- QEMU:       qemu-system-xtensa on PATH, or DUET_QEMU=/path/to/qemu-system-xtensa
"""

import os
import re
import shutil
import socket
import subprocess
import time

import pytest

from duet.conductor import VirtualClock, perform
from duet.device.clock import hub_now_us
from duet.device.gateway import DeviceFault, DeviceGateway
from duet.profile import keyboard_profile, robot_profile
from duet.protocol import Estop, Home
from duet.score import load_score
from helpers import ROOT

IMAGE = ROOT / "firmware" / "build" / "qemu-flash.bin"
QEMU = os.environ.get("DUET_QEMU") or shutil.which("qemu-system-xtensa")
BOOT_TIMEOUT_S = 30  # QEMU boots the ESP32 in a second or two; slow CI machines need more
STRIKE = re.compile(r"^# strike t_us=(-?\d+) position=(-?\d+)")
ONSET_TOLERANCE_US = 5000  # the firmware's own "late" threshold (Config::late_tolerance_us)

pytestmark = pytest.mark.skipif(
    not (QEMU and IMAGE.is_file()),
    reason="needs firmware/build/qemu-flash.bin and qemu-system-xtensa (see firmware/QEMU.md)",
)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def esp32(tmp_path):
    """A booting emulated ESP32; yields the tcp:// URL of its serial port."""
    image = tmp_path / "flash.bin"
    shutil.copy(IMAGE, image)  # QEMU may write to flash; keep the built image clean
    port = free_port()
    qemu = subprocess.Popen(
        [
            QEMU,
            "-machine", "esp32",
            "-display", "none",
            "-monitor", "none",
            "-drive", f"file={image},if=mtd,format=raw",
            # The guest starts only when the Hub connects, so hello is never missed.
            "-serial", f"tcp:127.0.0.1:{port},server=on,wait=on",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )  # fmt: skip
    try:
        yield f"tcp://127.0.0.1:{port}"
    finally:
        qemu.terminate()
        try:
            qemu.wait(timeout=10)
        except subprocess.TimeoutExpired:
            qemu.kill()


def connect(url: str) -> DeviceGateway:
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while True:  # QEMU opens its port a moment after it starts
        try:
            return DeviceGateway(url, timeout_s=BOOT_TIMEOUT_S, profile=robot_profile()).connect()
        except (ConnectionRefusedError, OSError):
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)


def strikes(gateway: DeviceGateway) -> list[tuple[int, int]]:
    found = (STRIKE.match(line) for line in gateway.console)
    return [(int(m[1]), int(m[2])) for m in found if m]


def test_the_firmware_plays_a_score_on_time(esp32):
    robot = robot_profile()
    score = load_score(ROOT / "examples" / "rain-on-the-bottles.json")
    gateway = connect(esp32)
    try:
        assert gateway.hello.device_id == "duet-rig-1"  # the real firmware said hello
        perf = perform(score, robot, keyboard_profile(), [gateway], VirtualClock(hub_now_us()))
        gateway.wait_acked()
        planned = [p for p in perf.planned if p.part == "robot"]
        deadline = time.monotonic() + (planned[-1].t_us - hub_now_us()) / 1e6 + 5
        while len(strikes(gateway)) < len(planned) and time.monotonic() < deadline:
            time.sleep(0.1)
        heard = strikes(gateway)
        assert gateway.errors == [] and gateway.faults == []
    finally:
        gateway.close()

    assert len(heard) == len(planned)
    latency = round(robot.striker.latency_ms * 1000)  # the plan is when the bottle sounds
    errors = []
    for (t_device, position), note in zip(heard, planned, strict=True):
        assert robot.notes[robot.bottle_index(note.pitch)].steps == position  # right bottle
        errors.append(abs(gateway.sync.to_hub(t_device) + latency - note.t_us))
    assert max(errors) < ONSET_TOLERANCE_US, f"onset errors (us): {errors}"


def test_the_firmware_latches_an_emergency_stop(esp32):
    gateway = connect(esp32)
    try:
        gateway.send(Home(seq=1))
        gateway.wait_ready(timeout_s=10)  # the simulated carriage finds home
        gateway.send(Estop(seq=2))
        gateway.send(Home(seq=3))
        with pytest.raises(DeviceFault, match="seq 3: error: emergency stop"):
            gateway.wait_acked()
    finally:
        gateway.close()
