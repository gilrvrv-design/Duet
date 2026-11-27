import json
from pathlib import Path

from duet.compose import CompositionRequest
from duet.score import DuetScore

ROOT = Path(__file__).resolve().parents[1]


def make_score(robot=(), pianist=(), tempo=120.0, time_signature=(4, 4), **meta) -> DuetScore:
    """Build a score from (bar, beat, dur, pitch) tuples for each part."""
    events = [
        {"part": "robot", "bar": b, "beat": bt, "dur": d, "pitch": p} for b, bt, d, p in robot
    ] + [{"part": "pianist", "bar": b, "beat": bt, "dur": d, "pitch": p} for b, bt, d, p in pianist]
    return DuetScore.model_validate(
        {"meta": {"tempo_bpm": tempo, "time_signature": time_signature, **meta}, "events": events}
    )


def synth(notes, sr=22050, total_s=None):
    """Render (midi, start_s, dur_s) notes as a plucked tone with a few harmonics."""
    import numpy as np

    end = max(s + d for _, s, d in notes) + 0.3
    out = np.zeros(int(sr * (total_s or end)), dtype=np.float32)
    for midi, start, dur in notes:
        hz = 440.0 * 2 ** ((midi - 69) / 12)
        t = np.arange(int(sr * dur)) / sr
        tone = sum(np.sin(2 * np.pi * hz * k * t) / k for k in (1, 2, 3))
        env = np.minimum(1, t / 0.01) * np.minimum(1, (dur - t) / 0.03).clip(0, 1)
        i = int(sr * start)
        out[i : i + t.size] += (0.3 * tone * env).astype(np.float32)
    return out


# A scripted composer and drafts, shared by the composition, API and job tests.


def draft(robot, pianist, **meta):
    note = lambda b, bt, d, p: {"bar": b, "beat": bt, "dur": d, "pitch": p, "vel": 80}  # noqa: E731
    return json.dumps(
        {
            "title": "Test",
            "key": "C major",
            "beats_per_bar": 4,
            "beat_unit": 4,
            "tempo_bpm": 100,
            "robot": [note(*n) for n in robot],
            "pianist": [note(*n) for n in pianist],
            "explanation": "The robot sings, you hold the bass.",
            **meta,
        }
    )


GOOD = draft(
    [(1, 1, 2, "E5"), (1, 3, 2, "G5"), (2, 1, 4, "C6")], [(1, 1, 4, "C4"), (2, 1, 4, "E4")]
)
TOO_FAST = draft([(1, 1, 0.5, "C5"), (1, 1.5, 0.5, "C6")], [(1, 1, 4, "C4")])


class ScriptedComposer:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def write(self, system, messages):
        self.calls.append((system, [dict(m) for m in messages]))
        return self.answers.pop(0)


REQUEST = CompositionRequest(prompt="a happy tune", difficulty=1, bars=2)
