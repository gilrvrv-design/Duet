from duet import midi_bot
from duet.conductor import VirtualClock, one_rig, perform
from duet.instruments import instrument
from duet.performers import Bot, performers, repair_bots, score_problems
from duet.profile import robot_profile
from duet.protocol import MIDI_OUT, NoteAt
from duet.score import load_score
from duet.sim import RIG_CHANNELS, SimulatedRig

PIANO = instrument("piano-88")


def duet_of_bots(piano_notes, bottle_notes=()):
    """Two bots, no person: the bottles' carriage and a digital piano over MIDI."""
    events = [
        {"part": "piano", "bar": b, "beat": bt, "dur": d, "pitch": p} for b, bt, d, p in piano_notes
    ] + [
        {"part": "bottles", "bar": b, "beat": bt, "dur": d, "pitch": p}
        for b, bt, d, p in bottle_notes
    ]
    return load_score(
        {
            "meta": {"tempo_bpm": 120},
            "parts": {
                "bottles": {"instrument": "bottles-v1", "performer": "bot"},
                "piano": {"instrument": "piano-88", "performer": "bot"},
            },
            "events": events,
        }
    )


def test_a_bot_plays_the_piano_over_midi():
    score = duet_of_bots([(1, 1, 1, "C4"), (1, 1, 1, "E4"), (1, 2, 2, "G4")], [(1, 1, 1, "C5")])
    bots = {p.part: p for p in performers(score)}
    assert isinstance(bots["piano"], Bot) and not bots["piano"].moves
    assert bots["bottles"].moves
    assert score_problems(score) == {"bottles": [], "piano": []}  # chords are fine


def test_range_and_polyphony_problems_and_their_repair():
    low = duet_of_bots([(1, 1, 1, 12)])  # C0: below A0
    assert "is outside A0-C8" in score_problems(low)["piano"][0]
    fixed = repair_bots(low)
    assert [e.pitch for e in fixed.score.part_events("piano")] == [24]  # up an octave: C1
    assert score_problems(fixed.score)["piano"] == []

    cluster = duet_of_bots([(1, 1, 1, 40 + i) for i in range(20)])  # 20 notes at once
    assert "20 notes at once (polyphony 16)" in score_problems(cluster)["piano"][0]
    thinned = repair_bots(cluster).score
    kept = sorted(e.pitch for e in thinned.part_events("piano"))
    assert kept == list(range(44, 60))  # the highest 16 stay


def test_notes_become_ons_and_offs_and_a_repeat_is_struck_again():
    score = duet_of_bots([(1, 1, 1, "C4"), (1, 2, 1, "C4")])
    msgs = midi_bot.messages(score, "piano", PIANO, lambda s: round(s * 1_000_000))
    assert [(m.t_us, m.vel > 0) for m in msgs] == [
        (0, True),
        (500_000, False),  # the first C4 ends...
        (500_000, True),  # ...before the second starts
        (1_000_000, False),
    ]
    assert all(isinstance(m, NoteAt) and m.midi == 0 and m.pitch == 60 for m in msgs)


def test_both_bots_play_on_one_rig():
    score = duet_of_bots([(1, 1, 1, "C4"), (1, 2, 1, "E4")], [(1, 1, 1, "C5"), (1, 3, 1, "E5")])
    rig = SimulatedRig(robot_profile())
    perf = perform(score, one_rig(score, [rig]), VirtualClock())
    rig.run()
    assert rig.faults == []
    assert len(rig.sounds) == 2  # the carriage struck both bottles
    ons = [(n.t_us, n.pitch) for n in rig.notes if n.vel > 0]
    played = [(p.t_us, p.pitch) for p in perf.planned if p.part == "piano"]
    assert ons == played == [(ons[0][0], 60), (ons[0][0] + 500_000, 64)]
    assert all(n.ch == RIG_CHANNELS[MIDI_OUT] for n in rig.notes)
    assert len(rig.notes) == 4  # every note is also released
