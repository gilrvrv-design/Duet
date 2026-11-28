"""Learning (spec §5.8): what the pianist can do, what to give them next, and lesson paths.

Every graded pianist note exercises some features (a black key, a jump, an offbeat...).
Each feature keeps a Beta(successes + 1, failures + 1) estimate, so mastery is a
probability that becomes more certain with evidence (FR-E1). The pianist's level is the
highest difficulty level whose new features they have mastered.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from duet.difficulty import LEVELS
from duet.listening import Report
from duet.pitch import is_black_key
from duet.profile import KeyboardProfile, RobotProfile
from duet.score import DuetScore
from duet.timing import EPSILON, onset_groups, timed_events

MASTERED = 0.8
MIN_TRIES = 6
FAST_GAP_S = 0.5

# What each level adds on top of the one below (see duet.difficulty.LEVELS).
LEVEL_FEATURES = {
    1: ["steps"],
    2: ["offbeats", "jump5"],
    3: ["black_keys", "jump7", "chords", "fast"],
    4: ["jump12", "big_chords"],
    5: [],
}
FEATURE_WORDS = {
    "steps": "notes next to each other",
    "offbeats": "notes between the beats",
    "jump5": "jumps of up to five keys",
    "black_keys": "black keys",
    "jump7": "jumps of up to seven keys",
    "chords": "two notes at once",
    "fast": "quicker notes",
    "jump12": "jumps of up to an octave",
    "big_chords": "three-note chords",
}


def note_features(score: DuetScore, part: str) -> list[set[str]]:
    """The features each note of a human's part exercises, in time order (matches
    grading order)."""
    timed = timed_events(score, part)
    size = {id(t): len(group) for group in onset_groups(timed) for t in group}
    features = []
    prev_pitch, prev_start = None, None
    for t in timed:
        e = t.event
        together = size[id(t)]
        f = {"steps"}
        if abs(e.beat - round(e.beat)) > EPSILON:
            f.add("offbeats")
        if is_black_key(e.pitch):
            f.add("black_keys")
        if together >= 2:
            f.add("chords")
        if together >= 3:
            f.add("big_chords")
        if prev_pitch is not None and together == 1:
            jump = abs(e.pitch - prev_pitch)
            f |= {"jump5"} if 5 <= jump < 7 else set()
            f |= {"jump7"} if 7 <= jump < 12 else set()
            f |= {"jump12"} if jump >= 12 else set()
            if 0 < t.start_s - prev_start < FAST_GAP_S:
                f.add("fast")
        prev_pitch, prev_start = e.pitch, t.start_s
        features.append(f)
    return features


class Skill(BaseModel):
    successes: int = 0
    failures: int = 0

    @property
    def tries(self) -> int:
        return self.successes + self.failures

    @property
    def mastery(self) -> float:
        return (self.successes + 1) / (self.tries + 2)  # Beta posterior mean

    @property
    def known(self) -> bool:
        return self.tries >= MIN_TRIES and self.mastery >= MASTERED


class SkillModel(BaseModel):
    skills: dict[str, Skill] = Field(default_factory=dict)
    performances: int = 0

    def update(self, score: DuetScore, report: Report) -> list[str]:
        """Learn from one graded performance of a part (``report.part``); returns features
        newly mastered."""
        if report.part is None:
            raise ValueError("a skill comes from grading a part of a score: use grade_take")
        before = {k for k, s in self.skills.items() if s.known}
        # Grades and features are both in (time, pitch) order, so they line up.
        features_by_note = note_features(score, report.part)
        for grade_, features in zip(report.grades, features_by_note, strict=False):
            ok = grade_.result in ("hit", "early", "late")
            for feature in features:
                skill = self.skills.setdefault(feature, Skill())
                if ok:
                    skill.successes += 1
                else:
                    skill.failures += 1
        self.performances += 1
        return sorted({k for k, s in self.skills.items() if s.known} - before)

    @property
    def level(self) -> int:
        """Highest level whose features (and every level below's) are all mastered."""
        level = 0
        for lvl in range(1, 6):
            needed = LEVEL_FEATURES[lvl]
            if all(self.skills.get(f, Skill()).known for f in needed):
                level = lvl
            else:
                break
        return max(1, level)

    def next_request(self) -> tuple[int, str | None]:
        """(difficulty to compose at, what to focus on) for the next duet (FR-E2)."""
        working = min(5, self.level + 1) if self.level < 5 else 5
        candidates = [f for lvl in range(1, working + 1) for f in LEVEL_FEATURES[lvl]]
        unknown = [f for f in candidates if not self.skills.get(f, Skill()).known]
        if not unknown:
            return working, None
        weakest = min(unknown, key=lambda f: (self.skills.get(f, Skill()).mastery, f))
        return working, FEATURE_WORDS[weakest]


# Lesson paths ---------------------------------------------------------------

PASS_ACCURACY = 0.9


def step_passes(report: Report) -> bool:
    """A lesson step passes at 90% right or better (FR-E3)."""
    return report.accuracy >= PASS_ACCURACY


def current_step(passed: list[bool]) -> int | None:
    """The first step not yet passed, or None when the lesson is done."""
    return next((i for i, done in enumerate(passed) if not done), None)


@dataclass
class Step:
    title: str
    difficulty: int
    tempo_factor: float
    score: DuetScore


@dataclass
class LessonPath:
    title: str
    steps: list[Step] = field(default_factory=list)


def teach_song(
    transcription,
    target_level: int = 3,
    title: str = "Your song",
    robot: RobotProfile | None = None,
    keyboard: KeyboardProfile | None = None,
) -> LessonPath:
    """ "Teach me this song" (FR-A26): from the easiest part slowly to the target level at
    full speed. Each level is first played at 70% tempo, then at full tempo."""
    from duet.audio.arranger import arrange

    path = LessonPath(title)
    for level in range(1, target_level + 1):
        score = arrange(
            transcription, difficulty=level, robot=robot, keyboard=keyboard, title=title
        ).score
        for factor in (0.7, 1.0):
            tempo = round(score.meta.tempo_bpm * factor, 1)
            label = "slowly" if factor < 1 else "at full speed"
            path.steps.append(
                Step(f"Level {level} {label}", level, factor, score.with_tempo(tempo))
            )
    return path


__all__ = ["LEVELS", "LessonPath", "SkillModel", "Step", "note_features", "teach_song"]
