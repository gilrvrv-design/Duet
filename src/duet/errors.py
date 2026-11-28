"""Errors with stable codes (spec §6.3): what the API answers as problem details
(duet.api.errors), and what a background job fails with. One kind of coded error for
both; every code is in ``STATUS``, the one place that decides its HTTP status.
"""

from __future__ import annotations

STATUS = {
    "NOT_FOUND": 404,
    "SCORE_INVALID": 422,
    "LINE_UP_INVALID": 422,  # a part names an unknown instrument or a performer it cannot have
    "MIDI_INVALID": 422,
    "FILE_TOO_LARGE": 413,
    "FILE_EMPTY": 422,
    "RIGHTS_NOT_CONFIRMED": 422,
    "COPYRIGHT_MATCH": 422,
    "AUDIO_INVALID": 422,
    "ROUTE_UNAVAILABLE": 422,
    "VARIATION_INVALID": 422,
    "SONG_INVALID": 422,  # the duet cannot be stored as a song for that rig
    "LIVE_INVALID": 422,  # a practice asked for a mode or input this server cannot give
    "PRACTICE_BUSY": 409,  # a practice is already playing
    "COMPOSITION_FAILED": 502,
    "LLM_ERROR": 502,
    "SEPARATION_FAILED": 500,  # the full-mix route's source separation (Demucs) failed
    "INTERNAL": 500,
}


class Problem(Exception):
    """A request or job that cannot be done, with a stable code and what went wrong."""

    def __init__(self, code: str, detail: str):
        if code not in STATUS:
            raise ValueError(f"unknown error code {code!r}: add it to STATUS")
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, STATUS[code]
