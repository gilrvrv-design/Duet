"""Songs stored on the device, to play without the Hub ("play from memory").

The Hub does all the thinking once: it compiles a score into the same timed commands
it would stream live (moves, strikes, LED frames, count-in included), with times
counted from the song's start, and uploads them. The device homes, then plays them
from its own clock (firmware/lib/duet_core/src/duet_device.hpp).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace

from duet.conductor import build_messages
from duet.performers import Bot, Human, in_use, performers
from duet.profile import KeyboardProfile, RobotProfile
from duet.protocol import CHANNEL_KIND, TITLE_BYTES, Message, message_time_us
from duet.score import DuetScore
from duet.timing import timed_events

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

    def song_file(self) -> str:
        """The song as the device keeps it, and as its API takes it (PUT /api/songs/<k>,
        docs/device-api.md): the title line, then one command per line."""
        lines = [json.dumps({"title": self.title}, ensure_ascii=False)]
        return "\n".join(lines + [m.to_json() for m in self.commands]) + "\n"


def song_title(title: str) -> str:
    """The title as the device keeps it: one line, at most TITLE_BYTES of UTF-8."""
    line = " ".join(title.split())
    if len(line.encode()) <= TITLE_BYTES:
        return line
    cut = line.encode()[: TITLE_BYTES - len("…".encode())].decode(errors="ignore")
    return cut.rstrip() + "…"


def compile_song(
    score: DuetScore,
    robot: RobotProfile,
    keyboard: KeyboardProfile,
    channels: Mapping[str, int],
    count_in: bool = True,
) -> CompiledSong:
    """The commands a live performance would send, from the home position, shifted so
    the first one is at t_us 0, on the device's ``channels`` (kind -> number). A song
    lives on one device, which has one carriage: at most one bot part, and it must
    already be playable."""
    playing = in_use(robot, keyboard)
    carriages = [p.part for p in performers(score, playing) if isinstance(p, Bot) and p.moves]
    if len(carriages) > 1:
        raise SongError(f"a stored song plays on one device, which has one carriage: {carriages}")
    for p in (p for p in performers(score, playing) if isinstance(p, Human)):
        # The light guide shows only the keyboard's keys.
        off = [t for t in timed_events(score, p.part) if not p.profile.contains(t.event.pitch)]
        if off:
            raise SongError(f"key {off[0].event.pitch} is not on the keyboard")
    messages = build_messages(score, instruments=playing, count_in=count_in).messages
    if not messages:
        raise SongError("the score has nothing to play")
    if len(messages) > MAX_LINES:
        raise SongError(f"{len(messages)} commands; a stored song holds at most {MAX_LINES}")
    missing = sorted({CHANNEL_KIND[type(m)] for m in messages} - set(channels))
    if missing:
        raise SongError(f"the rig has no channel for: {', '.join(missing)}")
    first = message_time_us(messages[0])
    commands = [
        replace(m, t_us=message_time_us(m) - first, seq=i, ch=channels[CHANNEL_KIND[type(m)]])
        for i, m in enumerate(messages)
    ]
    return CompiledSong(song_title(score.meta.title), commands)


def check_slot(slot: int) -> int:
    if not 0 <= slot < SLOTS:
        raise SongError(f"slot {slot} is outside 0..{SLOTS - 1}")
    return slot
