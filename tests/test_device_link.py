import asyncio
import threading
import time

import pytest

from duet.conductor import VirtualClock, one_rig, perform
from duet.device.clock import SyncSample, best_sync, hub_now_us
from duet.device.gateway import DeviceFault, DeviceGateway, DeviceMismatch
from duet.device.sim_server import SimulatedDevice
from duet.performers import in_use
from duet.profile import keyboard_profile, robot_profile
from duet.protocol import (
    Ack,
    Channel,
    Estop,
    Fault,
    Heartbeat,
    Hello,
    Home,
    LedFrameAt,
    MoveAt,
    StrikeAt,
    Telemetry,
    TimePing,
    TimePong,
    parse_message,
)
from duet.score import load_score
from helpers import ROOT


def test_offset_and_delay_maths():
    # Device clock is 1000 us ahead; 100 us each way on the wire; 10 us inside the device.
    sample = SyncSample(t1=0, t2=1100, t3=1110, t4=210)
    assert sample.offset_us == 1000 and sample.delay_us == 200
    noisy = SyncSample(t1=0, t2=1900, t3=1910, t4=1010)  # slow outbound leg
    sync = best_sync([noisy, sample])
    assert (sync.offset_us, sync.delay_us, sync.samples) == (1000, 200, 2)
    assert sync.to_hub(sync.to_device(5)) == 5 and sync.error_bound_us == 100
    with pytest.raises(ValueError):
        best_sync([])


@pytest.mark.parametrize(
    "msg",
    [
        Home(seq=1),
        MoveAt(10, 6400, 500.0, 5000.0, seq=2, ch=0),
        StrikeAt(20, 15000, seq=3, ch=0),
        LedFrameAt(30, 4, 2, (255, 0, 0), seq=4, ch=1),
        Estop(),
        Hello(device_id="d", board="esp32-s3", profile="bottles-v1", features=("wifi", "flash")),
        Channel(ch=0, kind="carriage_striker", steps_per_mm=80.0, travel_steps=48000),
        Channel(ch=1, kind="led_strip", count=176),
        StrikeAt(20, 15000, seq=3, ch=0),
        TimePing(5),
        TimePong(5, 6, 7),
        Ack(seq=9, status="ok"),
        Fault(code="STALL", detail="lost steps"),
        Heartbeat(),
        Telemetry(homed=True, position=1200, queued=3),
    ],
)
def test_messages_round_trip(msg):
    assert parse_message(msg.to_json()) == msg


def test_unknown_message():
    with pytest.raises(ValueError, match="unknown message type"):
        parse_message('{"type": "dance"}')


@pytest.fixture
def device(request):
    options = dict(getattr(request, "param", {}))
    lines = options.pop("_lines", False)
    sim = SimulatedDevice(clock_offset_us=987_654_321, **options)
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    port = {}

    def started(p):
        port["value"] = p
        ready.set()

    serve = sim.serve_lines if lines else sim.serve
    task = loop.create_task(serve(port=0, ready=started))
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    assert ready.wait(5)
    yield sim, f"{'tcp' if lines else 'ws'}://127.0.0.1:{port['value']}"

    async def stop():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run_coroutine_threadsafe(stop(), loop).result(5)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(5)
    loop.close()


def test_clock_sync_over_a_real_socket(device):
    sim, url = device
    with DeviceGateway(url) as gateway:
        assert gateway.hello.device_id == "sim-1"
        error = abs(gateway.sync.offset_us - sim.clock_offset_us)
        assert error < 2000, f"sync error {error} us"  # spec target: under 2 ms
        assert gateway.sync.samples == 16
        time.sleep(0.6)
        assert sim.heartbeats >= 2


def test_performance_over_the_socket_lands_on_time(device):
    sim, url = device
    robot, piano = robot_profile(), keyboard_profile()
    score = load_score(ROOT / "examples" / "rain-on-the-bottles.json")
    with DeviceGateway(url) as gateway:
        # Real Hub timestamps, but no waiting: the device queues commands (FR-D4).
        perf = perform(
            score,
            one_rig(score, [gateway]),
            VirtualClock(hub_now_us()),
            instruments=in_use(robot, piano),
        )
        gateway.wait_acked()
        assert gateway.errors == []
    sim.rig.run()
    assert sim.rig.faults == []
    planned = [p for p in perf.planned if p.performer == "bot"]
    heard = [s.t_us - sim.clock_offset_us for s in sim.rig.sounds]  # back to Hub time
    assert len(heard) == len(planned) == 9
    worst = max(abs(h - p.t_us) for h, p in zip(heard, planned, strict=True))
    assert worst < 2000, f"worst onset error {worst} us"
    assert len(sim.rig.led_frames) == 22


def test_cli_play_on_device(device, capsys):
    from duet.cli import main

    _, url = device
    score = ROOT / "tests" / "data" / "two-notes.json"
    assert main(["play", str(score), "--device", url]) == 0
    out = capsys.readouterr().out
    assert "connected to sim-1" in out and "played 12 commands" in out  # errors would raise


def test_drift_estimate_maths():
    first = best_sync([SyncSample(0, 1000, 1000, 0)])
    # One second later the device is 1000 us further ahead: 1000 ppm fast.
    second = best_sync([SyncSample(1_000_000, 1_002_000, 1_002_000, 1_000_000)], previous=first)
    assert second.drift_ppm == pytest.approx(1000)
    assert second.to_device(2_000_000) == 2_000_000 + 2000 + 1000


@pytest.mark.parametrize("device", [{"drift_ppm": 2000.0}], indirect=True)
def test_periodic_resync_tracks_a_drifting_clock(device):
    sim, url = device
    with DeviceGateway(url, resync_every_s=0.25) as gateway:
        time.sleep(1.2)
        sync = gateway.sync
        assert sync.drift_ppm == pytest.approx(2000, rel=0.25)
        target = hub_now_us() + 1_000_000  # predict one second ahead
        error = abs(sync.to_device(target) - sim.true_device_time(target))
        # Without drift compensation the error here would be over 3 ms.
        assert error < 1000, f"prediction error {error:.0f} us"


@pytest.mark.parametrize("device", [{"homing_s": 0.6}], indirect=True)
def test_conductor_waits_for_slow_homing(device):
    from duet.conductor import RealClock

    sim, url = device
    score = load_score(ROOT / "tests" / "data" / "two-notes.json")
    with DeviceGateway(url) as gateway:
        sent_home = hub_now_us()
        perf = perform(
            score,
            one_rig(score, [gateway]),
            RealClock(),
            instruments=in_use(robot_profile(), keyboard_profile()),
        )
        gateway.wait_acked()
        assert gateway.telemetry.homed
    assert perf.start_us - sent_home > 600_000  # the count-in started after homing
    assert sim.early_commands == 0


def test_messages_over_the_size_limit_are_refused():
    from duet.protocol import MAX_MESSAGE_BYTES

    with pytest.raises(ValueError, match="limit 255"):
        Fault(code="X", detail="y" * MAX_MESSAGE_BYTES).to_json()


def test_two_performances_with_the_same_plan_seqs_are_acked_apart(device):
    """Plans number from 1 every time; the gateway's wire seqs keep acks apart."""
    sim, url = device
    score = load_score(ROOT / "tests" / "data" / "two-notes.json")
    with DeviceGateway(url, profile=robot_profile()) as gateway:
        for _ in range(2):
            perform(
                score,
                one_rig(score, [gateway]),
                VirtualClock(hub_now_us()),
                instruments=in_use(robot_profile(), keyboard_profile()),
            )
            gateway.wait_acked()
        assert gateway.errors == [] and not gateway._unacked
    assert sim.commands > 0


def test_an_error_ack_stops_the_performance(device):
    sim, url = device
    with DeviceGateway(url) as gateway:
        gateway.send(Estop())
        gateway.send(Home(seq=7))
        with pytest.raises(DeviceFault, match="seq 7: error: emergency stop"):
            gateway.wait_acked()
        with pytest.raises(DeviceFault):
            gateway.send(Home(seq=8))  # nothing more is sent once the device refused
    assert gateway.errors == ["seq 7: error: emergency stop"]


@pytest.mark.parametrize("device", [{"homing_fails": True, "homing_s": 0.1}], indirect=True)
def test_a_homing_fault_wakes_wait_ready_at_once(device):
    _, url = device
    with DeviceGateway(url) as gateway:
        gateway.send(Home(seq=1))
        started = time.monotonic()
        with pytest.raises(DeviceFault, match="HOMING_TIMEOUT"):
            gateway.wait_ready(timeout_s=10)
        assert time.monotonic() - started < 2  # not the full ten seconds


def test_a_lost_connection_is_raised_not_hung_on(device):
    sim, url = device
    gateway = DeviceGateway(url, resync_every_s=None).connect()
    try:
        gateway._call(gateway._ws.close())  # as if the device rebooted
        with pytest.raises(DeviceFault, match="connection closed|stopped"):
            gateway.wait_ready(timeout_s=5)
    finally:
        gateway.close()


@pytest.mark.parametrize("device", [{"profile": robot_profile("glock-v1")}], indirect=True)
def test_a_device_with_other_limits_is_refused_at_connect(device):
    _, url = device
    with pytest.raises(DeviceMismatch, match="profile: device glock-v1"):
        DeviceGateway(url, profile=robot_profile()).connect()


def test_the_simulated_device_reports_the_firmware_limits():
    from duet.device.limits import DeviceLimits, mismatches

    hello, carriage, strip, midi = SimulatedDevice().greeting()
    assert hello.board == "sim"
    assert hello.channels == 3 and strip.kind == "led_strip" and midi.kind == "midi_out"
    assert mismatches(DeviceLimits.from_channel(carriage), robot_profile()) == []


@pytest.mark.parametrize("device", [{"_lines": True}], indirect=True)
def test_a_serial_line_link_plays_like_the_websocket(device):
    """tcp:// is a serial port as lines (QEMU, ser2net); boot noise goes to the console."""
    sim, url = device
    score = load_score(ROOT / "examples" / "rain-on-the-bottles.json")
    with DeviceGateway(url, profile=robot_profile()) as gateway:
        assert gateway.hello.device_id == "sim-1"
        assert abs(gateway.sync.offset_us - sim.clock_offset_us) < 2000
        perform(
            score,
            one_rig(score, [gateway]),
            VirtualClock(hub_now_us()),
            instruments=in_use(robot_profile(), keyboard_profile()),
        )
        gateway.wait_acked()
        assert gateway.errors == []
        assert any("POWERON_RESET" in line for line in gateway.console)
    sim.rig.run()
    assert sim.rig.faults == [] and len(sim.rig.sounds) == 9


def test_line_links_need_a_host_and_port():
    import asyncio

    from duet.device.lines import LineLink

    with pytest.raises(ValueError, match="tcp://host:port"):
        asyncio.run(LineLink.open("tcp://nohost"))


@pytest.mark.parametrize("device", [{"protocol": 2}], indirect=True)
def test_a_device_on_another_protocol_is_refused_at_connect(device):
    _, url = device
    with pytest.raises(ConnectionError, match="protocol 2; this Hub speaks 5"):
        DeviceGateway(url).connect()
