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
