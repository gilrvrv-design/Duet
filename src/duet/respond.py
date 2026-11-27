"""Call and response (spec §5.7 FR-G1, FR-G3; FR-H6): the robot answers the pianist.

The pianist plays a phrase; the robot answers with a variation of it, on the bottles,
straight away. Answers are built in "bottle space" (index 0..7 along the bottles), so
every note lands on a bottle and stays in the bottles' scale. A phrase memory lets the
robot bring back the pianist's earlier ideas later in the session.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from duet.listening import PlayedNote
from duet.profile import RobotProfile
from duet.repair import repair_robot
from duet.score import DuetScore

GRID_BEATS = 0.5
VARIATIONS = ("echo", "answer", "sequence", "retrograde")


@dataclass(frozen=True)
class PhraseNote:
    beat: float  # from the start of the phrase
    dur: float
    pitch: int


def capture(
    played: list[PlayedNote], start_us: int, tempo_bpm: float, beats: float
) -> list[PhraseNote]:
    """The pianist's phrase on a half-beat grid (FR-H6)."""
    spb = 60 / tempo_bpm
    onsets = sorted(
        (round(((p.t_us - start_us) / 1e6 / spb) / GRID_BEATS) * GRID_BEATS, p.pitch)
        for p in played
        if start_us <= p.t_us < start_us + beats * spb * 1e6
    )
    phrase, seen = [], set()
    for i, (beat, pitch) in enumerate(onsets):
        if beat in seen or beat >= beats:
            continue  # one note per grid slot: the robot plays one note at a time
        seen.add(beat)
        nxt = next((b for b, _ in onsets[i + 1 :] if b > beat), beats)
        phrase.append(PhraseNote(beat, max(GRID_BEATS, nxt - beat), pitch))
    return phrase


def _to_index(pitch: int, robot: RobotProfile, shift: int) -> int:
    """Nearest bottle (by pitch, after an octave shift) as an index."""
    target = pitch + shift
    return min(range(len(robot.notes)), key=lambda i: (abs(robot.notes[i].midi - target), i))


def _octave_shift(pitches: list[int], robot: RobotProfile) -> int:
    """The octave shift that puts the phrase's middle nearest the bottles' middle."""
    centre = (robot.notes[0].midi + robot.notes[-1].midi) / 2
    middle = (min(pitches) + max(pitches)) / 2
    return 12 * round((centre - middle) / 12)


@dataclass
class Responder:
    robot: RobotProfile
    memory: list[list[int]] = field(default_factory=list)  # earlier phrases, as indices
    turn: int = 0

    def next_kind(self) -> str:
        if self.turn >= 3 and self.memory and self.turn % 3 == 0:
            return "recall"  # bring back the pianist's first idea (FR-G3)
        return VARIATIONS[self.turn % len(VARIATIONS)]

    def predict_first(self, heard: list[int]) -> int | None:
        """Best guess, from the phrase so far, of the bottle the answer starts on, so the
        carriage can get there while the pianist is still playing."""
        kind = self.next_kind()
        if kind == "recall":
            return self.memory[0][0]
        if not heard:
            return None
        shift = _octave_shift(heard, self.robot)
        first = _to_index(heard[-1] if kind == "retrograde" else heard[0], self.robot, shift)
        if kind == "sequence":
            first = min(len(self.robot.notes) - 1, first + 1)
        return first

    def respond(self, phrase: list[PhraseNote]) -> tuple[str, list[PhraseNote]]:
        """Answer one phrase. Returns (which variation, the robot's notes)."""
        if not phrase:
            return "rest", []
        shift = _octave_shift([n.pitch for n in phrase], self.robot)
        idx = [_to_index(n.pitch, self.robot, shift) for n in phrase]
        top = len(self.robot.notes) - 1
        kind = self.next_kind()
        if kind == "answer":  # mirror the intervals around the first note
            idx = [2 * idx[0] - i for i in idx]
        elif kind == "sequence":  # the same shape one step higher (or lower at the top)
            step = 1 if max(idx) < top else -1
            idx = [i + step for i in idx]
        elif kind == "retrograde":
            idx = idx[::-1]
        elif kind == "recall":
            first = self.memory[0]
            idx = [first[k % len(first)] for k in range(len(idx))]
        idx = [min(top, max(0, i)) for i in idx]
        idx[-1] = self._home(idx[-1])  # end on the home note: an answer sounds finished
        self.memory.append([_to_index(n.pitch, self.robot, shift) for n in phrase])
        self.turn += 1
        notes = [
            PhraseNote(n.beat, n.dur, self.robot.notes[i].midi)
            for n, i in zip(phrase, idx, strict=True)
        ]
        return kind, notes

    def _home(self, index: int) -> int:
        """Nearest bottle with the same pitch class as the lowest bottle (the tonic)."""
        tonic = self.robot.notes[0].midi % 12
        homes = [i for i, b in enumerate(self.robot.notes) if b.midi % 12 == tonic] or [0]
        return min(homes, key=lambda i: abs(i - index))


def reply_score(
    notes: list[PhraseNote], tempo_bpm: float, robot: RobotProfile, beats_per_bar: int = 4
) -> DuetScore:
    """A robot-only score for the answer, made playable by repair."""
    events = [
        {
            "part": "robot",
            "bar": int(n.beat // beats_per_bar) + 1,
            "beat": n.beat % beats_per_bar + 1,
            "dur": n.dur,
            "pitch": n.pitch,
            "vel": 96,
        }
        for n in notes
    ]
    score = DuetScore.model_validate(
        {
            "meta": {
                "title": "Answer",
                "tempo_bpm": tempo_bpm,
                "time_signature": [beats_per_bar, 4],
            },
            "events": events,
        }
    )
    return repair_robot(score, robot, keep_tempo=True).score  # the session's beat holds
