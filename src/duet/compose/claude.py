"""Claude as the composer (spec §5.1 FR-C3).

Uses structured outputs so the answer always matches the draft schema, streaming so
long answers do not time out, and server-side fallbacks so a declined request is
retried on another model inside the same call.
"""

from __future__ import annotations

import os
from typing import Any

from duet.compose.draft import DRAFT_SCHEMA
from duet.compose.service import ComposerError

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ComposerRefused(ComposerError):
    """Claude declined the request."""


class ComposerUnavailable(ComposerError):
    """The Claude API could not be reached or returned an error."""


def _sdk_errors() -> tuple[tuple, tuple]:
    """(status errors, connection errors) from the SDK, if it is installed."""
    try:
        import anthropic
    except ImportError:
        return (), ()
    return (anthropic.APIStatusError,), (anthropic.APIConnectionError,)


class ClaudeComposer:
    """Implements the ``Composer`` protocol with the Anthropic SDK."""

    def __init__(
        self,
        client: Any | None = None,
        model: str | None = None,
        effort: str = "medium",
        max_tokens: int = 32000,
    ):
        if client is None:
            import anthropic  # optional dependency: pip install "duet[llm]"

            client = anthropic.Anthropic()
        self.client = client
        self.model = model or os.environ.get("DUET_MODEL", DEFAULT_MODEL)
        self.effort = effort
        self.max_tokens = max_tokens

    def write(self, system: str, messages: list[dict]) -> str:
        status_errors, connection_errors = _sdk_errors()
        try:
            response = self._stream(system, messages)
        except status_errors as exc:  # the SDK already retried 429 and 5xx
            raise ComposerUnavailable(f"Claude API error {exc.status_code}: {exc.message}") from exc
        except connection_errors as exc:
            raise ComposerUnavailable("cannot reach the Claude API") from exc
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise ComposerRefused(getattr(details, "explanation", None) or "request declined")
        if response.stop_reason == "max_tokens":
            raise ComposerError(
                "composer answer was cut off; raise max_tokens or shorten the piece"
            )
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise ComposerError("composer returned no text")
        return text

    def _stream(self, system: str, messages: list[dict]):
        with self.client.beta.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": DRAFT_SCHEMA},
            },
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            return stream.get_final_message()
