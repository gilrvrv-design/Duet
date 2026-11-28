"""The full loop: the Hub drives the real firmware core over its serial link.

The same tests run against two devices:

- native: the firmware as a Linux process (firmware/host/duet_device.cpp), built with
  ``make -C firmware device``. Always runs; part of ``make check``.
- qemu: the compiled ESP32 image on Espressif's emulator (firmware/src/main_qemu.cpp).
  Runs when ``firmware/build/qemu-flash.bin`` and QEMU are there (see firmware/QEMU.md).

Both use the firmware's own executor, framing and safety rules, with stubbed hardware
that always works (duet_report_hal.hpp): a carriage that always arrives, a solenoid and
LED strip that report what they did as '#' lines. The Hub side is the real
DeviceGateway and conductor, so this checks what unit tests on either side cannot:
that both agree, in real time, about clocks, messages, acknowledgements and faults.
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
from duet.plans import HOME_STEPS
from duet.profile import keyboard_profile, robot_profile
from duet.protocol import Estop, Heartbeat, Home, MoveAt, StrikeAt, parse_message
from duet.score import load_score
from duet.songs import compile_song
from helpers import ROOT

FIRMWARE = ROOT / "firmware"
NATIVE = FIRMWARE / "build" / "duet_device"
QEMU_IMAGE = FIRMWARE / "build" / "qemu-flash.bin"
QEMU = os.environ.get("DUET_QEMU") or shutil.which("qemu-system-xtensa")
BOOT_TIMEOUT_S = 30  # QEMU boots in a second or two; slow machines need more
ONSET_TOLERANCE_US = 5000  # the firmware's own "late" threshold (Config::late_tolerance_us)
STRIKE = re.compile(r"^# strike t_us=(-?\d+) position=(-?\d+)")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_native():
    built = subprocess.run(["make", "-s", "-C", str(FIRMWARE), "device"], capture_output=True)
    assert built.returncode == 0, built.stderr.decode()
    process = subprocess.Popen(
        [str(NATIVE), "--port", "0"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )
    port = int(process.stdout.readline().split()[1])  # "listening <port>"
    return process, f"tcp://127.0.0.1:{port}"


def start_qemu(tmp_path):
    image = tmp_path / "flash.bin"
    shutil.copy(QEMU_IMAGE, image)  # QEMU may write to flash; keep the built image clean
    port = free_port()
    process = subprocess.Popen(
        [
            QEMU,
            "-machine", "esp32",
            "-display", "none",
            "-monitor", "none",
            "-drive", f"file={image},if=mtd,format=raw",
            # The guest starts only when the Hub connects, so hello is never missed.
            "-serial", f"tcp:127.0.0.1:{port},server=on,wait=on",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )  # fmt: skip
    return process, f"tcp://127.0.0.1:{port}"


QEMU_READY = bool(QEMU and QEMU_IMAGE.is_file())


@pytest.fixture(
    params=[
        "native",
        pytest.param(
            "qemu",
            marks=pytest.mark.skipif(
                not QEMU_READY,
                reason="needs firmware/build/qemu-flash.bin and qemu-system-xtensa "
                "(see firmware/QEMU.md)",
            ),
        ),
    ]
)
def device_url(request, tmp_path):
    """A running firmware; yields the tcp:// URL of its serial link."""
    process, url = start_native() if request.param == "native" else start_qemu(tmp_path)
    try:
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def connect(url: str) -> DeviceGateway:
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while True:  # QEMU opens its port a moment after it starts
        try:
            return DeviceGateway(url, timeout_s=BOOT_TIMEOUT_S, profile=robot_profile()).connect()
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)


def strikes(gateway: DeviceGateway) -> list[tuple[int, int]]:
    found = (STRIKE.match(line) for line in gateway.console)
    return [(int(m[1]), int(m[2])) for m in found if m]


def test_the_firmware_plays_a_score_on_time(device_url):
    robot = robot_profile()
    score = load_score(ROOT / "examples" / "rain-on-the-bottles.json")
    gateway = connect(device_url)
    try:
        assert gateway.hello.device_id == "duet-rig-1"  # the firmware's own hello
        assert gateway.hello.board in ("native", "qemu")
        assert gateway.limits.travel_steps == 48000
        perf = perform(score, robot, keyboard_profile(), [gateway], VirtualClock(hub_now_us()))
        gateway.wait_acked()
        planned = [p for p in perf.planned if p.part == "robot"]
        deadline = time.monotonic() + (planned[-1].t_us - hub_now_us()) / 1e6 + 5
        while len(strikes(gateway)) < len(planned) and time.monotonic() < deadline:
            time.sleep(0.05)
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


def test_the_firmware_latches_an_emergency_stop(device_url):
    gateway = connect(device_url)
    try:
        gateway.send(Home(seq=1))
        gateway.wait_ready(timeout_s=10)  # the stubbed carriage finds home
        gateway.send(Estop(seq=2))
        gateway.send(Home(seq=3))
        with pytest.raises(DeviceFault, match="seq 3: error: emergency stop"):
            gateway.wait_acked()
    finally:
        gateway.close()


def test_a_move_past_the_end_is_refused_and_the_music_goes_on(device_url):
    gateway = connect(device_url)
    try:
        gateway.send(Home(seq=1))
        gateway.wait_ready(timeout_s=10)
        soon = hub_now_us() + 100_000
        gateway.send(MoveAt(soon, 999_999, 500.0, 5000.0, seq=2))  # far beyond the travel
        deadline = time.monotonic() + 2
        while not gateway.faults and time.monotonic() < deadline:
            time.sleep(0.02)
        assert [f.code for f in gateway.faults] == ["SOFT_LIMIT"]
        gateway.send(Home(seq=3))  # a refused move is not fatal: the link carries on
        gateway.wait_acked()
    finally:
        gateway.close()


def test_the_firmware_stops_when_the_hub_goes_silent(device_url):
    """The watchdog (FR-D6): a moving carriage stops if the Hub is silent for 1 s.

    Raw socket on purpose: the gateway's heartbeats would keep the device happy."""
    _, address = device_url.split("://")
    host, port = address.split(":")
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while True:
        try:
            link = socket.create_connection((host, int(port)), timeout=BOOT_TIMEOUT_S)
            break
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)
    reader = link.makefile("r")

    def until(kind: str):
        while True:
            line = reader.readline()
            assert line, f"link closed before a {kind}"
            if line.startswith("{"):
                msg = parse_message(line)
                if msg.type == kind:
                    return msg

    def send(msg) -> None:
        link.sendall(msg.to_json().encode() + b"\n")

    try:
        hello = until("hello")
        send(Home(seq=1))
        assert until("telemetry").homed
        # A slow, long move on the device's own clock (no clock sync on a raw link):
        # t_us 0 is in the past, so it starts at once.
        send(MoveAt(0, 40_000, 50.0, 5000.0, seq=2))
        send(Heartbeat())
        started = time.monotonic()
        fault = until("fault")
        assert fault.code == "WATCHDOG"
        assert 0.8 < time.monotonic() - started < 3.0
        assert not until("telemetry").homed  # the position is no longer trusted
        assert hello.device_id == "duet-rig-1"
    finally:
        link.close()


# Play from memory ----------------------------------------------------------------


def wait_for_strikes(gateway: DeviceGateway, count: int, timeout_s: float) -> list:
    deadline = time.monotonic() + timeout_s
    while len(strikes(gateway)) < count and time.monotonic() < deadline:
        time.sleep(0.05)
    return strikes(gateway)


def check_song_timing(heard: list[tuple[int, int]], song) -> None:
    """Strikes on the right bottles, spaced exactly as the compiled song says."""
    planned = [m for m in song.commands if isinstance(m, StrikeAt)]
    assert len(heard) == len(planned)
    moves = {}  # strike time -> the target of the move before it
    target = None
    for m in song.commands:
        if isinstance(m, MoveAt):
            target = m.target_steps
        elif isinstance(m, StrikeAt):
            moves[m.t_us] = target
    t0_device, t0_song = heard[0][0], planned[0].t_us
    for (t_device, position), strike in zip(heard, planned, strict=True):
        target = moves[strike.t_us]
        assert position == (HOME_STEPS if target is None else target)  # the right bottle
        error = abs((t_device - t0_device) - (strike.t_us - t0_song))
        assert error < ONSET_TOLERANCE_US, f"strike {strike.seq} off by {error} us"


def example_song():
    score = load_score(ROOT / "examples" / "rain-on-the-bottles.json")
    return compile_song(score, robot_profile(), keyboard_profile())


def test_a_stored_song_plays_from_memory(device_url):
    song = example_song()
    gateway = connect(device_url)
    try:
        gateway.upload(3, song.commands)
        assert strikes(gateway) == []  # stored, not played
        gateway.play(3)
        heard = wait_for_strikes(gateway, 9, timeout_s=song.duration_s + 10)
        assert gateway.errors == [] and gateway.faults == []
    finally:
        gateway.close()
    check_song_timing(heard, song)


def test_bad_songs_and_plays_are_refused(device_url):
    gateway = connect(device_url)
    try:
        with pytest.raises(DeviceFault, match="no song in that slot"):
            gateway.play(5)
    finally:
        gateway.close()
    gateway = connect(device_url)
    try:
        bad = [StrikeAt(-1, 20000)]  # before the song starts
        with pytest.raises(DeviceFault, match="bad song line"):
            gateway.upload(0, bad)
    finally:
        gateway.close()


def test_the_play_button_plays_without_the_hub():
    """Upload, disconnect the Hub, press the button: the song plays on its own."""
    process, url = start_native()
    song = example_song()
    try:
        gateway = connect(url)
        gateway.upload(0, song.commands)
        gateway.close()  # no Hub from here on
        process.stdin.write("press\n")
        process.stdin.flush()
        heard = []
        deadline = time.monotonic() + song.duration_s + 10  # homing, the lead, the song
        while len(heard) < 9 and time.monotonic() < deadline:
            match = STRIKE.match(process.stdout.readline())
            if match:
                heard.append((int(match[1]), int(match[2])))
    finally:
        process.terminate()
        process.wait(timeout=10)
    check_song_timing(heard, song)


def test_cli_upload_and_play(capsys):
    from duet.cli import main

    process, url = start_native()
    example = str(ROOT / "examples" / "rain-on-the-bottles.json")
    try:
        assert main(["upload", example, "--device", url, "--slot", "2", "--play"]) == 0
        out = capsys.readouterr().out
        assert "stored 'Rain on the Bottles' in slot 2" in out and "playing from memory" in out
        assert main(["upload", example, "--device", url, "--slot", "9"]) == 2
        assert "slot 9 is outside 0..7" in capsys.readouterr().err
    finally:
        process.terminate()
        process.wait(timeout=10)
