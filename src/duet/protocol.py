"""Hub <-> device messages (spec §5.10 FR-D3).

Inside the Hub, times are microseconds on the Hub clock. The gateway converts them to
the device's own clock before sending, so firmware only ever deals with its local time.
The same messages go over WebSocket (JSON) or serial; this module only defines them.
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


@dataclass(frozen=True)
class Heartbeat(Message):
    """Proof of life from the Hub. Devices stop moving if they hear nothing for 1 s
    (FR-D6), so the gateway sends one every 250 ms. Not acknowledged."""

    type: ClassVar[str] = "heartbeat"


@dataclass(frozen=True)
class Hello(Message):
    type: ClassVar[str] = "hello"
    protocol: int = 1
    device_id: str = ""
    profile: str = ""


@dataclass(frozen=True)
class TimePing(Message):
    type: ClassVar[str] = "time_ping"
    t1: int


@dataclass(frozen=True)
class TimePong(Message):
    type: ClassVar[str] = "time_pong"
    t1: int
    t2: int  # device time the ping arrived
    t3: int  # device time the pong left


@dataclass(frozen=True)
class Ack(Message):
    type: ClassVar[str] = "ack"
    status: str = "ok"


@dataclass(frozen=True)
class Telemetry(Message):
    """Device state, sent when homing ends and whenever position trust changes."""

    type: ClassVar[str] = "telemetry"
    homed: bool = False
    position: int = 0
    queued: int = 0


@dataclass(frozen=True)
class Fault(Message):
    type: ClassVar[str] = "fault"
    code: str = ""
    detail: str = ""


TIMED = (MoveAt, StrikeAt, LedFrameAt)
MESSAGE_TYPES = {cls.type: cls for cls in Message.__subclasses__()}  # every message, by name


def parse_message(data: dict | str) -> Message:
    """Inverse of ``Message.to_dict`` / ``to_json``."""
    if isinstance(data, str):
        data = json.loads(data)
    fields = dict(data)
    cls = MESSAGE_TYPES.get(fields.pop("type", None))
    if cls is None:
        raise ValueError(f"unknown message type: {data.get('type')!r}")
    if "rgb" in fields:
        fields["rgb"] = tuple(fields["rgb"])
    return cls(**fields)


def message_time_us(msg: Message) -> int:
    return getattr(msg, "t_us", 0)
