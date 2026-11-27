import os
from types import SimpleNamespace

import pytest

from duet.compose import CompositionRequest, compose
from duet.compose.claude import DEFAULT_MODEL, ClaudeComposer, ComposerRefused
from duet.compose.draft import DRAFT_SCHEMA
from duet.compose.service import ComposerError


class FakeStream:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.response


class FakeClient:
    def __init__(self, response):
        self.kwargs = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))
        self.response = response

    def _stream(self, **kwargs):
        self.kwargs = kwargs
        return FakeStream(self.response)


def response(text=None, stop_reason="end_turn", explanation=None):
    content = [SimpleNamespace(type="thinking", thinking="")]
    if text is not None:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(explanation=explanation),
    )


def test_request_shape():
    client = FakeClient(response('{"ok": 1}'))
    composer = ClaudeComposer(client=client)
    assert composer.write("sys", [{"role": "user", "content": "hi"}]) == '{"ok": 1}'
    kw = client.kwargs
    assert kw["model"] == os.environ.get("DUET_MODEL", DEFAULT_MODEL)
    assert kw["system"] == "sys"
    assert kw["output_config"]["format"] == {"type": "json_schema", "schema": DRAFT_SCHEMA}
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in kw and "temperature" not in kw


def test_refusal_and_truncation():
    with pytest.raises(ComposerRefused, match="nope"):
        ClaudeComposer(
            client=FakeClient(response(stop_reason="refusal", explanation="nope"))
        ).write("s", [])
    with pytest.raises(ComposerError, match="cut off"):
        ClaudeComposer(client=FakeClient(response("{", stop_reason="max_tokens"))).write("s", [])
    with pytest.raises(ComposerError, match="no text"):
        ClaudeComposer(client=FakeClient(response())).write("s", [])


@pytest.mark.skipif(
    not os.environ.get("DUET_LIVE_LLM"), reason="set DUET_LIVE_LLM=1 to call the real API"
)
def test_live_composition():
    result = compose(
        CompositionRequest(prompt="a calm lullaby", difficulty=1, bars=4), ClaudeComposer()
    )
    assert result.score.part_events("robot")


def test_cli_compose(tmp_path, monkeypatch, capsys):
    import json

    from duet import cli
    from duet.compose import claude

    note = {"bar": 1, "beat": 1, "dur": 4, "pitch": "C5", "vel": 80}
    text = json.dumps(
        {
            "title": "Tiny",
            "key": "C major",
            "beats_per_bar": 4,
            "beat_unit": 4,
            "tempo_bpm": 90,
            "robot": [note],
            "pianist": [{**note, "pitch": "C4"}],
            "explanation": "Short.",
        }
    )
    client = FakeClient(response(text))

    class StubComposer(ClaudeComposer):
        def __init__(self, model=None):
            super().__init__(client=client, model=model)

    monkeypatch.setattr(claude, "ClaudeComposer", StubComposer)
    out = tmp_path / "tiny.mid"
    assert cli.main(["compose", "a tiny tune", str(out), "--bars", "1"]) == 0
    assert out.exists()
    assert "Tiny: 1 bars in 1 round(s)" in capsys.readouterr().out
