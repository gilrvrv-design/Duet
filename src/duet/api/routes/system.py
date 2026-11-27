from __future__ import annotations

from fastapi import APIRouter

from duet import __version__
from duet.api.errors import Problem
from duet.kinematics import reachability
from duet.profile import robot_profile

router = APIRouter()


@router.get("/v1/health")
def health():
    return {"status": "ok", "version": __version__}


@router.get("/v1/profiles/{profile_id}/reachability")
def profile_reachability(profile_id: str):
    try:
        robot = robot_profile(profile_id)
    except (KeyError, TypeError) as exc:
        raise Problem("NOT_FOUND", str(exc)) from exc
    matrix = reachability(robot)
    return {"pitches": list(matrix.pitches), "min_interval_s": matrix.seconds}
