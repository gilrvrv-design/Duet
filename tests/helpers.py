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
