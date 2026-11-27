"""Copyright guard (spec FR-C5, FR-A11): is this melody someone else's?

Melodies are compared by their intervals (the steps between consecutive notes), so a
copy is found even when it is transposed or played at another tempo. A long enough run
of matching intervals, which is not just a scale or a repeated note, counts as a match.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

from duet.pitch import name_to_midi
from duet.score import PARTS, DuetScore

MATCH = 7  # consecutive matching intervals that make a melody recognisable
REVIEW = 5  # shorter runs worth a person's look
MIN_DISTINCT = 3  # a run must use at least this many different intervals


@dataclass(frozen=True)
class Melody:
    title: str
    pitches: tuple[int, ...]
    protected: bool

    @property
    def intervals(self) -> tuple[int, ...]:
        return tuple(b - a for a, b in zip(self.pitches, self.pitches[1:], strict=False))


@dataclass(frozen=True)
class Match:
    title: str
    part: str
    length: int  # matching intervals in a row
    protected: bool


@dataclass
class Verdict:
    matches: list[Match] = field(default_factory=list)

    @property
    def status(self) -> str:
        """original, public_domain, review or protected."""
        if any(m.protected and m.length >= MATCH for m in self.matches):
            return "protected"
        if any(m.protected for m in self.matches):
            return "review"
        if self.matches:
            return "public_domain"
        return "original"

    def problems(self) -> list[str]:
        """Feedback for the composer: only protected matches are problems."""
        return [
            f'the {m.part} part copies {m.length + 1} notes of "{m.title}"; write an original '
            "melody in that style instead"
            for m in self.matches
            if m.protected and m.length >= MATCH
        ]


def melody_line(score: DuetScore, part: str) -> list[int]:
    """The top note of each onset: what a listener hears as the tune."""
    tops: dict[tuple, int] = {}
    for e in score.part_events(part):
        key = (e.bar, e.beat)
        tops[key] = max(tops.get(key, 0), e.pitch)
    return [tops[k] for k in sorted(tops)]


def longest_run(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    """Longest run of equal intervals shared by a and b (longest common substring),
    ignoring runs that are too plain to identify a tune."""
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                run = a[i - cur[j] : i]
                if cur[j] > best and len(set(run)) >= MIN_DISTINCT:
                    best = cur[j]
        prev = cur
    return best


@dataclass
class CopyrightGuard:
    melodies: list[Melody] = field(default_factory=list)

    @classmethod
    def load(cls, protected_file: str | Path | None = None) -> CopyrightGuard:
        """Public-domain melodies ship with Duet; protected ones come from a file the
        operator provides (``DUET_PROTECTED_MELODIES``), e.g. from a licensed catalogue."""
        text = (resources.files("duet.profiles") / "melodies-public-domain.yaml").read_text(
            encoding="utf-8"
        )
        melodies = _parse(yaml.safe_load(text), protected=False)
        path = protected_file or os.environ.get("DUET_PROTECTED_MELODIES")
        if path:
            melodies += _parse(yaml.safe_load(Path(path).read_text(encoding="utf-8")), True)
        return cls(melodies)

    def check(self, score: DuetScore) -> Verdict:
        verdict = Verdict()
        for part in PARTS:
            line = melody_line(score, part)
            intervals = tuple(b - a for a, b in zip(line, line[1:], strict=False))
            for melody in self.melodies:
                run = longest_run(intervals, melody.intervals)
                if run >= (REVIEW if melody.protected else MATCH):
                    verdict.matches.append(Match(melody.title, part, run, melody.protected))
        return verdict


def _parse(data: dict, protected: bool) -> list[Melody]:
    return [
        Melody(
            m["title"],
            tuple(name_to_midi(n) if isinstance(n, str) else n for n in m["notes"]),
            protected,
        )
        for m in data.get("melodies", [])
    ]
