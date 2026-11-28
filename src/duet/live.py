"""Live practice on a real rig (docs/design/esp-first.md, step 6): the Hub plays a duet
on the rig while it listens to the pianist, and can be stopped at any moment.

Modes: "play" (the bot plays in time, nobody is listened to), "wait" (the bot waits for
each of the pianist's notes) and "follow" (the bot keeps the pianist's tempo). Every wait
in a performance goes through its clock, so a ``StoppableClock`` stops it cleanly; the
rig is then told to stop, which clears what it has queued (protocol 5).
"""

from __future__ import annotations

import threading

from duet.conductor import Performance, RealClock, one_rig, perform
from duet.device.gateway import DeviceGateway
from duet.listening import KeyInput, grade
from duet.performers import Instruments
from duet.profile import RobotProfile
from duet.score import DuetScore

MODES = ("play", "wait", "follow")
RING_OUT_US = 1_000_000  # after the last command is sent, the last notes still sound


class Stopped(Exception):
    """The performance was stopped before its end."""


class StoppableClock(RealClock):
    """The Hub's clock; once stopped, any wait on it raises Stopped."""

    def __init__(self) -> None:
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def sleep_until(self, t_us: int) -> None:
        if self._stop.wait(max(0.0, (t_us - self.now_us()) / 1_000_000)):
            raise Stopped


def play_live(
    score: DuetScore,
    url: str,
    robot: RobotProfile,
    instruments: Instruments,
    *,
    mode: str,
    keys: KeyInput | None,
    clock: StoppableClock,
    on_connect=lambda gateway: None,
) -> Performance:
    """Play ``score`` on the rig at ``url`` in ``mode``, hearing the pianist through ``keys``
    (wait and follow modes need them). Stopped through ``clock``, or by Ctrl-C, it stops
    the rig too and raises."""
    if mode not in MODES:
        raise ValueError(f"mode {mode!r}: choose one of {', '.join(MODES)}")
    if mode != "play" and keys is None:
        raise ValueError(f"{mode} mode listens to the pianist: give a key input")
    with DeviceGateway(url, profile=robot) as gateway:
        on_connect(gateway)
        try:
            perf = perform(
                score,
                one_rig(score, [gateway]),
                clock,
                instruments=instruments,
                keys=None if mode == "play" else keys,
                mode="wait" if mode == "play" else mode,
            )
            gateway.wait_acked()
            clock.sleep_until(clock.now_us() + RING_OUT_US)
        except (Stopped, KeyboardInterrupt):
            gateway.stop()  # the rig clears what it has queued and goes quiet
            raise
    return perf


def summary(perf: Performance, mode: str) -> str:
    """How it went, for the pianist: how long the bot waited or how it followed, and the
    grade of what was heard."""
    if mode == "play":
        return f"played {perf.messages_sent} commands"
    pace = (
        f"waited {perf.waited_us / 1e6:.1f} s for you"
        if mode == "wait"
        else f"followed you: tempo now {100 / perf.final_rate:.0f}% of written"
    )
    return f"{pace}\n{grade(perf.expected_pianist(), perf.played).feedback()}"
