import importlib.util

import numpy as np
import pytest
import soundfile

from duet.audio.arranger import arrange, melody_track
from duet.audio.fullmix import FullMixTranscriber, looks_polyphonic
from duet.audio.melody import PyinTranscriber
from duet.audio.pipeline import transcribe_file
from duet.feasibility import check_robot
from duet.profile import robot_profile
from helpers import synth

SR = 22050
# Vocals sing C-E-G-E in bar 1 and G-B-D-B in bar 2; the bass plays C then G.
VOCALS = [(p, i * 0.5, 0.45) for i, p in enumerate([72, 76, 79, 76, 79, 83, 86, 83])]
BASS = [(48, 0.0, 1.9), (43, 2.0, 1.9)]


class FakeSeparator:
    name = "fake"

    def separate(self, path):
        n = int(SR * 4.5)
        return {
            "vocals": synth(VOCALS, total_s=4.5)[:n],
            "bass": synth(BASS, total_s=4.5)[:n],
            "drums": np.random.default_rng(0).normal(0, 0.1, n).astype(np.float32),
            "guitar": np.zeros(n, dtype=np.float32),
        }


def mix_file(tmp_path):
    path = tmp_path / "song.wav"
    soundfile.write(path, synth(VOCALS + BASS + [(64, 0, 1.9), (67, 0, 1.9)]), SR)
    return path


def test_polyphony_detection():
    assert looks_polyphonic(synth([(60, 0, 2), (64, 0, 2), (67, 0, 2)]), SR)
    assert not looks_polyphonic(
        synth([(p, i * 0.5, 0.45) for i, p in enumerate([60, 62, 64, 65])]), SR
    )


def test_full_mix_route_transcribes_pitched_stems(tmp_path):
    engine = FullMixTranscriber(FakeSeparator(), polyphonic=PyinTranscriber())
    result = transcribe_file(mix_file(tmp_path), route="full", full_mix=engine)
    assert result.route == "full"
    assert result.tracks() == ["bass", "vocals"]  # drums skipped, silent guitar skipped
    assert [n.pitch for n in result.notes if n.track == "bass"] == [48, 43]
    assert result.model == "bass:pyin, vocals:pyin"


def test_auto_route(tmp_path):
    engine = FullMixTranscriber(FakeSeparator(), polyphonic=PyinTranscriber())
    assert transcribe_file(mix_file(tmp_path), full_mix=engine).route == "full"
    melody = tmp_path / "hum.wav"
    soundfile.write(melody, synth(VOCALS), SR)
    assert transcribe_file(melody, full_mix=engine).route == "melody"


def test_auto_route_warns_without_full_mix(tmp_path, monkeypatch):
    from duet.audio import fullmix

    monkeypatch.setattr(fullmix, "full_mix_available", lambda: False)
    result = transcribe_file(mix_file(tmp_path))
    assert result.route == "melody" and "more than one voice" in result.warnings[-1]
    with pytest.raises(fullmix.RouteUnavailable, match="pip install demucs basic-pitch"):
        transcribe_file(mix_file(tmp_path), route="full")


def test_arranger_uses_vocals_and_backing_for_chords(tmp_path):
    engine = FullMixTranscriber(FakeSeparator(), polyphonic=PyinTranscriber())
    result = transcribe_file(mix_file(tmp_path), route="full", full_mix=engine)
    assert {n.track for n in melody_track(result)} == {"vocals"}
    arrangement = arrange(result)
    assert arrangement.chords[:2] == ["C", "G"]
    assert check_robot(arrangement.score, robot_profile(), part="robot").ok


@pytest.mark.skipif(
    importlib.util.find_spec("basic_pitch") is None, reason="basic-pitch is not installed"
)
def test_basic_pitch_adapter():
    from duet.audio.fullmix import BasicPitchTranscriber

    chord = synth([(60, 0, 1.5), (64, 0, 1.5), (67, 0, 1.5)])
    pitches = {n.pitch for n in BasicPitchTranscriber().transcribe(chord, SR)}
    assert {60, 64, 67} <= pitches
