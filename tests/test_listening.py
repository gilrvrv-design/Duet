from types import SimpleNamespace

import pytest

from duet.conductor import State, VirtualClock, perform
from duet.listening import Expected, MidiKeys, PlayedNote, SimulatedPianist, grade
from duet.profile import keyboard_profile, robot_profile
from duet.sim import SimulatedRig
from helpers import make_score

ROBOT, PIANO = robot_profile(), keyboard_profile()


def expected(*notes):
    return [Expected(t * 1000, p, bar) for t, p, bar in notes]


def played(*notes):
    return [PlayedNote(t * 1000, p) for t, p in notes]


def test_grading_categories():
    exp = expected((0, 60, 1), (500, 62, 1), (1000, 64, 2), (1500, 65, 2), (2000, 67, 3))
    report = grade(
        exp,
        played((30, 60), (300, 62), (1050, 66), (2600, 67), (2900, 72)),
    )
    assert [g.result for g in report.grades] == ["hit", "early", "wrong", "missed", "missed"]
    assert report.grades[1].offset_ms == -200
    assert report.grades[2].played_pitch == 66
    assert [p.pitch for p in report.extras] == [67, 72]  # 600 ms late is too late to count
    assert report.accuracy == pytest.approx(0.4)
    assert report.hardest_bars() == [2, 3]


def test_feedback_words():
    exp = expected((0, 60, 1), (500, 62, 1), (1000, 64, 2), (1500, 65, 2))
    late = grade(exp, played((60, 60), (560, 62), (1060, 64), (1560, 65)))
    assert late.feedback() == "You played 4 of 4 notes right (100%). You tend to play 60 ms late."
    rough = grade(exp, played((0, 60), (500, 62)))
    assert rough.feedback().startswith("You played 2 of 4 notes right (50%). Hardest: bar 2.")
    assert grade([], []).accuracy == 1.0


SCORE = make_score(
    robot=[(1, 1, 1, "E5"), (1, 3, 1, "G5"), (2, 1, 1, "E5")],
    pianist=[(1, 2, 1, "C4"), (2, 2, 1, "G4")],
    tempo=60,
)


def run(keys):
    rig = SimulatedRig(ROBOT)
    perf = perform(SCORE, ROBOT, PIANO, [rig], VirtualClock(), keys=keys)
    rig.run()
    return perf, rig


def test_wait_mode_shifts_everything_after_each_pianist_note():
    fixed, fixed_rig = run(None)
    waited, rig = run(SimulatedPianist(reaction_s=0.4))
    assert rig.faults == []
    assert waited.waited_us == 800_000  # two cues, 0.4 s each
    assert State.WAITING in waited.states
    shift = [w.t_us - f.t_us for w, f in zip(rig.sounds, fixed_rig.sounds, strict=True)]
    # Robot note before the first cue is unchanged; after cue 1 +0.4 s; after cue 2 +0.8 s.
    assert shift == [0, 400_000, 400_000]
    report = grade(waited.expected_pianist(), waited.played)
    assert [g.result for g in report.grades] == ["hit", "hit"]


def test_wait_mode_keeps_waiting_through_a_wrong_key():
    perf, rig = run(SimulatedPianist(reaction_s=0.4, wrong_first={0}))
    assert rig.faults == []
    report = grade(perf.expected_pianist(), perf.played)
    assert [g.result for g in report.grades] == ["hit", "hit"]
    assert [p.pitch for p in report.extras] == [61]  # the wrong key, then the right one


def test_wait_mode_needs_every_key_of_a_chord():
    class Port:
        def __init__(self, notes):
            self.notes = notes

        def iter_pending(self):
            out, self.notes = self.notes, []
            return out

    clock = VirtualClock(1_000_000)
    note = lambda n: SimpleNamespace(type="note_on", note=n, velocity=70)  # noqa: E731
    keys = MidiKeys(Port([note(60), SimpleNamespace(type="note_on", note=64, velocity=0)]))
    keys.port.notes.append(note(67))
    assert keys.wait_for(frozenset({60, 67}), 0, clock) == 1_000_000
    timeout = MidiKeys(Port([note(60)]), timeout_s=0)
    assert timeout.wait_for(frozenset({60, 64}), 0, clock) == 1_000_000  # gives up, plays on


def test_cli_wait_mode_and_grade(tmp_path, capsys):
    import mido

    from duet.cli import main

    score = tmp_path / "s.json"
    score.write_text(SCORE.to_json())
    assert main(["play", str(score), "--sim", "--wait", "--reaction", "0.2"]) == 0
    out = capsys.readouterr().out
    assert "waited 0.4 s" in out and "You played 2 of 2 notes right (100%)" in out

    # A recording that starts 1 s late, plays C4 on time and G4 1.5 s late (missed).
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    track.append(mido.MetaMessage("set_tempo", tempo=1_000_000))  # 60 bpm: 480 ticks = 1 s
    for delta, note in ((960, 60), (2400, 67)):
        track.append(mido.Message("note_on", note=note, velocity=80, time=delta))
        track.append(mido.Message("note_off", note=note, velocity=0, time=240))
    midi.tracks.append(track)
    played = tmp_path / "played.mid"
    midi.save(played)
    assert main(["grade", str(score), str(played)]) == 0
    out = capsys.readouterr().out
    assert "bar 2: missed" in out and "You played 1 of 2 notes right (50%)" in out
