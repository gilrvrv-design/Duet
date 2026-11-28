"""API errors (spec §6.3): RFC 9457 problem details with stable codes.

Every error code the API can return is in ``STATUS``, the one place that decides its
HTTP status.
"""

from __future__ import annotations

from fastapi.responses import JSONResponse

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
    "INTERNAL": 500,
}


class Problem(Exception):
    def __init__(self, code: str, detail: str):
        if code not in STATUS:
            raise ValueError(f"unknown error code {code!r}: add it to STATUS")
        super().__init__(detail)
        self.code, self.detail, self.status = code, detail, STATUS[code]


def problem_response(exc: Problem) -> JSONResponse:
    return JSONResponse(
        {
            "type": f"https://duet.dev/problems/{exc.code}",
            "title": exc.code,
            "status": exc.status,
            "detail": exc.detail,
            "code": exc.code,
        },
        status_code=exc.status,
        media_type="application/problem+json",
    )
