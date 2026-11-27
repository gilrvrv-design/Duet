"""Notes recovered from audio, independent of any model or library (spec §5.14.4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class NoteEvent:
    start_s: float
    end_s: float
    pitch: int  # MIDI number
    velocity: int = 80
    confidence: float = 1.0
    track: str = "melody"

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


class Transcriber(Protocol):
    """Any model that turns audio into notes: pYIN today, Basic Pitch or MT3 later."""

    name: str

    def transcribe(self, audio: np.ndarray, sr: int) -> list[NoteEvent]: ...
