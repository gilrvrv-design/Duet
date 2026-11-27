from duet.conductor import VirtualClock
from duet.feasibility import check_robot
from duet.listening import PlayedNote
from duet.profile import keyboard_profile, robot_profile
from duet.respond import PhraseNote, Responder, capture, reply_score
from duet.session import PhrasePianist, call_and_response
from duet.sim import SimulatedRig

ROBOT, PIANO = robot_profile(), keyboard_profile()
RISING = [PhraseNote(b, 1, p) for b, p in [(0, 60), (1, 62), (2, 64), (3, 65)]]  # C4 D4 E4 F4


def test_capture_quantises_to_half_beats_and_keeps_one_note_per_slot():
    start = 1_000_000
    played = [
        PlayedNote(start + t, p)
        for t, p in [(30_000, 60), (520_000, 62), (530_000, 67), (1_480_000, 64)]
    ]
    phrase = capture(played, start, tempo_bpm=120, beats=4)
    assert [(n.beat, n.pitch) for n in phrase] == [(0.0, 60), (1.0, 62), (3.0, 64)]
    assert [n.dur for n in phrase] == [1.0, 2.0, 1.0]


def test_variations_stay_on_bottles_and_end_home():
    responder = Responder(ROBOT)
    kinds, replies = [], []
    for _ in range(5):
        kind, notes = responder.respond(RISING)
        kinds.append(kind)
        replies.append([n.pitch for n in notes])
    assert kinds == ["echo", "answer", "sequence", "recall", "echo"]
    for pitches in replies:
        assert all(p in ROBOT.pitches for p in pitches)
        assert pitches[-1] % 12 == 0  # ends on C, the bottles' home note
    assert replies[0] == [72, 74, 76, 72]  # the same tune an octave up, ending home
    assert replies[1] == [72, 72, 72, 72]  # the mirror of a rising line, clamped at the bottom
    assert replies[2] == [74, 76, 77, 84]  # one step higher, home on the nearer (top) C
    assert responder.respond([]) == ("rest", [])


def test_reply_keeps_the_session_tempo():
    fast = [PhraseNote(b * 0.5, 0.5, p) for b, p in enumerate([60, 72, 60, 72, 60, 72, 60, 72])]
    _, notes = Responder(ROBOT).respond(fast)
    score = reply_score(notes, 140, ROBOT)
    assert score.meta.tempo_bpm == 140
    assert check_robot(score, ROBOT).ok


PHRASES = [
    [(0, 60), (1, 64), (2, 67), (4, 72)],
    [(0, 67), (1, 65), (2, 64), (3, 62), (6, 60)],
    [(0, 64), (0.5, 65), (1, 67), (3, 64)],
    [(0, 72), (2, 67), (4, 64), (6, 60)],
]


def test_session_alternates_and_the_robot_answers_within_a_beat():
    rig = SimulatedRig(ROBOT)
    pianist = PhrasePianist(PHRASES, tempo_bpm=90)
    clock = VirtualClock(2_000_000)
    session = call_and_response(ROBOT, PIANO, [rig], clock, pianist, tempo_bpm=90, turns=4)
    rig.run()
    assert rig.faults == []
    beat_us = 60 / 90 * 1e6
    assert [t.kind for t in session.turns] == ["echo", "answer", "sequence", "recall"]
    for i, turn in enumerate(session.turns):
        assert turn.reply_start_us - turn.pianist_end_us <= beat_us  # FR-G1: within one beat
        sounds = [
            s
            for s in rig.sounds
            if turn.reply_start_us <= s.t_us < turn.reply_start_us + 8 * beat_us
        ]
        assert [s.pitch for s in sounds] == [n.pitch for n in turn.reply]
        assert len(turn.phrase) == len(PHRASES[i])
        if i + 1 < len(session.turns):
            # The robot is quiet while the pianist plays the next phrase.
            nxt = session.turns[i + 1]
            assert not [
                s for s in rig.sounds if nxt.pianist_start_us <= s.t_us < nxt.pianist_end_us
            ]
    lit = [f for f in rig.led_frames if f.rgb == (0, 40, 90)]
    assert len(lit) == 4  # "your turn" glow at each pianist turn


def test_prediction_of_the_first_answer_note():
    responder = Responder(ROBOT)
    assert responder.predict_first([]) is None
    assert responder.predict_first([60, 62]) == 0  # echo starts on the first note (C)
    responder.respond(RISING)
    responder.respond(RISING)
    assert responder.next_kind() == "sequence"
    assert responder.predict_first([64]) == 3  # E -> one step up: F


def test_cli_jam(capsys):
    from duet.cli import main

    assert main(["jam", "--turns", "2"]) == 0
    out = capsys.readouterr().out
    assert "turn 1: you C4 E4 G4 C5 -> robot echo: C5 E5 G5 C6" in out
    assert "turn 2:" in out and "faults: 0" in out
