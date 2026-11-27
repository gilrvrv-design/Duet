import pytest

from duet.jobs import JobFailure, JobRunner, job_view
from duet.storage import MemoryStore


@pytest.fixture
def runner():
    runner = JobRunner(MemoryStore())
    yield runner
    runner.shutdown()


def test_job_reports_progress_and_result(runner):
    def work(progress):
        progress("step one", 0.25)
        progress("step two", None)
        return {"answer": 42}

    job = runner.wait(runner.submit("test", work).id)
    view = job_view(job)
    assert view["state"] == "succeeded" and view["result"] == {"answer": 42}
    assert [e["stage"] for e in job.meta["events"]] == [
        "queued",
        "started",
        "step one",
        "step two",
        "done",
    ]
    assert view["progress"] == 1.0


def test_job_failures_are_recorded(runner, capsys):
    def coded(progress):
        raise JobFailure("BAD_INPUT", "no good")

    def crash(progress):
        raise ValueError("boom")

    assert job_view(runner.wait(runner.submit("t", coded).id))["error"] == {
        "code": "BAD_INPUT",
        "detail": "no good",
    }
    error = job_view(runner.wait(runner.submit("t", crash).id))["error"]
    assert error == {"code": "INTERNAL", "detail": "ValueError: boom"}


def test_compose_and_transcribe_report_stages():
    from duet.audio.pipeline import transcribe_file
    from duet.compose import compose
    from helpers import GOOD, REQUEST, ScriptedComposer, synth

    stages = []
    compose(REQUEST, ScriptedComposer(GOOD), progress=lambda s, f=None: stages.append(s))
    assert stages == ["drafting", "checking", "ready"]

    import soundfile

    stages.clear()
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        soundfile.write(tmp.name, synth([(72, 0, 0.4)]), 22050)
        transcribe_file(tmp.name, route="melody", progress=lambda s, f=None: stages.append(s))
    assert stages == ["decoding", "analysing", "transcribing:melody", "ready"]
