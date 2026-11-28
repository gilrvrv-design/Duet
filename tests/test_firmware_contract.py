"""Contract test (spec §9.5): the firmware core and the Hub agree on what a
performance does. Builds the native firmware CLI, feeds it the Hub's real command
stream, and compares its strikes with the Python simulator's."""

import json
import shutil
import subprocess

import pytest

from duet.conductor import VirtualClock, perform
from duet.profile import keyboard_profile, robot_profile
from duet.protocol import Home, MoveAt, StrikeAt
from duet.repair import repair_robot
from duet.score import load_score
from duet.sim import SimulatedRig
from helpers import ROOT, make_score

FIRMWARE = ROOT / "firmware"
pytestmark = pytest.mark.skipif(shutil.which("g++") is None, reason="needs a C++ compiler")


class Recorder:
    def __init__(self):
        self.messages = []

    def send(self, msg):
        self.messages.append(msg)


@pytest.fixture(scope="module")
def firmware_cli():
    subprocess.run(["make", "-s", "-C", str(FIRMWARE), "build/duet_core_cli"], check=True)
    return FIRMWARE / "build" / "duet_core_cli"


def hub_messages(score):
    recorder = Recorder()
    perform(score, robot_profile(), keyboard_profile(), [recorder], VirtualClock(5_000_000))
    return recorder.messages


def run_firmware(cli, messages, *args) -> str:
    """Run the firmware core on messages. Args: lookahead_us, heartbeat_us."""
    lines = "\n".join(m.to_json() for m in messages)
    return subprocess.run(
        [str(cli), *args], input=lines, capture_output=True, text=True, check=True
    ).stdout


def playable(robot=(), pianist=(), tempo=100):
    return repair_robot(make_score(robot, pianist, tempo), robot_profile()).score


@pytest.mark.parametrize(
    "score",
    [
        load_score(ROOT / "examples" / "rain-on-the-bottles.json"),
        # Big jumps, made playable by repair (it slows the tempo).
        playable(
            robot=[(1, 1, 0.5, "C5"), (1, 2, 0.5, "D5"), (1, 3, 0.5, "C6"), (2, 1, 0.5, "C5")],
            pianist=[(1, 1, 4, "C4")],
        ),
    ],
    ids=["example", "jumps"],
)
def test_firmware_and_hub_agree(score, firmware_cli):
    robot = robot_profile()
    messages = hub_messages(score)
    events = [json.loads(line) for line in run_firmware(firmware_cli, messages).splitlines()]
    rig = SimulatedRig(robot)
    for m in messages:
        rig.send(m)
    rig.run()

    assert [e for e in events if e["event"] == "fault"] == [] and rig.faults == []
    strikes = [e for e in events if e["event"] == "strike"]
    by_steps = {b.steps: b.midi for b in robot.notes}
    assert [by_steps[s["position"]] for s in strikes] == [s.pitch for s in rig.sounds]
    latency = round(robot.striker.latency_ms * 1000)
    for fw, hub in zip(strikes, rig.sounds, strict=True):
        assert abs((fw["t_us"] + latency) - hub.t_us) <= 100  # firmware ticks every 50 us
    assert len([e for e in events if e["event"] == "led"]) == len(rig.led_frames)
    assert events[-1]["event"] == "stats" and events[-1]["late"] == 0


def test_firmware_refuses_a_strike_before_arrival(firmware_cli):
    messages = [
        Home(),
        MoveAt(1_000_000, 46000, 500, 5000, seq=1),
        StrikeAt(1_100_000, 20000, seq=2),
    ]
    assert "NOT_ARRIVED" in run_firmware(firmware_cli, messages)


def test_heartbeats_keep_the_watchdog_quiet(firmware_cli):
    """Why the gateway sends heartbeats: without them, long moves trip the watchdog."""
    messages = hub_messages(
        playable(robot=[(1, 1, 0.5, "C5"), (1, 3, 0.5, "C6"), (2, 3, 0.5, "C5")], tempo=40)
    )
    assert "WATCHDOG" in run_firmware(firmware_cli, messages, "500000", "0")
    assert "WATCHDOG" not in run_firmware(firmware_cli, messages, "500000", "250000")


def test_firmware_limits_match_the_profile(firmware_cli):
    """The firmware's compiled-in limits (duet_config.hpp) and the profile the Hub plans
    with (bottles-v1.yaml) describe the same rig."""
    from duet.device.limits import FIRMWARE_MAX_PULSE_US, DeviceLimits, mismatches
    from duet.protocol import parse_message

    limits = DeviceLimits.from_message(
        parse_message(
            subprocess.run(
                [str(firmware_cli), "--limits"], capture_output=True, text=True, check=True
            ).stdout
        )
    )
    assert mismatches(limits, robot_profile()) == []
    assert limits.max_pulse_us == FIRMWARE_MAX_PULSE_US
    # A glockenspiel profile allows a higher duty limit than this firmware enforces.
    assert any("duty_limit" in m for m in mismatches(limits, robot_profile("glock-v1")))


def test_firmware_and_hub_know_the_same_features(firmware_cli):
    from duet.device.features import KNOWN

    out = subprocess.run(
        [str(firmware_cli), "--features"], capture_output=True, text=True, check=True
    ).stdout
    assert tuple(out.split()) == KNOWN


def fault_codes(output: str) -> list[str]:
    codes = []
    for line in output.splitlines():
        event = json.loads(line)
        if event["event"] == "fault" and event["message"]["type"] == "fault":
            codes.append(event["message"]["code"])
    return codes


@pytest.mark.parametrize(
    "messages",
    [
        [MoveAt(1_000_000, 6400, 500, 5000, seq=1)],  # no home
        [Home(), MoveAt(1_000_000, 99_999, 500, 5000, seq=1)],  # beyond travel
        [Home(), MoveAt(1_000_000, 46000, 500, 5000, seq=1), StrikeAt(1_100_000, 20000, seq=2)],
        [Home()] + [StrikeAt(1_000_000 + i * 10_000, 5000, seq=i + 1) for i in range(1000)],
        [Home()] + [StrikeAt(1_000_000 + i * 100_000, 50_000, seq=i + 1) for i in range(60)],
    ],
    ids=["not-homed", "soft-limit", "not-arrived", "short-pulse-duty", "long-pulse-duty"],
)
def test_firmware_and_simulator_refuse_the_same_things(messages, firmware_cli):
    rig = SimulatedRig(robot_profile())
    for m in messages:
        rig.send(m)
    rig.run()
    firmware = fault_codes(run_firmware(firmware_cli, messages))
    hub = [c for c in rig.fault_codes if c != "OFF_BOTTLE"]  # the firmware does not know bottles
    assert firmware == hub and firmware  # each stream breaks a rule
