"""Hub -> device messages (spec §5.10 FR-D3).

Times are microseconds on the shared Hub clock. The same messages go over
WebSocket (JSON) or serial; this module only defines them.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import ClassVar


@dataclass(frozen=True)
class Message:
    type: ClassVar[str] = ""
    seq: int = field(default=0, kw_only=True)

    def to_dict(self) -> dict:
        return {"type": self.type, **asdict(self)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))


@dataclass(frozen=True)
class Home(Message):
    type: ClassVar[str] = "home"


@dataclass(frozen=True)
class MoveAt(Message):
    type: ClassVar[str] = "move_at"
    t_us: int
    target_steps: int
    v_max_mm_s: float
    a_max_mm_s2: float


@dataclass(frozen=True)
class StrikeAt(Message):
    type: ClassVar[str] = "strike_at"
    t_us: int
    pulse_us: int


@dataclass(frozen=True)
class LedFrameAt(Message):
    type: ClassVar[str] = "led_frame_at"
    t_us: int
    first: int
    count: int
    rgb: tuple[int, int, int]


@dataclass(frozen=True)
class Estop(Message):
    type: ClassVar[str] = "estop"


TIMED = (MoveAt, StrikeAt, LedFrameAt)


def message_time_us(msg: Message) -> int:
    return getattr(msg, "t_us", 0)
