"""Calibration (spec §5.11): learn the real rig from a microphone recording.

The sweep: the Hub strikes every bottle once, ``interval_s`` apart, starting at
``first_s`` into the recording. From that one recording we measure, per bottle, the
real pitch, how long it rings and the strike-to-sound latency (FR-K2, FR-K3), and
produce a new, versioned profile. Strike positions come from a loudness sweep (FR-K1).
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass, field

import numpy as np

from duet.instruments import CalibrationInfo, Note
from duet.pitch import cents_between, hz_to_midi, midi_to_hz, midi_to_name
from duet.profile import RobotProfile

DRIFT_WARNING_CENTS = 15.0
SWEEP_INTERVAL_S = 1.0  # time between strikes in a sweep: long enough for a bottle to ring
RENAME_CENTS = 50.0  # keep at or below RobotProfile.tolerance_cents


@dataclass(frozen=True)
class BottleMeasurement:
    index: int
    name: str
    onset_s: float | None
    hz: float | None
    decay_ms: float | None
    latency_ms: float | None

    @property
    def heard(self) -> bool:
        return self.hz is not None


@dataclass
class CalibrationResult:
    profile: RobotProfile
    bottles: list[BottleMeasurement]
    warnings: list[str] = field(default_factory=list)


def plan_sweep(
    profile: RobotProfile, interval_s: float = SWEEP_INTERVAL_S
) -> list[tuple[float, int]]:
    """(time from the start of the sweep, bottle index): every bottle once, in order."""
    return [(i * interval_s, i) for i in range(len(profile.notes))]


def first_onset(audio: np.ndarray, sr: int, silence: float = 0.01) -> float | None:
    """First sample above 20% of the peak, in seconds from the window start.

    A struck bottle reaches its peak within a cycle or two, so this is accurate to about
    a millisecond, which is what latency calibration needs.
    """
    if audio.size == 0:
        return None
    peak = float(np.max(np.abs(audio)))
    if peak < silence:
        return None
    return int(np.argmax(np.abs(audio) >= 0.2 * peak)) / sr


def _pitch(audio: np.ndarray, sr: int, fmin: float, fmax: float) -> float | None:
    """Strongest spectral peak between fmin and fmax, refined by parabolic interpolation.

    Suits struck glass, whose fundamental dominates; resolution is well under a cent.
    """
    if audio.size < sr // 20:
        return None
    n = 1 << 16
    spectrum = np.abs(np.fft.rfft(audio * np.hanning(audio.size), n))
    freqs = np.fft.rfftfreq(n, 1 / sr)
    band = np.nonzero((freqs >= fmin) & (freqs <= fmax))[0]
    if band.size < 3:
        return None
    k = int(band[np.argmax(spectrum[band])])
    a, b, c = np.log(spectrum[k - 1 : k + 2] + 1e-12)
    shift = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
    return float((k + shift) * sr / n)


def _decay_ms(audio: np.ndarray, sr: int, drop_db: float = 40.0) -> float | None:
    """Ring time: how long the level takes to fall ``drop_db`` (T40), from the fade rate.

    Fits a line to the level in dB from the peak down to -30 dB (or the end of the window),
    so a ring that is cut off by the next strike is still measured correctly.
    """
    hop = 256
    if audio.size < 4 * 1024:
        return None
    frames = np.lib.stride_tricks.sliding_window_view(audio, 1024)[::hop]
    level = np.sqrt((frames**2).mean(axis=1)) + 1e-9
    peak = int(np.argmax(level))
    db = 20 * np.log10(level[peak:] / level[peak])
    stop = np.nonzero(db <= -30)[0]
    end = int(stop[0]) if stop.size else int(db.size * 0.9)  # skip a possible cut at the end
    if end < 4:
        return None
    t = np.arange(end) * hop / sr
    slope = np.polyfit(t, db[:end], 1)[0]  # dB per second, negative while it fades
    if slope >= -1:
        return None  # not fading: a sustained tone, or noise
    return round(drop_db / -slope * 1000)


def measure_sweep(
    audio: np.ndarray,
    sr: int,
    profile: RobotProfile,
    first_s: float,
    interval_s: float = SWEEP_INTERVAL_S,
) -> list[BottleMeasurement]:
    """Measure every bottle in a sweep recording (one window per strike)."""
    results = []
    for offset, index in plan_sweep(profile, interval_s):
        start = first_s + offset
        a, b = int(start * sr), int((start + interval_s) * sr)
        window = audio[a:b]
        nominal = profile.notes[index].hz
        onset = first_onset(window, sr)
        if onset is None:
            results.append(
                BottleMeasurement(
                    index, midi_to_name(profile.notes[index].midi), None, None, None, None
                )
            )
            continue
        ring = window[int(onset * sr) :]
        hz = _pitch(ring[: int(0.4 * sr)], sr, nominal / 1.5, nominal * 1.5)
        results.append(
            BottleMeasurement(
                index=index,
                name=midi_to_name(profile.notes[index].midi),
                onset_s=round(start + onset, 4),
                hz=round(hz, 2) if hz else None,
                decay_ms=_decay_ms(ring, sr),  # None if it rings past the window
                latency_ms=round(onset * 1000, 1),
            )
        )
    return results


def apply_measurements(
    profile: RobotProfile, bottles: list[BottleMeasurement], source: str = "sweep"
) -> CalibrationResult:
    """A new instrument from measurements, plus warnings a person should act on."""
    warnings = []
    inst = profile.instrument
    notes = list(inst.notes)
    for m in bottles:
        bottle = profile.notes[m.index]
        if not m.heard:
            warnings.append(f"bottle {m.index + 1} ({m.name}) was not heard; check the striker")
            continue
        drift = cents_between(bottle.hz, m.hz)
        name = bottle.name
        target = midi_to_hz(bottle.midi)
        off_target = cents_between(target, m.hz)
        if abs(off_target) > RENAME_CENTS:
            name = round(hz_to_midi(m.hz))
            warnings.append(
                f"bottle {m.index + 1} now sounds {midi_to_name(name)}, not {m.name}; "
                "it was renamed"
            )
        elif abs(drift) > DRIFT_WARNING_CENTS or abs(off_target) > DRIFT_WARNING_CENTS:
            fix = "pour out a little water" if off_target < 0 else "add a little water"
            warnings.append(
                f"bottle {m.index + 1} ({m.name}) is {off_target:+.0f} cents off: {fix}"
            )
        notes[m.index] = Note(name=name, hz=m.hz)

    heard = [m for m in bottles if m.heard]
    striker, sound = profile.striker, profile.sound
    if heard:
        striker = striker.revised(
            {"latency_ms": round(statistics.median(m.latency_ms for m in heard), 1)}
        )
        decays = [m.decay_ms for m in heard if m.decay_ms]
        if decays:
            sound = sound.revised({"decay_ms": round(statistics.median(decays))})
    version = (profile.calibration.version + 1) if profile.calibration else 1
    info = CalibrationInfo(
        version=version, date=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), source=source
    )
    names = [n.name for n in notes]
    if len(set(names)) != len(names):
        warnings.append("two bottles now sound the same note; retune before playing")
        notes = list(inst.notes)  # keep the old pitches rather than an invalid instrument
    new = inst.revised(
        {
            "notes": tuple(notes),
            "bot": inst.bot.revised({"striker": striker}),
            "sound": sound,
            "calibration": info,
        }
    )
    return CalibrationResult(RobotProfile(new), bottles, warnings)


def calibrate_from_sweep(
    audio: np.ndarray,
    sr: int,
    profile: RobotProfile,
    first_s: float,
    interval_s: float = SWEEP_INTERVAL_S,
) -> CalibrationResult:
    return apply_measurements(profile, measure_sweep(audio, sr, profile, first_s, interval_s))


def best_strike_positions(
    profile: RobotProfile, samples: list[tuple[int, float]], window_steps: int = 1600
) -> tuple[RobotProfile, list[str]]:
    """Loudness sweep (FR-K1): ``samples`` are (carriage steps, loudness of the strike).

    For each bottle, the loudest strike within ``window_steps`` of its current position
    becomes its new position.
    """
    positions, report = [], []
    for i, bottle in enumerate(profile.notes):
        near = [(s, loud) for s, loud in samples if abs(s - bottle.steps) <= window_steps]
        if not near:
            positions.append(bottle.steps)
            report.append(f"bottle {i + 1}: no samples near {bottle.steps} steps; kept")
            continue
        steps = max(near, key=lambda sl: sl[1])[0]
        positions.append(steps)
        report.append(f"bottle {i + 1}: {bottle.steps} -> {steps} steps")
    inst = profile.instrument
    new = inst.revised({"bot": inst.bot.revised({"positions": tuple(positions)})})
    return RobotProfile(new), report
