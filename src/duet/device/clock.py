"""Clock sync between the Hub and a device (spec §5.10 FR-D2).

NTP-style: the Hub sends ``t1``; the device stamps arrival ``t2`` and departure ``t3``
on its clock; the Hub stamps arrival ``t4``. Then

    offset = ((t2 - t1) + (t3 - t4)) / 2      device clock minus Hub clock
    delay  = (t4 - t1) - (t3 - t2)            round trip on the wire

The sample with the smallest delay is the most trustworthy, so it wins.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


def hub_now_us() -> int:
    """The Hub clock: monotonic microseconds. Everything on the Hub uses this one."""
    return time.monotonic_ns() // 1000


@dataclass(frozen=True)
class SyncSample:
    t1: int
    t2: int
    t3: int
    t4: int

    @property
    def offset_us(self) -> float:
        return ((self.t2 - self.t1) + (self.t3 - self.t4)) / 2

    @property
    def delay_us(self) -> int:
        return (self.t4 - self.t1) - (self.t3 - self.t2)


@dataclass(frozen=True)
class ClockSync:
    offset_us: int
    delay_us: int
    samples: int

    @property
    def error_bound_us(self) -> float:
        """The true offset is within this of ``offset_us`` (half the best round trip)."""
        return self.delay_us / 2

    def to_device(self, hub_us: int) -> int:
        return hub_us + self.offset_us

    def to_hub(self, device_us: int) -> int:
        return device_us - self.offset_us


def best_sync(samples: list[SyncSample]) -> ClockSync:
    if not samples:
        raise ValueError("no clock sync samples")
    best = min(samples, key=lambda s: s.delay_us)
    return ClockSync(round(best.offset_us), best.delay_us, len(samples))
