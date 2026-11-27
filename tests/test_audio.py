import subprocess

import numpy as np
import pytest
import soundfile

from duet.audio.analysis import estimate_key, estimate_tempo, quantize
from duet.audio.io import AudioError, load_audio
from duet.audio.melody import PyinTranscriber
from duet.audio.notes import NoteEvent
from duet.audio.pipeline import transcribe, transcribe_file, transcription_to_midi
from helpers import synth

SR = 22050
TUNE = [(72, 0.0, 0.45), (76, 0.5, 0.45), (79, 1.0, 0.45), (84, 1.5, 0.9)]


def test_melody_transcription_finds_pitches_and_timing():
    notes = PyinTranscriber().transcribe(synth(TUNE), SR)
    assert [n.pitch for n in notes] == [72, 76, 79, 84]
    for found, (_, start, dur) in zip(notes, TUNE, strict=True):
        assert found.start_s == pytest.approx(start, abs=0.05)
        assert found.duration_s == pytest.approx(dur, abs=0.08)
        assert found.confidence > 0.5


def test_repeated_notes_are_split():
    repeated = [(74, 0.0, 0.3), (74, 0.4, 0.3), (74, 0.8, 0.3)]
    assert [n.pitch for n in PyinTranscriber().transcribe(synth(repeated), SR)] == [74, 74, 74]


def test_silence_gives_no_notes_and_a_warning():
    result = transcribe(np.zeros(SR, dtype=np.float32), SR)
    assert result.notes == [] and "no notes found" in result.warnings[0]


def test_key_estimate():
    scale = [
        NoteEvent(i * 0.5, i * 0.5 + 0.4, p)
        for i, p in enumerate([60, 62, 64, 65, 67, 69, 71, 72, 67, 60])
    ]
    assert estimate_key(scale)[0] == "C major"
    a_minor = [
        NoteEvent(i * 0.5, i * 0.5 + 0.4, p)
        for i, p in enumerate([57, 60, 64, 57, 59, 60, 62, 64, 57, 52])
    ]
    assert estimate_key(a_minor)[0] == "A minor"
    assert estimate_key([])[0] == "C major"


def test_tempo_from_onsets_and_audio():
    at_120 = [NoteEvent(i * 0.5, i * 0.5 + 0.3, 72) for i in range(8)]
    assert estimate_tempo(at_120) == pytest.approx(120, abs=1)
    at_240 = [NoteEvent(i * 0.25, i * 0.25 + 0.2, 72) for i in range(8)]
    assert estimate_tempo(at_240) == pytest.approx(120, abs=1)  # folded into 60-180
    clicks = synth([(84, i * 0.5, 0.1) for i in range(16)])
    assert estimate_tempo([], clicks, SR) == pytest.approx(120, rel=0.05)


def test_quantize_strength():
    notes = [NoteEvent(1.0, 1.5, 60), NoteEvent(1.55, 2.0, 62)]
    full = quantize(notes, 120, grid_beats=0.25, strength=1.0)
    assert [(s, d) for s, d, _ in full] == [(0.0, 1.0), (1.0, 1.0)]
    none = quantize(notes, 120, grid_beats=0.25, strength=0.0)
    assert none[1][0] == pytest.approx(1.1)


def test_file_formats_and_midi(tmp_path):
    wav = tmp_path / "tune.wav"
    soundfile.write(wav, synth(TUNE), 44100 // 2)
    result = transcribe_file(wav)
    assert [n.pitch for n in result.notes] == [72, 76, 79, 84]
    assert result.model == "pyin" and result.key.endswith("major")
    midi = transcription_to_midi(result)
    pitches = [m.note for m in midi.tracks[1] if m.type == "note_on"]
    assert pitches == [72, 76, 79, 84]

    mp3 = tmp_path / "tune.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), str(mp3)], check=True)
    assert [n.pitch for n in transcribe_file(mp3).notes] == [72, 76, 79, 84]


def test_bad_files(tmp_path):
    with pytest.raises(AudioError, match="no such file"):
        load_audio(tmp_path / "missing.wav")
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"not audio")
    with pytest.raises(AudioError, match="cannot decode"):
        load_audio(junk)
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"RIFF")
    with pytest.raises(AudioError, match="cannot read"):
        load_audio(broken)


def test_cli_transcribe(tmp_path, capsys):
    from duet.cli import main

    wav = tmp_path / "hum.wav"
    soundfile.write(wav, synth(TUNE), SR)
    out = tmp_path / "hum.mid"
    assert main(["transcribe", str(wav), str(out)]) == 0
    assert out.exists() and "4 notes" in capsys.readouterr().out
