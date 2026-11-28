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
import select
import shutil
import subprocess
import threading
import time

import pytest

import native_device
from duet.conductor import VirtualClock, one_rig, perform
from duet.device.clock import hub_now_us
from duet.device.gateway import GREET_RETRY_S, DeviceFault, DeviceGateway
from duet.performers import in_use
from duet.plans import HOME_STEPS
from duet.profile import keyboard_profile, robot_profile
from duet.protocol import Estop, Greet, Heartbeat, Home, MoveAt, StrikeAt, parse_message
from duet.score import load_score
from duet.sim import RIG_CHANNELS
from duet.songs import CompiledSong, compile_song
from helpers import ROOT, eventually, free_port, open_link

FIRMWARE = ROOT / "firmware"
QEMU_IMAGE = FIRMWARE / "build" / "qemu-flash.bin"
QEMU = os.environ.get("DUET_QEMU") or shutil.which("qemu-system-xtensa")
BOOT_TIMEOUT_S = 30  # QEMU boots in a second or two; slow machines need more
ONSET_TOLERANCE_US = 5000  # the firmware's own "late" threshold (Config::late_tolerance_us)
STRIKE = re.compile(r"^# strike t_us=(-?\d+) position=(-?\d+)")


def start_native():
    device = native_device.start()
    return device.process, device.serial_url


def start_qemu(tmp_path):
    image = tmp_path / "flash.bin"
    shutil.copy(QEMU_IMAGE, image)  # QEMU may write to flash; keep the built image clean
    port = free_port()
    process = subprocess.Popen(
        [
            QEMU,
            "-machine", "esp32",
            # As ESP-IDF's own `idf.py qemu`: emulated time is not steady enough for the
            # hardware watchdogs, which then fire at random during boot.
            "-global", "driver=timer.esp32.timg,property=wdt_disable,value=true",
            "-display", "none",
            "-monitor", "none",
            "-drive", f"file={image},if=mtd,format=raw",
            # The guest starts when the first client connects (wait=on).
            "-serial", f"tcp:127.0.0.1:{port},server=on,wait=on",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )  # fmt: skip
    wait_for_boot(port)
    return process, f"tcp://127.0.0.1:{port}"


def wait_for_boot(port: int) -> None:
    """Start the emulated chip and wait until its firmware is up (main_qemu.cpp). Bytes
    sent to a chip that is still booting crash QEMU (not a real ESP32), so nothing is
    sent until then; QEMU then takes the tests' own connection."""
    with (
        open_link("127.0.0.1", port, BOOT_TIMEOUT_S) as link,
        link.makefile("r", errors="replace") as console,
    ):
        for line in console:
            if line.startswith("# duet: ready"):
                return
    raise AssertionError("QEMU closed the link before the firmware was up")


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
    return DeviceGateway(url, timeout_s=BOOT_TIMEOUT_S, profile=robot_profile()).connect()


def steady_clock(gateway: DeviceGateway) -> bool:
    """Whether the device's clock runs at a steady rate, so the Hub can time notes on it
    to the millisecond: a real ESP32's crystal, and the native device's. QEMU's emulated
    clock speeds up and slows down with the load on the host (by about 1%), so on QEMU
    these tests check what plays and in what order, not when."""
    return gateway.hello.board != "qemu"


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
        perf = perform(
            score,
            one_rig(score, [gateway]),
            VirtualClock(hub_now_us()),
            instruments=in_use(robot, keyboard_profile()),
        )
        gateway.wait_acked()
        planned = [p for p in perf.planned if p.performer == "bot"]
        heard = wait_for_strikes(gateway, len(planned), (planned[-1].t_us - hub_now_us()) / 1e6 + 5)
        assert gateway.errors == [] and gateway.faults == []
    finally:
        gateway.close()

    assert len(heard) == len(planned)
    latency = round(robot.striker.latency_ms * 1000)  # the plan is when the bottle sounds
    errors = []
    for (t_device, position), note in zip(heard, planned, strict=True):
        assert robot.notes[robot.bottle_index(note.pitch)].steps == position  # right bottle
        errors.append(abs(gateway.sync.to_hub(t_device) + latency - note.t_us))
    if steady_clock(gateway):
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
        gateway.send(MoveAt(soon, 999_999, 500.0, 5000.0, seq=2, ch=0))  # far beyond the travel
        eventually(lambda: gateway.faults, 2, every_s=0.02)
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
    link = open_link(host, int(port), BOOT_TIMEOUT_S)
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    pending = b""

    def until(kind: str, timeout_s: float = BOOT_TIMEOUT_S):
        """The next message of this kind; None if none comes within the timeout."""
        nonlocal pending
        give_up = time.monotonic() + timeout_s
        while True:
            line, newline, rest = pending.partition(b"\n")
            if newline:
                pending = rest
                if line.startswith(b"{") and (msg := parse_message(line.decode())).type == kind:
                    return msg
                continue
            if not select.select([link], [], [], max(0, give_up - time.monotonic()))[0]:
                return None
            data = link.recv(4096)
            assert data, f"link closed before a {kind}"
            pending += data

    def send(msg) -> None:
        link.sendall(msg.to_json().encode() + b"\n")

    try:
        hello = None
        while hello is None:  # a serial link: ask for the greeting until it comes
            assert time.monotonic() < deadline + BOOT_TIMEOUT_S, "no greeting"
            send(Greet())
            hello = until("hello", timeout_s=GREET_RETRY_S)
        send(Home(seq=1))
        assert until("telemetry").homed
        # A slow, long move on the device's own clock (no clock sync on a raw link):
        # t_us 0 is in the past, so it starts at once.
        send(MoveAt(0, 40_000, 50.0, 5000.0, seq=2, ch=0))
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
    eventually(lambda: len(strikes(gateway)) >= count, timeout_s)
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
    return compile_song(score, robot_profile(), keyboard_profile(), RIG_CHANNELS)


def test_a_stored_song_plays_from_memory(device_url):
    song = example_song()
    gateway = connect(device_url)
    try:
        gateway.upload(3, song)
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
        bad = [StrikeAt(-1, 20000, ch=0)]  # before the song starts
        with pytest.raises(DeviceFault, match="bad song line"):
            gateway.upload(0, CompiledSong("bad", bad))
    finally:
        gateway.close()


def test_the_play_button_plays_without_the_hub():
    """Upload, disconnect the Hub, press the button: the song plays on its own."""
    process, url = start_native()
    song = example_song()
    try:
        gateway = connect(url)
        gateway.upload(0, song)
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


MIDI = re.compile(r"^# midi t_us=(-?\d+) bytes=(\d+),(\d+),(\d+)")


def test_the_firmware_plays_a_digital_piano_over_midi(device_url):
    """A bot on the piano: the device sends note on and off (default velocity 80)."""
    score = load_score(
        {
            "meta": {"tempo_bpm": 120},
            "parts": {"piano": {"instrument": "piano-88", "performer": "bot"}},
            "events": [
                {"part": "piano", "bar": 1, "beat": 1, "dur": 1, "pitch": "C4"},
                {"part": "piano", "bar": 1, "beat": 2, "dur": 1, "pitch": "E4"},
            ],
        }
    )
    gateway = connect(device_url)
    try:
        perf = perform(score, one_rig(score, [gateway]), VirtualClock(hub_now_us()))
        gateway.wait_acked()
        eventually(
            lambda: len(midi_out(gateway)) >= 4, (perf.planned[-1].t_us - hub_now_us()) / 1e6 + 5
        )
        sent = midi_out(gateway)
        assert gateway.errors == [] and gateway.faults == []
    finally:
        gateway.close()

    assert [b for _, b in sent] == [(0x90, 60, 80), (0x80, 60, 0), (0x90, 64, 80), (0x80, 64, 0)]
    ons = [t for t, b in sent if b[0] == 0x90]
    assert len(ons) == len(perf.planned)
    if steady_clock(gateway):
        for t_device, note in zip(ons, perf.planned, strict=True):
            assert abs(gateway.sync.to_hub(t_device) - note.t_us) < ONSET_TOLERANCE_US


def midi_out(gateway: DeviceGateway) -> list[tuple[int, tuple[int, int, int]]]:
    found = (MIDI.match(line) for line in gateway.console)
    return [(int(m[1]), (int(m[2]), int(m[3]), int(m[4]))) for m in found if m]


# Live practice (duet.live) -----------------------------------------------------------

SHORT = {
    "meta": {"tempo_bpm": 120},
    "events": [
        {"part": "robot", "bar": 1, "beat": b, "dur": 1, "pitch": p}
        for b, p in [(1, "C5"), (2, "D5"), (3, "E5"), (4, "F5")]
    ]
    + [{"part": "pianist", "bar": 2, "beat": b, "dur": 1, "pitch": "C4"} for b in (1, 3)],
}


def test_the_rig_waits_for_the_pianist(device_url):
    from duet.listening import SimulatedPianist
    from duet.live import StoppableClock, play_live, summary

    keys = SimulatedPianist(reaction_s=0.4)
    perf = play_live(
        load_score(SHORT), device_url, robot_profile(), in_use(robot_profile(), keyboard_profile()),
        mode="wait", keys=keys, clock=StoppableClock(),
    )  # fmt: skip
    assert perf.waited_us > 0  # it waited for each of the pianist's two notes
    assert [n.pitch for n in keys.played] == [60, 60]
    assert summary(perf, "wait").startswith("waited ")


def test_a_live_performance_stops_and_the_rig_goes_quiet():
    """Stopped mid-piece: the rig clears what the Hub queued, and no strike follows."""
    from duet.live import StoppableClock, Stopped, play_live

    device = native_device.start()
    heard: list[float] = []  # when each strike was reported, Hub time
    playing = threading.Event()

    def listen() -> None:
        for line in device.process.stdout:
            if STRIKE.match(line):
                heard.append(time.monotonic())
                playing.set()

    threading.Thread(target=listen, daemon=True).start()
    long = load_score(
        {
            "meta": {"tempo_bpm": 60},
            "events": [
                {"part": "robot", "bar": 1 + i // 4, "beat": 1 + i % 4, "dur": 1, "pitch": "C5"}
                for i in range(20)
            ],
        }
    )
    clock = StoppableClock()
    stopped_at: list[float] = []

    def stop_soon(gateway) -> None:
        def stop() -> None:  # a second and a half into the music
            playing.wait(timeout=30)
            time.sleep(1.5)
            stopped_at.append(time.monotonic())
            clock.stop()

        threading.Thread(target=stop, daemon=True).start()

    try:
        with pytest.raises(Stopped):
            play_live(
                long, device.serial_url, robot_profile(), in_use(robot_profile()),
                mode="play", keys=None, clock=clock, on_connect=stop_soon,
            )  # fmt: skip
        time.sleep(2)  # the strikes queued half a second ahead would have played by now
    finally:
        device.stop()
    assert heard, "it played before it was stopped"
    assert all(t < stopped_at[0] + 0.2 for t in heard), "a strike after the stop"
