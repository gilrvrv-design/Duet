"""Claude as the composer (spec §5.1 FR-C3).

Uses structured outputs so the answer always matches the draft schema, streaming so
long answers do not time out, and server-side fallbacks so a declined request is
retried on another model inside the same call.
"""

from __future__ import annotations

import os
from typing import Any

from duet.compose.draft import DRAFT_SCHEMA

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ComposerRefused(RuntimeError):
    pass


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
            response = stream.get_final_message()
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise ComposerRefused(getattr(details, "explanation", None) or "request declined")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("composer answer was cut off; raise max_tokens or shorten the piece")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise RuntimeError("composer returned no text")
        return text
