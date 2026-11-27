import mido
import pytest

from duet.midi_io import midi_to_score, save_midi, score_to_midi, score_to_midi_bytes
from duet.score import load_score
from helpers import make_score


def notes(score):
    return sorted((e.part, e.bar, e.beat, e.dur, e.pitch, e.vel) for e in score.events)


@pytest.mark.parametrize("signature", [(4, 4), (3, 4), (6, 8)])
def test_round_trip(signature, tmp_path):
    score = make_score(
        robot=[(1, 1, 1, "E5"), (1, 2.5, 0.5, "G5"), (2, 1, 2, "C6")],
        pianist=[(1, 1, 2, "C4"), (1, 1, 2, "G4"), (2, 2, 1, "F4")],
        tempo=96,
        time_signature=signature,
        title="Round trip",
    )
    path = tmp_path / "duet.mid"
    save_midi(score, path)
    back = midi_to_score(path)
    assert notes(back) == notes(score)
    assert back.meta.tempo_bpm == pytest.approx(96)
    assert back.meta.time_signature == signature
    assert midi_to_score(score_to_midi_bytes(score), title="X").meta.title == "X"


def test_export_layout():
    data = make_score(robot=[(1, 1, 1, "C5")], pianist=[(2, 1, 1, "C4")]).to_dict()
    data["sections"] = [{"name": "A", "bars": [1, 2]}]
    data["turns"] = [{"bars": [2, 2], "lead": "pianist"}]
    midi = score_to_midi(load_score(data))
    assert midi.type == 1 and len(midi.tracks) == 3
    markers = [m.text for m in midi.tracks[0] if m.type == "marker"]
    assert markers == ["section:A", "lead:pianist"]
    robot_on = [m for m in midi.tracks[1] if m.type == "note_on"]
    assert robot_on[0].channel == 0 and robot_on[0].note == 72
    tempo = next(m for m in midi.tracks[0] if m.type == "set_tempo")
    assert tempo.tempo == 500_000  # 120 bpm


def _file(*tracks, ticks=480):
    midi = mido.MidiFile(type=1, ticks_per_beat=ticks)
    for name, pitches in tracks:
        track = mido.MidiTrack()
        if name:
            track.append(mido.MetaMessage("track_name", name=name))
        for chord in pitches:
            for p in chord:
                track.append(mido.Message("note_on", note=p, velocity=64, time=0))
            for i, p in enumerate(chord):
                track.append(
                    mido.Message("note_off", note=p, velocity=0, time=ticks if i == 0 else 0)
                )
        midi.tracks.append(track)
    return midi


def test_unnamed_tracks_highest_goes_to_robot():
    score = midi_to_score(_file((None, [[48], [50]]), (None, [[76], [79]])))
    assert [e.pitch for e in score.part_events("robot")] == [76, 79]
    assert [e.pitch for e in score.part_events("pianist")] == [48, 50]


def test_named_tracks_win():
    score = midi_to_score(_file(("Robot", [[48]]), ("Pianist", [[76]])))
    assert [e.pitch for e in score.part_events("robot")] == [48]


def test_single_track_skyline_split():
    score = midi_to_score(_file((None, [[60, 64, 72], [62, 74]])))
    assert [e.pitch for e in score.part_events("robot")] == [72, 74]
    assert sorted(e.pitch for e in score.part_events("pianist")) == [60, 62, 64]


def test_quantize_and_running_status_note_on_zero():
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack(
        [
            mido.Message("note_on", note=72, velocity=90, time=10),
            mido.Message("note_on", note=72, velocity=0, time=470),
        ]
    )
    midi.tracks.append(track)
    score = midi_to_score(midi, quantize_beats=0.25)
    (event,) = score.events
    assert (event.beat, event.dur, event.vel) == (1.0, 1.0, 90)


def test_import_reports_what_it_ignores_or_changes():
    from duet.midi_io import read_midi

    midi = _file((None, [[60], [62]]))
    track = midi.tracks[0]
    track.insert(0, mido.MetaMessage("set_tempo", tempo=4_000_000))  # 15 bpm: too slow
    track.insert(1, mido.MetaMessage("set_tempo", tempo=600_000, time=480))
    track.append(mido.Message("note_on", note=64, velocity=64, time=0))  # never released
    score, warnings = read_midi(midi)
    assert score.meta.tempo_bpm == 20.1
    assert any("tempo change" in w for w in warnings)
    assert any("never released" in w for w in warnings)
    assert any("outside what a score allows" in w for w in warnings)
