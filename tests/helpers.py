from pathlib import Path

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
