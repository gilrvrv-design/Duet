"""Songs stored on the device, to play without the Hub ("play from memory").

The Hub does all the thinking once: it compiles a score into the same timed commands
it would stream live (moves, strikes, LED frames, count-in included), with times
counted from the song's start, and uploads them. The device homes, then plays them
from its own clock (firmware/lib/duet_core/src/duet_device.hpp).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from duet.conductor import build_messages
from duet.plans import HOME_STEPS
from duet.profile import KeyboardProfile, RobotProfile
from duet.protocol import Message, message_time_us
from duet.score import DuetScore

SLOTS = 8  # firmware kSongSlots
MAX_LINES = 4000  # firmware kMaxSongLines


class SongError(ValueError):
    """The score cannot be stored as a song."""


@dataclass(frozen=True)
class CompiledSong:
    title: str
    commands: list[Message]  # timed commands, t_us from 0, in time order

    @property
    def duration_s(self) -> float:
        return message_time_us(self.commands[-1]) / 1e6 if self.commands else 0.0


def compile_song(
    score: DuetScore, robot: RobotProfile, keyboard: KeyboardProfile, count_in: bool = True
) -> CompiledSong:
    """The commands a live performance would send, from the home position, shifted so
    the first one is at t_us 0. The robot part must already be playable."""
    messages, _ = build_messages(score, robot, keyboard, 0, HOME_STEPS, count_in)
    if not messages:
        raise SongError("the score has nothing to play")
    if len(messages) > MAX_LINES:
        raise SongError(f"{len(messages)} commands; a stored song holds at most {MAX_LINES}")
    first = message_time_us(messages[0])
    commands = [replace(m, t_us=message_time_us(m) - first, seq=i) for i, m in enumerate(messages)]
    return CompiledSong(score.meta.title, commands)


def check_slot(slot: int) -> int:
    if not 0 <= slot < SLOTS:
        raise SongError(f"slot {slot} is outside 0..{SLOTS - 1}")
    return slot
