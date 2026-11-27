"""Melody route (spec §5.14 FR-A3): one voice at a time - humming, singing, whistling,
or a single instrument. Uses librosa's pYIN pitch tracker plus onset detection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from duet.audio.notes import NoteEvent
from duet.pitch import hz_to_midi


@dataclass
class PyinTranscriber:
    name: str = "pyin"
    fmin_hz: float = 65.0  # C2
    fmax_hz: float = 2100.0  # C7
    hop: int = 256
    min_note_s: float = 0.06
    min_voiced_prob: float = 0.5

    def transcribe(self, audio: np.ndarray, sr: int) -> list[NoteEvent]:
        import librosa

        if audio.size < sr * 0.1:
            return []
        f0, voiced, prob = librosa.pyin(
            audio,
            fmin=self.fmin_hz,
            fmax=self.fmax_hz,
            sr=sr,
            frame_length=2048,
            hop_length=self.hop,
        )
        rms = librosa.feature.rms(y=audio, frame_length=2048, hop_length=self.hop)[0]
        onsets = set(
            librosa.onset.onset_detect(y=audio, sr=sr, hop_length=self.hop, backtrack=True)
        )
        frame_s = self.hop / sr
        midi = np.full(len(f0), -1)
        ok = voiced & (prob >= self.min_voiced_prob) & np.isfinite(f0)
        midi[ok] = np.round([hz_to_midi(h) for h in f0[ok]]).astype(int)

        notes: list[NoteEvent] = []
        start = None
        for i in range(len(midi) + 1):
            current = midi[i] if i < len(midi) else -1
            new_note = start is not None and (current != midi[start] or (i in onsets and i > start))
            if new_note:
                notes.append(self._note(start, i, midi[start], prob, rms, frame_s))
                start = None
            if start is None and current >= 0:
                start = i
        return [n for n in _merge_flicker(notes) if n.duration_s >= self.min_note_s]

    def _note(self, a, b, pitch, prob, rms, frame_s) -> NoteEvent:
        level = float(np.max(rms[a:b])) if b > a else 0.0
        velocity = int(np.clip(40 + 87 * min(1.0, level / 0.3), 1, 127))
        return NoteEvent(
            start_s=round(a * frame_s, 4),
            end_s=round(b * frame_s, 4),
            pitch=int(pitch),
            velocity=velocity,
            confidence=round(float(np.nanmean(prob[a:b])), 3),
        )


def _merge_flicker(notes: list[NoteEvent], max_gap_s: float = 0.03) -> list[NoteEvent]:
    """Join a note with the next one of the same pitch when only a tiny gap separates
    them (pitch trackers flicker at note edges)."""
    merged: list[NoteEvent] = []
    for note in notes:
        last = merged[-1] if merged else None
        if last and last.pitch == note.pitch and note.start_s - last.end_s <= max_gap_s:
            merged[-1] = NoteEvent(
                last.start_s,
                note.end_s,
                note.pitch,
                max(last.velocity, note.velocity),
                min(last.confidence, note.confidence),
            )
        else:
            merged.append(note)
    return merged
