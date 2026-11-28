"""Hub <-> device messages (spec §5.10 FR-D3).

Inside the Hub, times are microseconds on the Hub clock. The gateway converts them to
the device's own clock before sending, so firmware only ever deals with its local time.
The same messages go over WebSocket (JSON) or serial; this module only defines them.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import ClassVar

MAX_MESSAGE_BYTES = 255  # same as kMaxMessage in firmware/lib/duet_core/src/duet_protocol.hpp
PROTOCOL = 4  # same as kProtocol; 4: on a serial link the Hub asks for the greeting (Greet)
CARRIAGE_STRIKER, LED_STRIP, MIDI_OUT = "carriage_striker", "led_strip", "midi_out"

# A timed command's channel is the device's business: the conductor fills it in for each
# device it sends to (its channel of the right kind). Until then it is None, which a
# device refuses ("cannot parse"), so a forgotten channel can never play by accident.
_CH = field(default=None, kw_only=True)


@dataclass(frozen=True)
class Message:
    type: ClassVar[str] = ""
    seq: int = field(default=0, kw_only=True)

    def to_dict(self) -> dict:
        return {"type": self.type, **asdict(self)}

    def to_json(self) -> str:
        text = json.dumps(self.to_dict(), separators=(",", ":"))
        if len(text.encode()) > MAX_MESSAGE_BYTES:
            raise ValueError(f"{self.type} message is {len(text)} bytes; limit {MAX_MESSAGE_BYTES}")
        return text


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
    ch: int | None = _CH


@dataclass(frozen=True)
class StrikeAt(Message):
    type: ClassVar[str] = "strike_at"
    t_us: int
    pulse_us: int
    ch: int | None = _CH


@dataclass(frozen=True)
class LedFrameAt(Message):
    type: ClassVar[str] = "led_frame_at"
    t_us: int
    first: int
    count: int
    rgb: tuple[int, int, int]
    ch: int | None = _CH


@dataclass(frozen=True)
class NoteAt(Message):
    """A MIDI note on (``vel`` > 0) or off (``vel`` 0) on MIDI channel ``midi`` (0-15)."""

    type: ClassVar[str] = "note_at"
    t_us: int
    midi: int
    pitch: int
    vel: int
    ch: int | None = _CH


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
    """Who the device is: its first message on every connection. ``channels`` channel
    messages follow, one per thing it drives."""

    type: ClassVar[str] = "hello"
    protocol: int = PROTOCOL
    device_id: str = ""
    board: str = ""
    profile: str = ""
    features: tuple[str, ...] = ()  # duet.device.features
    channels: int = 0


@dataclass(frozen=True)
class Channel(Message):
    """One thing the device drives. A carriage-striker channel carries the safety limits
    the firmware enforces; an LED strip its number of LEDs."""

    type: ClassVar[str] = "channel"
    ch: int = 0
    kind: str = ""  # CARRIAGE_STRIKER, LED_STRIP or MIDI_OUT
    count: int = 0
    steps_per_mm: float = 0.0
    travel_steps: int = 0
    duty_limit: float = 0.0
    duty_window_us: int = 0
    max_pulse_us: int = 0


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
class Song(Message):
    """Store a song on the device: the next ``lines`` timed commands, with t_us counted
    from the song's start, go into ``slot`` (0-7). Acked once, after the last line."""

    type: ClassVar[str] = "song"
    slot: int = 0
    lines: int = 0


@dataclass(frozen=True)
class Play(Message):
    """Home, then play the song stored in ``slot``, without the Hub."""

    type: ClassVar[str] = "play"
    slot: int = 0


@dataclass(frozen=True)
class Stop(Message):
    """Stop playing a stored song."""

    type: ClassVar[str] = "stop"


@dataclass(frozen=True)
class Greet(Message):
    """Ask the device for its greeting (hello, then its channels). A WebSocket device
    greets when the Hub connects; on a serial link, which has no connect, the Hub asks."""

    type: ClassVar[str] = "greet"


@dataclass(frozen=True)
class Fault(Message):
    type: ClassVar[str] = "fault"
    code: str = ""
    detail: str = ""


TIMED = (MoveAt, StrikeAt, LedFrameAt, NoteAt)
CHANNEL_KIND = {
    MoveAt: CARRIAGE_STRIKER,
    StrikeAt: CARRIAGE_STRIKER,
    LedFrameAt: LED_STRIP,
    NoteAt: MIDI_OUT,
}
MESSAGE_TYPES = {cls.type: cls for cls in Message.__subclasses__()}  # every message, by name


def parse_message(data: dict | str) -> Message:
    """Inverse of ``Message.to_dict`` / ``to_json``."""
    if isinstance(data, str):
        data = json.loads(data)
    fields = dict(data)
    cls = MESSAGE_TYPES.get(fields.pop("type", None))
    if cls is None:
        raise ValueError(f"unknown message type: {data.get('type')!r}")
    for name in ("rgb", "features"):  # JSON arrays are tuples in frozen messages
        if name in fields:
            fields[name] = tuple(fields[name])
    return cls(**fields)


def message_time_us(msg: Message) -> int:
    return getattr(msg, "t_us", 0)
