"""Contract test: the firmware core's MIDI importer (duet_midi.cpp), which makes a duet
on the device with no server, makes the same score as the Hub's duet.midi_io.read_midi:
the same tempo, time signature, warnings and events, to the last bit of every float."""

import io
import json
import random
import shutil
import subprocess

import mido
import pytest

from duet.midi_io import read_midi, score_to_midi_bytes
from duet.score import load_score
from helpers import ROOT

FIRMWARE = ROOT / "firmware"
pytestmark = pytest.mark.skipif(shutil.which("g++") is None, reason="needs a C++ compiler")


@pytest.fixture(scope="module")
def firmware_cli():
    subprocess.run(["make", "-s", "-C", str(FIRMWARE), "build/duet_core_cli"], check=True)
    return FIRMWARE / "build" / "duet_core_cli"


def device(cli, data: bytes, tmp_path) -> dict:
    path = tmp_path / "upload.mid"
    path.write_bytes(data)
    out = subprocess.run([str(cli), "--midi", str(path)], capture_output=True, text=True)
    return json.loads(out.stdout)


def hub(data: bytes) -> dict:
    score, warnings = read_midi(data)
    return {
        "tempo_bpm": score.meta.tempo_bpm,
        "time_signature": list(score.meta.time_signature),
        "warnings": warnings,
        "events": [
            {
                "part": e.part,
                "bar": e.bar,
                "beat": e.beat,
                "dur": e.dur,
                "pitch": e.pitch,
                "vel": e.vel,
            }
            for e in score.events
        ],
    }


def midi(*tracks, ticks_per_beat=480, type=1) -> bytes:
    """A file of tracks, each a list of (absolute tick, message) kept in its order."""
    file = mido.MidiFile(type=type, ticks_per_beat=ticks_per_beat)
    for events in tracks:
        track = mido.MidiTrack()
        now = 0
        for tick, msg in sorted(events, key=lambda e: e[0]):
            track.append(msg.copy(time=tick - now))
            now = tick
        file.tracks.append(track)
    buffer = io.BytesIO()
    file.save(file=buffer)
    return buffer.getvalue()


def notes(*spec, channel=0, release_with_note_on=False):
    """(start, end, pitch, vel) notes as messages; at a tick, releases come first."""
    events = []
    for start, end, pitch, vel in spec:
        events.append(
            (start, 1, mido.Message("note_on", channel=channel, note=pitch, velocity=vel))
        )
        off = (
            mido.Message("note_on", channel=channel, note=pitch, velocity=0)
            if release_with_note_on
            else mido.Message("note_off", channel=channel, note=pitch)
        )
        events.append((end, 0, off))
    return [(tick, msg) for tick, _, msg in sorted(events, key=lambda e: (e[0], e[1]))]


def meta(tick, kind, **fields):
    return (tick, mido.MetaMessage(kind, **fields))


def tempo(bpm, tick=0):
    return meta(tick, "set_tempo", tempo=mido.bpm2tempo(bpm))


def signature(beats, unit, tick=0):
    return meta(tick, "time_signature", numerator=beats, denominator=unit)


MELODY = notes((0, 240, 72, 90), (240, 480, 74, 80), (480, 960, 76, 70), (960, 1000, 79, 100))
BASS = notes((0, 960, 48, 60), (960, 1920, 43, 60))
CHORDS = notes(
    *[(0, 480, p, 70) for p in (60, 64, 67)],  # C major
    *[(480, 960, 62, 70), (480, 720, 65, 70), (480, 960, 69, 90)],
    (960, 1440, 55, 50),  # one note alone
    # Two G4s on top: the first is the bot's.
    *[(1440, 1920, 67, 80), (1440, 1700, 67, 81), (1440, 1920, 59, 60)],
)


def random_file(seed: int) -> bytes:
    rng = random.Random(seed)
    beats, unit = rng.choice([(2, 2), (3, 4), (4, 4), (5, 4), (6, 8), (7, 8), (12, 16)])
    tracks = [[signature(beats, unit), tempo(rng.uniform(30, 250))]]
    for _ in range(rng.randint(1, 3)):
        spec = []
        for _ in range(rng.randint(1, 40)):
            start = rng.randrange(0, 20_000)
            spec.append(
                (start, start + rng.randrange(0, 2000), rng.randint(30, 100), rng.randint(1, 127))
            )
        tracks.append(notes(*spec, channel=rng.randrange(16)))
    return midi(*tracks, ticks_per_beat=rng.choice([1, 7, 96, 100, 192, 384, 480, 960, 1000]))


EXAMPLE = score_to_midi_bytes(load_score(ROOT / "examples" / "rain-on-the-bottles.json"))

CASES = {
    "example": EXAMPLE,
    "two-unnamed-tracks": midi([tempo(96)], BASS, MELODY),
    "named-tracks": midi(
        [meta(0, "track_name", name=" Robot\t")] + BASS,  # the name beats the pitch
        [meta(0, "track_name", name="PIANIST")] + MELODY,
    ),
    "one-named-track": midi([meta(0, "track_name", name="robot")] + BASS, MELODY),
    "other-names": midi(
        [meta(0, "track_name", name="Bass")] + BASS, [meta(0, "track_name", name="Lead")] + MELODY
    ),
    "skyline": midi(CHORDS),
    "skyline-format-0": midi(CHORDS + notes((0, 480, 40, 50), channel=3), type=0),
    "running-status": midi(
        notes((0, 100, 60, 64), (100, 120, 62, 64), (120, 127, 64, 64), release_with_note_on=True)
    ),
    "later-changes": midi(
        [
            tempo(120),
            signature(4, 4),
            tempo(120, 960),
            tempo(90, 1920),
            tempo(100, 2880),
            signature(3, 4, 1920),
            signature(4, 4, 2880),
        ],
        MELODY,
        [tempo(60), signature(6, 8)] + BASS,
    ),
    "unreleased": midi(
        MELODY + [(1200, mido.Message("note_on", note=81, velocity=70))],
        BASS
        + [
            (5, mido.Message("note_on", note=36, velocity=70)),
            (2000, mido.Message("note_off", note=99)),
        ],
    ),
    "same-key-overlap": midi(
        [
            (0, mido.Message("note_on", note=60, velocity=70)),
            (240, mido.Message("note_on", note=60, velocity=80)),
            (480, mido.Message("note_off", note=60)),
            (480, mido.Message("note_on", note=60, velocity=90)),
            (720, mido.Message("note_on", note=60, velocity=0)),
            (960, mido.Message("note_off", note=60)),
            (960, mido.Message("note_on", note=60, velocity=50, channel=1)),
            (960, mido.Message("note_on", note=60, velocity=50, channel=1)),
            (1000, mido.Message("note_off", note=60, channel=1)),
            (1000, mido.Message("note_off", note=60, channel=1)),
        ]
    ),
    "three-four": midi([signature(3, 4), tempo(72)], MELODY, BASS),
    "six-eight": midi([signature(6, 8), tempo(50)], MELODY, BASS),
    "too-fast": midi([meta(0, "set_tempo", tempo=50_000), signature(4, 16)], MELODY),
    "too-slow": midi([meta(0, "set_tempo", tempo=4_000_000)], MELODY),
    "default-tempo-and-metre": midi(MELODY),
    "zero-length-notes": midi(notes((0, 0, 60, 70), (7, 7, 62, 70), (480, 481, 64, 70))),
    **{
        f"ticks-per-beat-{tpb}": midi(
            [signature(3, 8)],
            notes(*((i * 37, i * 37 + 1 + i % 11, 60 + i % 20, 64) for i in range(60))),
            notes((0, tpb * 6, 40, 60), (tpb * 3, tpb * 9, 45, 60)),
            ticks_per_beat=tpb,
        )
        for tpb in (96, 384, 1000, 7)
    },
    **{f"random-{seed}": random_file(seed) for seed in range(40)},
}


@pytest.mark.parametrize("data", CASES.values(), ids=CASES.keys())
def test_device_and_hub_import_the_same_duet(data, firmware_cli, tmp_path):
    assert device(firmware_cli, data, tmp_path) == hub(data)


def test_the_cases_cover_what_they_claim():
    running = CASES["running-status"]
    assert running.count(b"\x90") == 1  # one status byte for six note messages
    assert hub(CASES["later-changes"])["warnings"] == [
        "3 later tempo change(s) ignored: one tempo per score",
        "2 later time signature change(s) ignored",
    ]
    assert hub(CASES["unreleased"])["warnings"] == ["2 note(s) never released were left out"]
    assert "outside what a score allows; using 300" in hub(CASES["too-fast"])["warnings"][0]
    assert "using 20.1" in hub(CASES["too-slow"])["warnings"][0]
    parts = {e["part"] for e in hub(CASES["skyline"])["events"]}
    assert parts == {"robot", "pianist"}


@pytest.mark.parametrize(
    "data",
    [EXAMPLE[:n] for n in range(0, len(EXAMPLE), 13)] + [midi([tempo(100)], [])],
    ids=lambda d: f"{len(d)}-bytes",
)
def test_device_and_hub_both_refuse_a_broken_file(data, firmware_cli, tmp_path):
    with pytest.raises(Exception):  # noqa: B017 - mido and the score raise many kinds
        read_midi(data)
    assert device(firmware_cli, data, tmp_path)["error"]


def test_a_doubled_note_leaves_the_top_to_the_bot():
    """Two identical notes at one onset (channel 1, velocity 50): one each, not both to
    the pianist."""
    doubled = [e for e in hub(CASES["same-key-overlap"])["events"] if e["vel"] == 50]
    assert sorted(e["part"] for e in doubled) == ["pianist", "robot"]


def test_a_file_with_no_notes_says_so(firmware_cli, tmp_path):
    empty = midi([tempo(100)], [])
    with pytest.raises(ValueError, match="the file has no notes"):
        read_midi(empty)
    assert device(firmware_cli, empty, tmp_path)["error"] == "the file has no notes"
