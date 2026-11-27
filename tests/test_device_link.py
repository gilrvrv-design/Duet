import asyncio
import threading
import time

import pytest

from duet.conductor import VirtualClock, perform
from duet.device.clock import SyncSample, best_sync, hub_now_us
from duet.device.gateway import DeviceGateway
from duet.device.sim_server import SimulatedDevice
from duet.profile import keyboard_profile, robot_profile
from duet.protocol import (
    Ack,
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
        MoveAt(10, 6400, 500.0, 5000.0, seq=2),
        StrikeAt(20, 15000, seq=3),
        LedFrameAt(30, 4, 2, (255, 0, 0), seq=4),
        Estop(),
        Hello(device_id="d", profile="bottles-v1"),
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
    options = getattr(request, "param", {})
    sim = SimulatedDevice(clock_offset_us=987_654_321, **options)
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    port = {}

    def started(p):
        port["value"] = p
        ready.set()

    task = loop.create_task(sim.serve(port=0, ready=started))
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    assert ready.wait(5)
    yield sim, f"ws://127.0.0.1:{port['value']}"

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
        perf = perform(score, robot, piano, [gateway], VirtualClock(hub_now_us()))
        gateway.wait_acked()
        assert gateway.errors == []
    sim.rig.run()
    assert sim.rig.faults == []
    planned = [p for p in perf.planned if p.part == "robot"]
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
    assert "connected to sim-1" in out and "errors: 0" in out


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
        perf = perform(score, robot_profile(), keyboard_profile(), [gateway], RealClock())
        gateway.wait_acked()
        assert gateway.telemetry.homed
    assert perf.start_us - sent_home > 600_000  # the count-in started after homing
    assert sim.early_commands == 0
