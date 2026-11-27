import json
import zlib

from duet.evaluation import gate, load_cases, prompt_pack_id, run_eval
from helpers import ROOT

CASES = load_cases(ROOT / "evals" / "prompts.yaml")


class RuleComposer:
    """Deterministic stand-in for an LLM. ``quality`` < 1 makes some first drafts too fast."""

    def __init__(self, quality=1.0):
        self.quality = quality

    def write(self, system, messages):
        request = messages[0]["content"]
        bars = int(request.split("Length: ")[1].split(" ")[0])
        first_try = len(messages) == 1
        bad = first_try and (zlib.crc32(request.encode()) % 100) / 100 >= self.quality
        note = lambda b, beat, d, p: {"bar": b, "beat": beat, "dur": d, "pitch": p, "vel": 80}  # noqa: E731
        robot = [note(b, 1, 2, "E5") for b in range(1, bars + 1)]
        robot += [
            note(b, 3 if not bad else 1.25, 2, "C6" if bad else "G5") for b in range(1, bars + 1)
        ]
        pianist = [note(b, 1, 4, "C4") for b in range(1, bars + 1)]
        return json.dumps(
            {
                "title": "t",
                "key": "C major",
                "beats_per_bar": 4,
                "beat_unit": 4,
                "tempo_bpm": 90,
                "robot": robot,
                "pianist": pianist,
                "explanation": "e",
            }
        )


def test_eval_set_is_well_formed():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)) >= 30
    assert {c["difficulty"] for c in CASES} == {1, 2, 3, 4, 5}


def test_perfect_composer_scores_full_marks():
    run = run_eval(CASES, lambda: RuleComposer(1.0))
    summary = run["summary"]
    assert summary["cases"] == len(CASES)
    assert summary["pass_rate"] == summary["first_draft_rate"] == 1.0
    assert summary["mean_rounds"] == 1
    assert run["prompt_pack"] == prompt_pack_id()


def test_weaker_composer_needs_feedback_and_fails_the_gate():
    good = run_eval(CASES, lambda: RuleComposer(1.0))
    weak = run_eval(CASES, lambda: RuleComposer(0.5))
    assert weak["summary"]["pass_rate"] == 1.0  # feedback rounds still get there
    assert weak["summary"]["first_draft_rate"] < 0.9
    assert weak["summary"]["mean_rounds"] > 1
    problems = gate(weak, good)
    assert problems and problems[0].startswith("first_draft_rate fell from 100%")
    assert gate(good, good) == []


def test_errors_are_recorded_per_case_and_gated():
    class Broken:
        def write(self, system, messages):
            raise RuntimeError("API down")

    good = run_eval(CASES[:3], lambda: RuleComposer(1.0))
    broken = run_eval(CASES[:3], lambda: Broken())
    assert broken["summary"]["pass_rate"] == 0
    assert broken["cases"][0]["error"] == "RuntimeError: API down"
    assert any("used to pass and now fails" in p for p in gate(broken, good))


def test_prompt_pack_changes_when_prompts_change(monkeypatch):
    import duet.evaluation as evaluation

    before = prompt_pack_id()
    monkeypatch.setattr(evaluation, "feedback_message", lambda problems: "different")
    assert prompt_pack_id() != before


def test_cli_eval_with_baseline(tmp_path, monkeypatch, capsys):
    from duet import cli
    from duet.compose import claude

    class Stub(claude.ClaudeComposer):
        def __init__(self, model=None):
            self.model = model or "stub"

        def write(self, system, messages):
            return RuleComposer(1.0).write(system, messages)

    monkeypatch.setattr(claude, "ClaudeComposer", Stub)
    cases = ROOT / "evals" / "prompts.yaml"
    out = tmp_path / "run.json"
    assert cli.main(["eval", str(cases), "--out", str(out), "--limit", "4"]) == 0
    assert "pass 100%" in capsys.readouterr().out
    assert cli.main(["eval", str(cases), "--limit", "4", "--baseline", str(out)]) == 0
    assert "gate: ok" in capsys.readouterr().out
