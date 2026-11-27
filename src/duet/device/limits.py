"""The safety limits a rig's firmware enforces, and checking them against a profile.

The firmware reports its limits in ``hello`` (firmware/lib/duet_core/src/duet_config.hpp).
The Hub plans with an instrument profile. If they disagree, a score the Hub thinks is
playable would be refused mid-song, so the gateway checks them at connect, and the
contract test checks the firmware's defaults against ``bottles-v1``.
"""

from __future__ import annotations

from dataclasses import dataclass

from duet.profile import RobotProfile
from duet.protocol import Hello

# The firmware's per-pulse cap (Config::max_pulse_us). It is a device safety limit, not
# a musical fact, so it is not in the profile; the contract test keeps this in step.
FIRMWARE_MAX_PULSE_US = 50_000
STRIKE_HISTORY = 256  # firmware kDutySlots: strikes remembered for the duty limit


@dataclass(frozen=True)
class DeviceLimits:
    steps_per_mm: float
    travel_steps: int
    duty_limit: float
    duty_window_us: int
    max_pulse_us: int = FIRMWARE_MAX_PULSE_US

    @classmethod
    def from_profile(cls, profile: RobotProfile) -> DeviceLimits:
        return cls(
            steps_per_mm=profile.kinematics.steps_per_mm,
            travel_steps=profile.kinematics.travel_steps,
            duty_limit=profile.striker.duty_limit,
            duty_window_us=round(profile.striker.duty_window_s * 1_000_000),
        )

    @classmethod
    def from_hello(cls, hello: Hello) -> DeviceLimits:
        return cls(
            hello.steps_per_mm,
            hello.travel_steps,
            hello.duty_limit,
            hello.duty_window_us,
            hello.max_pulse_us,
        )


def mismatches(device: DeviceLimits, profile: RobotProfile) -> list[str]:
    """Where the device's limits differ from what the Hub plans with."""
    expected = DeviceLimits.from_profile(profile)
    problems = []
    for name in ("steps_per_mm", "travel_steps", "duty_limit", "duty_window_us"):
        got, want = getattr(device, name), getattr(expected, name)
        if abs(got - want) > 1e-6 * max(1.0, abs(want)):
            problems.append(f"{name}: device {got:g}, profile {profile.id} {want:g}")
    return problems
