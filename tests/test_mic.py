import numpy as np
import pytest

from duet.listening import Expected, grade
from duet.mic import MicKeys, MicListener, RobotSound
from duet.pitch import midi_to_hz
from duet.profile import robot_profile

SR = 22050
GLASS = robot_profile().model_copy(
    update={"sound": robot_profile().sound.model_copy(update={"partials": (1.0, 2.7)})}
)


def piano(out, midi, t, dur=0.6):
    """A piano-like tone: harmonics falling as 1/k, fast attack, exponential decay."""
    n = np.arange(int(SR * dur)) / SR
    hz = midi_to_hz(midi)
    tone = sum(np.sin(2 * np.pi * hz * k * n) / k for k in range(1, 7)) * np.exp(-n / 0.4)
    i = int(SR * t)
    release = np.minimum(1, (dur - n) / 0.02)  # dampers come down over 20 ms
    out[i : i + n.size] += 0.25 * tone * np.minimum(1, n / 0.003) * release


def bottle(out, midi, t, dur=1.5):
    """Struck glass: an inharmonic partial at 2.7x and a long ring."""
    n = np.arange(int(SR * dur)) / SR
    hz = GLASS.notes[GLASS.bottle_index(midi)].hz
    tone = (np.sin(2 * np.pi * hz * n) + 0.5 * np.sin(2 * np.pi * 2.7 * hz * n)) * np.exp(-n / 0.6)
    i = int(SR * t)
    out[i : i + n.size] += 0.3 * tone * np.minimum(1, n / 0.002)


def listen(audio, listener, block=1024):
    notes = []
    for i in range(0, audio.size, block):
        notes += listener.feed(audio[i : i + block], 0 if i == 0 else None)
    notes += listener.feed(np.zeros(FRAME_PAD, np.float32))
    return notes


FRAME_PAD = 8192


def test_piano_alone_is_heard_correctly():
    audio = np.zeros(SR * 4, np.float32)
    melody = [(60, 0.5), (64, 1.0), (67, 1.5), (65, 2.0), (62, 2.5), (72, 3.0)]
    for midi, t in melody:
        piano(audio, midi, t)
    notes = listen(audio, MicListener(SR))
    assert [n.pitch for n in notes] == [m for m, _ in melody]
    for note, (_, t) in zip(notes, melody, strict=True):
        assert note.t_us == pytest.approx(t * 1e6, abs=25_000)


# A duet: the robot strikes bottles while the pianist plays, sometimes at the same moment.
ROBOT = [(76, 0.5), (79, 1.25), (76, 2.0), (84, 2.75), (72, 3.5)]
PIANO = [(60, 0.5), (64, 1.0), (67, 2.0), (62, 3.0), (72, 4.0)]  # 72 = a bottle's note (C5)


def duet_audio():
    audio = np.zeros(int(SR * 5.5), np.float32)
    for midi, t in ROBOT:
        bottle(audio, midi, t)
    for midi, t in PIANO:
        piano(audio, midi, t)
    return audio


def expected():
    return [Expected(round(t * 1e6), m, 1) for m, t in PIANO]


def test_self_filtering_hears_only_the_pianist():
    listener = MicListener(SR, robot=GLASS)
    listener.expect_robot([RobotSound(round(t * 1e6), m) for m, t in ROBOT])
    report = grade(expected(), listen(duet_audio(), listener))
    assert [g.result for g in report.grades] == ["hit"] * 5, report.grades
    assert report.extras == []


def test_without_self_filtering_the_bottles_confuse_it():
    report = grade(expected(), listen(duet_audio(), MicListener(SR)))
    assert report.extras or report.accuracy < 1.0


def test_mic_keys_poll_reads_the_source():
    audio = np.zeros(SR * 2, np.float32)
    piano(audio, 64, 0.5)

    class Source:
        def __init__(self):
            self.blocks = [(audio, 0), (np.zeros(FRAME_PAD, np.float32), None)]

        def read(self):
            return self.blocks.pop(0) if self.blocks else (np.zeros(0, np.float32), None)

    keys = MicKeys(MicListener(SR), Source())
    heard = keys.poll(None) + keys.poll(None) + keys.poll(None)
    assert [n.pitch for n in heard] == [64] and keys.played == heard


def test_high_notes_are_not_lowered_an_octave():
    audio = np.zeros(SR * 3, np.float32)
    high = [(84, 0.5), (79, 1.0), (76, 1.5), (83, 2.0)]
    for midi, t in high:
        piano(audio, midi, t)
    assert [n.pitch for n in listen(audio, MicListener(SR))] == [m for m, _ in high]


def test_duet_in_a_noisy_room():
    audio = duet_audio() + np.random.default_rng(1).normal(0, 0.01, int(SR * 5.5)).astype(
        np.float32
    )
    listener = MicListener(SR, robot=GLASS)
    listener.expect_robot([RobotSound(round(t * 1e6), m) for m, t in ROBOT])
    report = grade(expected(), listen(audio, listener))
    assert report.accuracy == 1.0 and report.extras == []


def test_conductor_tells_the_microphone_about_every_strike():
    from duet.conductor import VirtualClock, perform
    from duet.profile import keyboard_profile
    from duet.sim import SimulatedRig
    from helpers import make_score

    class Silent:
        def read(self):
            return np.zeros(0, np.float32), None

    keys = MicKeys(MicListener(SR, robot=GLASS), Silent())
    keys.begin = lambda expected: None
    score = make_score(robot=[(1, 1, 1, "E5"), (1, 3, 1, "G5")], pianist=[(1, 1, 4, "C4")])
    rig = SimulatedRig(GLASS)
    # Follow mode with nobody playing: the robot just keeps going at the written tempo.
    perform(score, GLASS, keyboard_profile(), [rig], VirtualClock(), keys=keys, mode="follow")
    rig.run()
    told = [(s.t_us, s.pitch) for s in keys.listener.robot_sounds]
    assert told == [(s.t_us, s.pitch) for s in rig.sounds]
