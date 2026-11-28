"""Score positions to clock time.

Tempo counts beats of the time signature (a 6/8 bar at 120 bpm has six beats of 0.5 s).
This is the only module that turns bars and beats into seconds.
"""

from __future__ import annotations

from dataclasses import dataclass

from duet.score import DuetScore, Event, PartName

EPSILON = 1e-9


def seconds_per_beat(tempo_bpm: float) -> float:
    if tempo_bpm <= 0:
        raise ValueError(f"tempo must be positive: {tempo_bpm}")
    return 60.0 / tempo_bpm


def beat_index(bar: int, beat: float, beats_per_bar: int) -> float:
    """0-based absolute beat for a 1-based bar and beat."""
    return (bar - 1) * beats_per_bar + (beat - 1)


def bar_and_beat(index: float, beats_per_bar: int) -> tuple[int, float]:
    """Inverse of :func:`beat_index`."""
    if index < -EPSILON:
        raise ValueError(f"beat index must not be negative: {index}")
    index = max(index, 0.0)
    bar = int((index + EPSILON) // beats_per_bar)
    beat = index - bar * beats_per_bar
    if abs(beat) < EPSILON:
        beat = 0.0
    return bar + 1, round(beat + 1, 6)


@dataclass(frozen=True)
class TimedEvent:
    event: Event
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


def timed_events(score: DuetScore, part: PartName | None = None) -> list[TimedEvent]:
    """Events with absolute start and end times, sorted by start then pitch."""
    spb = seconds_per_beat(score.meta.tempo_bpm)
    result = []
    for event in score.events:
        if part is not None and event.part != part:
            continue
        start = beat_index(event.bar, event.beat, score.meta.beats_per_bar) * spb
        result.append(TimedEvent(event, start, start + event.dur * spb))
    return sorted(result, key=lambda t: (t.start_s, t.event.pitch))


def onset_groups(timed: list[TimedEvent]) -> list[list[TimedEvent]]:
    """Notes that start together (a chord, or one note), in time order."""
    groups: list[list[TimedEvent]] = []
    for t in sorted(timed, key=lambda t: (t.start_s, t.event.pitch)):
        if groups and abs(t.start_s - groups[-1][0].start_s) <= EPSILON:
            groups[-1].append(t)
        else:
            groups.append([t])
    return groups


def sounding_at(timed: list[TimedEvent], t_s: float) -> list[TimedEvent]:
    """The notes sounding at ``t_s`` (a note ending as another starts does not overlap)."""
    return [o for o in timed if o.start_s <= t_s + EPSILON < o.end_s]


def polyphony(timed: list[TimedEvent]) -> int:
    """Most notes sounding at once."""
    return max((len(sounding_at(timed, t.start_s)) for t in timed), default=0)


def score_duration_s(score: DuetScore) -> float:
    return max((t.end_s for t in timed_events(score)), default=0.0)
