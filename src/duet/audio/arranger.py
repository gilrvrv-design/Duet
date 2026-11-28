"""Turn a transcription into a duet the rig can play (spec §5.14.3).

1. The robot takes the melody (FR-A20).
2. The melody is transposed to the key that puts the most notes on the bottles (FR-A21).
3. The pianist gets a harmony part built from the melody, at the target level (FR-A22).
4. Whatever still does not fit goes through deterministic repair.
5. Bottle retuning is suggested when it would raise melody coverage (FR-A24).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from duet.audio.analysis import estimate_key, quantize
from duet.audio.notes import NoteEvent
from duet.audio.pipeline import Transcription
from duet.pitch import (
    PITCH_CLASSES,
    best_transpose,
    cents_between,
    coverage,
    midi_to_hz,
    midi_to_name,
    name_to_midi,
)
from duet.profile import KeyboardProfile, RobotProfile, keyboard_profile, robot_profile
from duet.repair import Change, repair_robot
from duet.score import DuetScore, Duo

BEATS_PER_BAR = 4
# Diatonic triads used for simple accompaniment: (root offset from tonic, is minor).
MAJOR_TRIADS = ((0, False), (5, False), (7, False), (9, True), (2, True))  # I IV V vi ii
MINOR_TRIADS = (
    (0, True),
    (5, True),
    (7, False),
    (8, False),
    (3, False),
    (10, False),
)  # i iv V VI III VII


@dataclass(frozen=True)
class Retuning:
    bottle: str
    to: str
    cents: float
    coverage_after: float

    def advice(self) -> str:
        direction = "add water to" if self.cents < 0 else "pour water out of"
        return (
            f"retune bottle {self.bottle} to {self.to} ({self.cents:+.0f} cents: {direction} it); "
            f"melody coverage becomes {self.coverage_after:.0%}"
        )


@dataclass
class Arrangement:
    score: DuetScore
    transpose: int
    coverage_before: float
    coverage_after: float
    chords: list[str]
    repairs: list[Change] = field(default_factory=list)
    retuning: list[Retuning] = field(default_factory=list)


def melody_track(t: Transcription) -> list[NoteEvent]:
    """The "melody" track if there is one, else the track with the highest average pitch."""
    tracks = t.tracks()
    if not tracks:
        return []
    name = (
        "melody"
        if "melody" in tracks
        else max(
            tracks,
            key=lambda k: (
                sum(n.pitch for n in t.notes if n.track == k) / sum(n.track == k for n in t.notes)
            ),
        )
    )
    return [n for n in t.notes if n.track == name]


def suggest_retuning(
    pitches: list[int], robot: RobotProfile, max_cents: float = 200
) -> list[Retuning]:
    """Retune the least-used bottle to the most-missed pitch, when that bottle is close."""
    available = robot.pitches
    missing: dict[int, int] = {}
    for p in pitches:
        if p not in available:
            missing[p] = missing.get(p, 0) + 1
    base = coverage(pitches, available)
    suggestions = []
    for target, _ in sorted(missing.items(), key=lambda kv: -kv[1]):
        use = {b: pitches.count(b) for b in available}
        candidates = [
            b
            for b in available
            if abs(cents_between(midi_to_hz(b), midi_to_hz(target))) <= max_cents
        ]
        if not candidates:
            continue
        bottle = min(candidates, key=lambda b: (use[b], abs(b - target)))
        after = coverage(pitches, [target if b == bottle else b for b in available])
        if after > base:
            suggestions.append(
                Retuning(
                    midi_to_name(bottle),
                    midi_to_name(target),
                    round(cents_between(midi_to_hz(bottle), midi_to_hz(target))),
                    round(after, 3),
                )
            )
    return sorted(suggestions, key=lambda r: -r.coverage_after)[:2]


def _triad(root: int, minor: bool) -> tuple[int, int, int]:
    return (root % 12, (root + (3 if minor else 4)) % 12, (root + 7) % 12)


def _bar_chords(placed, tonic: int, mode: str, bars: int) -> list[tuple[str, tuple[int, ...]]]:
    """Pick, for each bar, the triad that covers the most melody time. Ties go to the
    earlier chord in the list (tonic first)."""
    options = [
        (f"{PITCH_CLASSES[(tonic + r) % 12]}{'m' if minor else ''}", _triad(tonic + r, minor))
        for r, minor in (MAJOR_TRIADS if mode == "major" else MINOR_TRIADS)
    ]
    chords = []
    for bar in range(bars):
        weight = [0.0] * 12
        for start, dur, n in placed:
            if bar * BEATS_PER_BAR <= start < (bar + 1) * BEATS_PER_BAR:
                weight[n.pitch % 12] += dur
        chords.append(max(options, key=lambda o: sum(weight[pc] for pc in o[1])))
    return chords


def _nearest(pitch_classes, near: int, low: int, high: int) -> int:
    """The pitch in [low, high] with one of the pitch classes, closest to ``near``."""
    candidates = [p for p in range(low, high + 1) if p % 12 in pitch_classes]
    return min(candidates, key=lambda p: (abs(p - near), p)) if candidates else low


def arrange(
    t: Transcription,
    difficulty: int = 1,
    robot: RobotProfile | None = None,
    keyboard: KeyboardProfile | None = None,
    pianist_range: tuple[str, str] = ("C3", "C5"),
    title: str = "Transcribed duet",
) -> Arrangement:
    """A playable duet from a transcription: its melody for the bot, moved to where the
    instrument has the most of its notes, and an accompaniment at ``difficulty`` for the
    person, from the chords of everything heard."""
    robot = robot or robot_profile()
    keyboard = keyboard or keyboard_profile()
    duo = Duo(bot_instrument=robot.id, human_instrument=keyboard.id)
    melody = melody_track(t)
    pitches = [n.pitch for n in melody]
    shift = best_transpose(pitches, robot.pitches)
    moved = _shifted(melody, shift)
    melody_name = melody[0].track if melody else "melody"
    backing = _shifted([n for n in t.notes if n.track != melody_name], shift)
    key_name, tonic, mode = estimate_key(moved + backing)

    origin = min((n.start_s for n in moved), default=0.0)
    events = _melody_events(duo.bot, quantize(moved, t.tempo_bpm, origin_s=origin))
    bars = max((e["bar"] for e in events), default=1)
    harmony = quantize(moved + backing, t.tempo_bpm, origin_s=origin)
    chords = _bar_chords(harmony, tonic, mode, bars)
    low, high = (name_to_midi(p) for p in pianist_range)
    events += _pianist_part(duo.human, chords, difficulty, low, high)

    score = DuetScore.model_validate(
        {
            "meta": {
                "title": title,
                "key": key_name,
                "time_signature": [BEATS_PER_BAR, 4],
                "tempo_bpm": t.tempo_bpm,
                "difficulty_target": difficulty,
                "style_tags": ["transcribed"],
            },
            "parts": duo.parts(human_range=pianist_range, hand="left"),
            "events": events,
        }
    )
    repaired = repair_robot(score, robot, part=duo.bot)
    return Arrangement(
        score=repaired.score,
        transpose=shift,
        coverage_before=round(coverage(pitches, robot.pitches), 3),
        coverage_after=round(coverage([n.pitch for n in moved], robot.pitches), 3),
        chords=[name for name, _ in chords],
        repairs=repaired.changes,
        retuning=suggest_retuning([n.pitch for n in moved], robot),
    )


def _shifted(notes: list[NoteEvent], semitones: int) -> list[NoteEvent]:
    return [
        NoteEvent(n.start_s, n.end_s, n.pitch + semitones, n.velocity, n.confidence, n.track)
        for n in notes
    ]


def _melody_events(part: str, placed) -> list[dict]:
    """The bot's part: each quantized melody note at its bar and beat."""
    events = []
    for start, dur, n in placed:
        bar, beat = int(start // BEATS_PER_BAR) + 1, start % BEATS_PER_BAR + 1
        events.append(
            {
                "part": part,
                "bar": bar,
                "beat": round(beat, 6),
                "dur": dur,
                "pitch": n.pitch,
                "vel": n.velocity,
                "confidence": n.confidence,
            }
        )
    return events


def _pianist_part(part: str, chords, difficulty: int, low: int, high: int) -> list[dict]:
    """Simple accompaniment with smooth voice leading (each note is the chord tone nearest
    the previous one).

    Level 1: one chord tone held for the bar. Level 2-3: two chord tones on half notes.
    Level 4-5: the full triad on each half bar.
    """
    events = []
    previous = _nearest({chords[0][1][0]}, (low + high) // 2, low, high) if chords else low
    for bar, (_, triad) in enumerate(chords, start=1):
        first = _nearest(set(triad), previous, low, high)
        if difficulty <= 1:
            notes = [(1, 4, [first])]
        elif difficulty <= 3:
            second = _nearest(set(triad) - {first % 12}, first, low, high)
            notes = [(1, 2, [first]), (3, 2, [second])]
        else:
            root = _nearest({triad[0]}, previous, low, high - 7)
            voicing = sorted(
                {root, *(_nearest({pc}, root + 4, root, root + 11) for pc in triad[1:])}
            )
            notes = [(1, 2, voicing), (3, 2, voicing)]
        previous = notes[-1][2][0]
        for beat, dur, pitches in notes:
            events += [
                {"part": part, "bar": bar, "beat": beat, "dur": dur, "pitch": p, "vel": 70}
                for p in pitches
            ]
    return events


__all__ = ["Arrangement", "Retuning", "arrange"]
