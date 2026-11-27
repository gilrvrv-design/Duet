"""Load any audio (or video) file as mono float samples (spec §5.14 FR-A1)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np

DEFAULT_SR = 22050
NATIVE = {".wav", ".flac", ".ogg", ".aiff", ".aif"}
MAX_SECONDS = 15 * 60
DECODE_TIMEOUT_S = 120  # FFmpeg decodes 15 minutes of audio in a few seconds


class AudioError(ValueError):
    pass


def load_audio(path: str | Path, sr: int = DEFAULT_SR, max_seconds: float = MAX_SECONDS):
    """Return (samples, sr): mono float32 in [-1, 1], resampled to ``sr``."""
    path = Path(path)
    if not path.is_file():
        raise AudioError(f"no such file: {path}")
    too_long = AudioError(f"audio is longer than {max_seconds / 60:g} minutes")
    if path.suffix.lower() in NATIVE:
        audio, native_sr = _read_soundfile(path, max_seconds, too_long)
    else:
        # Decode one second more than allowed: enough to tell it is too long, never more.
        audio, native_sr = _read_ffmpeg(path, sr, max_seconds + 1), sr
        if audio.size / sr > max_seconds:
            raise too_long
    if audio.size == 0:
        raise AudioError("the file has no audio")
    if native_sr != sr:
        import librosa

        audio = librosa.resample(audio, orig_sr=native_sr, target_sr=sr)
    return audio.astype(np.float32), sr


def _read_soundfile(path: Path, max_seconds: float, too_long: AudioError):
    """Check the length from the header before reading any samples."""
    import soundfile

    try:
        info = soundfile.info(str(path))
        if info.frames / info.samplerate > max_seconds:
            raise too_long
        audio, sr = soundfile.read(str(path), dtype="float32", always_2d=True)
    except RuntimeError as exc:  # soundfile.LibsndfileError is a RuntimeError
        raise AudioError(f"cannot read {path.name}: {exc}") from exc
    return audio.mean(axis=1), sr


def _read_ffmpeg(path: Path, sr: int, max_seconds: float) -> np.ndarray:
    """Decode MP3, M4A, Opus, video files and the rest through FFmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AudioError(f"FFmpeg is needed to read {path.suffix} files")
    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        str(path),
        "-t",
        f"{max_seconds:g}",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sr),
        "-f",
        "f32le",
        "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, check=False, timeout=DECODE_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise AudioError(f"decoding {path.name} took too long") from exc
    if result.returncode != 0:
        message = result.stderr.decode(errors="replace").strip().splitlines()
        raise AudioError(
            f"cannot decode {path.name}: {message[-1] if message else 'unknown error'}"
        )
    return np.frombuffer(result.stdout, dtype=np.float32)
