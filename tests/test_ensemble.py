import mido
import pytest

from duet.conductor import VirtualClock
from duet.ensemble import Instrument, assign, build_players, perform_ensemble, skyline
from duet.feasibility import check_robot
from duet.midi_io import TrackNote, midi_tracks
from duet.profile import keyboard_profile, robot_profile
from duet.sim import SimulatedRig

BOTTLES, GLOCK, PIANO = robot_profile(), robot_profile("glock-v1"), keyboard_profile()

# A three-line piece in C: a high descant, a middle melody, and a bass line.
DESCANT = [(0, 84), (2, 88), (4, 91), (6, 88), (8, 86), (10, 84), (12, 91), (14, 96)]
MELODY = [
    (i, p) for i, p in enumerate([72, 74, 76, 77, 79, 77, 76, 74, 72, 76, 79, 84, 79, 76, 74, 72])
]
BASS = [(0, 48), (4, 55), (8, 53), (12, 48)]


def song(tmp_path):
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    meta = mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=750_000)])  # 80 bpm
    midi.tracks.append(meta)
    for name, notes, length in (("descant", DESCANT, 2), ("melody", MELODY, 1), ("bass", BASS, 4)):
        track = mido.MidiTrack([mido.MetaMessage("track_name", name=name)])
        events = []
        for beat, pitch in notes:
            events.append((beat * 480, 1, mido.Message("note_on", note=pitch, velocity=80)))
            events.append(((beat + length) * 480 - 10, 0, mido.Message("note_off", note=pitch)))
        now = 0
        for tick, _, msg in sorted(events, key=lambda e: (e[0], e[1])):
            track.append(msg.copy(time=tick - now))
            now = tick
        midi.tracks.append(track)
    path = tmp_path / "trio.mid"
    midi.save(path)
    return path


INSTRUMENTS = [
    Instrument("bottles", BOTTLES),
    Instrument("glock", GLOCK),
    Instrument("pianist", low=36, high=72),
]


def test_midi_tracks_and_skyline(tmp_path):
    tempo, signature, tracks = midi_tracks(song(tmp_path))
    assert tempo == 80 and signature == (4, 4)
    assert list(tracks) == ["descant", "melody", "bass"]
    assert [n.pitch for n in tracks["bass"]] == [48, 55, 53, 48]
    chord = [TrackNote(0, 1, 60, 80), TrackNote(0, 1, 67, 80), TrackNote(1, 1, 64, 80)]
    assert [n.pitch for n in skyline(chord)] == [67, 64]


def test_each_line_goes_to_the_instrument_that_fits_it(tmp_path):
    _, _, tracks = midi_tracks(song(tmp_path))
    a = assign(tracks, INSTRUMENTS)
    assert a.transpose == 0  # everything already fits in C
    assert a.parts == {"glock": ("descant", 0), "bottles": ("melody", 0), "pianist": ("bass", 0)}
    assert a.fit == {"glock": 1.0, "bottles": 1.0, "pianist": 1.0}
    two = assign(tracks, INSTRUMENTS[:2])
    assert two.unused == ["bass"]


def test_whole_ensemble_plays_together_on_simulated_rigs(tmp_path):
    tempo, signature, tracks = midi_tracks(song(tmp_path))
    rigs = {
        "bottles": SimulatedRig(BOTTLES),
        "glock": SimulatedRig(GLOCK),
        "pianist": SimulatedRig(BOTTLES),
    }
    devices = {name: [rig] for name, rig in rigs.items()}
    players = build_players(
        tracks, INSTRUMENTS, assign(tracks, INSTRUMENTS), tempo, signature, devices
    )
    for p in players:
        if p.instrument.is_robot:
            assert check_robot(p.score, p.instrument.robot, part="robot").ok
    results = perform_ensemble(players, PIANO, VirtualClock(1_000_000))
    for rig in rigs.values():
        rig.run()
        assert rig.faults == []
    assert [s.pitch for s in rigs["bottles"].sounds] == [p for _, p in MELODY]
    assert [s.pitch for s in rigs["glock"].sounds] == [p for _, p in DESCANT]
    assert rigs["pianist"].sounds == [] and rigs["pianist"].led_frames  # lights only
    assert rigs["bottles"].led_frames == []  # the lights belong to the pianist's strip
    # One clock: the descant's first note and the melody's first note land together.
    beat_us = 60 / 80 * 1e6
    t0 = results["bottles"].start_us
    assert rigs["glock"].sounds[0].t_us == pytest.approx(rigs["bottles"].sounds[0].t_us, abs=1)
    assert rigs["glock"].sounds[1].t_us == pytest.approx(t0 + 2 * beat_us, abs=2)


def test_a_piece_in_d_is_moved_to_c_for_everyone():
    def up(notes, k=2):
        return [TrackNote(b, 1, p + k, 80) for b, p in notes]

    tracks = {"descant": up(DESCANT), "melody": up(MELODY), "bass": up(BASS)}
    a = assign(tracks, INSTRUMENTS)
    assert a.transpose == -2 and all(f == 1.0 for f in a.fit.values())


def test_cli_ensemble(tmp_path, capsys):
    from duet.cli import main

    assert main(["ensemble", str(song(tmp_path)), "--robots", "bottles-v1,glock-v1", "--sim"]) == 0
    out = capsys.readouterr().out
    assert "glock-v1: descant" in out and "bottles-v1: melody" in out and "pianist: bass" in out
    assert "faults: 0" in out
