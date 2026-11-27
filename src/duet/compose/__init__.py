"""Composition: a text request becomes a checked DuetScore (spec §5.1)."""

from duet.compose.service import CompositionRequest, CompositionResult, compose

__all__ = ["CompositionRequest", "CompositionResult", "compose"]
