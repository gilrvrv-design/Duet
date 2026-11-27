import numpy as np
import pytest

from duet.calibration import (
    apply_measurements,
    best_strike_positions,
    calibrate_from_sweep,
    measure_sweep,
    plan_sweep,
)
from duet.pitch import cents_between
from duet.profile import load_profile_file, robot_profile, save_profile_file

SR = 22050
BOTTLES = robot_profile()


def bottle_sweep(detune_cents, latency_s=0.012, decay_s=0.25, first_s=0.5, interval_s=1.0):
    """A recording of the sweep: each bottle rings with an exponential decay."""
    out = np.zeros(int(SR * (first_s + interval_s * len(BOTTLES.notes) + 0.5)), dtype=np.float32)
    t = np.arange(int(SR * interval_s * 0.9)) / SR
    for (offset, i), cents in zip(plan_sweep(BOTTLES, interval_s), detune_cents, strict=True):
        hz = BOTTLES.notes[i].hz * 2 ** (cents / 1200)
        tone = (np.sin(2 * np.pi * hz * t) + 0.3 * np.sin(2 * np.pi * 2.7 * hz * t)) * np.exp(
            -t / decay_s
        )
        start = int(SR * (first_s + offset + latency_s))
        out[start : start + t.size] += 0.4 * tone.astype(np.float32)
    return out


def test_sweep_measures_pitch_latency_and_decay():
    detune = [0, 20, -30, 0, 5, 0, 0, -10]
    measured = measure_sweep(bottle_sweep(detune), SR, BOTTLES, first_s=0.5)
    for m, cents in zip(measured, detune, strict=True):
        assert m.heard
        assert cents_between(BOTTLES.notes[m.index].hz, m.hz) == pytest.approx(cents, abs=6)
        assert m.latency_ms == pytest.approx(12, abs=4)
        # T40 of an exponential with tau 0.25 s is 0.25 * ln(100) = 1151 ms, even though
        # the next strike cuts each ring off at 0.9 s.
        assert m.decay_ms == pytest.approx(1151, rel=0.1)


def test_calibration_updates_profile_and_warns():
    detune = [0, 20, -30, 0, 0, 0, 0, 0]
    result = calibrate_from_sweep(bottle_sweep(detune, latency_s=0.02), SR, BOTTLES, first_s=0.5)
    profile = result.profile
    assert profile.calibration.version == 1
    assert profile.striker.latency_ms == pytest.approx(20, abs=4)
    assert profile.sound.decay_ms == pytest.approx(1151, rel=0.1)
    assert cents_between(BOTTLES.notes[1].hz, profile.notes[1].hz) == pytest.approx(20, abs=6)
    assert any(
        w.startswith("bottle 2 (D5) is +2") and "add a little water" in w for w in result.warnings
    )
    assert any(w.startswith("bottle 3 (E5) is -3") and "pour out" in w for w in result.warnings)
    again = apply_measurements(profile, result.bottles)
    assert again.profile.calibration.version == 2


def test_badly_detuned_bottle_is_renamed_and_silent_bottle_reported():
    detune = [0, 0, 0, 0, 0, 0, 0, 0]
    audio = bottle_sweep(detune)
    # Bottle 5 (G5) now sounds G#5; bottle 8 is silent.
    measured = measure_sweep(audio, SR, BOTTLES, first_s=0.5)
    sharp = measured[4].__class__(**{**measured[4].__dict__, "hz": 830.6})
    silent = measured[7].__class__(**{**measured[7].__dict__, "hz": None, "onset_s": None})
    result = apply_measurements(BOTTLES, [*measured[:4], sharp, *measured[5:7], silent])
    assert result.profile.notes[4].name == 80  # G#5
    assert any("now sounds G#5" in w for w in result.warnings)
    assert any("bottle 8 (C6) was not heard" in w for w in result.warnings)


def test_strike_positions_from_loudness_sweep():
    samples = [(s, 1.0 - abs(s - 1500) / 2000) for s in range(800, 2400, 100)]  # loudest at 1500
    profile, report = best_strike_positions(BOTTLES, samples)
    assert profile.notes[0].steps == 1500
    assert report[0] == "bottle 1: 1200 -> 1500 steps"
    assert "kept" in report[1]


def test_profile_save_and_load(tmp_path):
    result = calibrate_from_sweep(bottle_sweep([0] * 8), SR, BOTTLES, first_s=0.5)
    path = tmp_path / "calibrated.yaml"
    save_profile_file(result.profile, path)
    assert load_profile_file(path) == result.profile


def test_cli_sweep_and_calibrate(tmp_path, capsys):
    import soundfile

    from duet.cli import main
    from duet.score import load_score

    sweep = tmp_path / "sweep.json"
    assert main(["sweep", str(sweep)]) == 0
    assert [e.pitch for e in load_score(sweep).part_events("robot")] == BOTTLES.pitches

    wav = tmp_path / "sweep.wav"
    soundfile.write(wav, bottle_sweep([0, 0, 25, 0, 0, 0, 0, 0], first_s=1.3), SR)
    out = tmp_path / "cal.yaml"
    assert main(["calibrate", str(wav), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "bottle 3 (E5) is +25 cents off" in text and "saved calibration v1" in text
    assert main(["--robot", str(out), "check", str(sweep)]) == 0
