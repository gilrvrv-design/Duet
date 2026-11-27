"""HTTP API (spec §6). Needs the api extra: pip install "duet[api]"."""

from duet.api.app import create_app

__all__ = ["create_app"]
