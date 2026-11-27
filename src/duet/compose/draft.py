"""The JSON contract between the composer (an LLM) and Duet.

It is deliberately smaller than DuetScore and strict-schema friendly (every field
required, no extra keys), so the model's output can be constrained by the API.
Code, not the model, turns a draft into a DuetScore.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from duet.score import PARTS, DuetScore

NOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "bar": {"type": "integer", "description": "1-based bar number"},
        "beat": {"type": "number", "description": "1-based beat in the bar, e.g. 1, 1.5, 2"},
        "dur": {"type": "number", "description": "length in beats"},
        "pitch": {"type": "string", "description": "scientific pitch, e.g. C4, F#5"},
        "vel": {"type": "integer", "description": "loudness 1-127"},
    },
    "required": ["bar", "beat", "dur", "pitch", "vel"],
    "additionalProperties": False,
}

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "key": {"type": "string", "description": "e.g. C major, A minor"},
        "beats_per_bar": {"type": "integer"},
        "beat_unit": {"type": "integer", "description": "4 for quarter-note beats, 8 for eighths"},
        "tempo_bpm": {"type": "number"},
        "robot": {"type": "array", "items": NOTE_SCHEMA},
        "pianist": {"type": "array", "items": NOTE_SCHEMA},
        "explanation": {"type": "string", "description": "one or two plain sentences"},
    },
    "required": [
        "title",
        "key",
        "beats_per_bar",
        "beat_unit",
        "tempo_bpm",
        "robot",
        "pianist",
        "explanation",
    ],
    "additionalProperties": False,
}


class DraftError(ValueError):
    """The composer's output could not be turned into a score. The message is feedback."""


def draft_to_score(
    text: str,
    *,
    prompt: str,
    difficulty: int,
    pianist_range: tuple[str, str],
    robot_profile_id: str = "bottles-v1",
    keyboard_profile_id: str = "piano-88",
):
    """Parse the composer's JSON text into (DuetScore, explanation). The score names
    the profiles it was composed for."""
    try:
        draft = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DraftError(f"output is not valid JSON: {exc}") from exc
    if not isinstance(draft, dict):
        raise DraftError("output must be a JSON object")
    missing = [k for k in DRAFT_SCHEMA["required"] if k not in draft]
    if missing:
        raise DraftError(f"missing fields: {', '.join(missing)}")
    events = []
    for part in PARTS:
        notes = draft[part]
        if not isinstance(notes, list):
            raise DraftError(f"{part} must be a list of notes")
        for i, note in enumerate(notes):
            if not isinstance(note, dict):
                raise DraftError(f'{part}[{i}] must be a note object like {{"bar": 1, ...}}')
            events.append({**note, "part": part})
    data = {
        "meta": {
            "title": draft["title"],
            "prompt": prompt,
            "key": draft["key"],
            "time_signature": [draft["beats_per_bar"], draft["beat_unit"]],
            "tempo_bpm": draft["tempo_bpm"],
            "difficulty_target": difficulty,
        },
        "parts": {
            "robot": {"instrument_profile": robot_profile_id, "role": "melody"},
            "pianist": {
                "instrument_profile": keyboard_profile_id,
                "role": "accompaniment",
                "hand": "right",
                "range": list(pianist_range),
            },
        },
        "events": events,
    }
    try:
        score = DuetScore.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()[:10]
        )
        raise DraftError(f"invalid score: {problems}") from exc
    return score, str(draft["explanation"])


def score_to_draft(score: DuetScore, explanation: str = "") -> str:
    """Inverse of :func:`draft_to_score`, used to show the composer its own last draft."""
    data = score.to_dict()

    def notes(part):
        return [
            {k: e[k] for k in ("bar", "beat", "dur", "pitch", "vel")}
            for e in data["events"]
            if e["part"] == part
        ]

    return json.dumps(
        {
            "title": score.meta.title,
            "key": score.meta.key,
            "beats_per_bar": score.meta.time_signature[0],
            "beat_unit": score.meta.time_signature[1],
            "tempo_bpm": score.meta.tempo_bpm,
            "robot": notes("robot"),
            "pianist": notes("pianist"),
            "explanation": explanation,
        }
    )
