"""Contract test: the firmware's planner (duet_planner.cpp), which makes a song of a MIDI
file on the device with no server, makes the same song as the Hub: read_midi, then
repair_bots and compile_song for the rig's channels, command by command, to the last
bit of every float, and refuses what the Hub refuses."""

import json
import random
import shutil
import subprocess
import sys

import pytest

from duet.midi_io import read_midi
from duet.performers import in_use, repair_bots
from duet.profile import keyboard_profile, robot_profile
from duet.score import Duo
from duet.sim import RIG_CHANNELS
from duet.songs import MAX_LINES, SongError, compile_song
from helpers import ROOT
from test_midi_contract import CASES, meta, midi, notes, signature, tempo

FIRMWARE = ROOT / "firmware"
pytestmark = pytest.mark.skipif(shutil.which("g++") is None, reason="needs a C++ compiler")
REPAIR_FAILED = "repair left violations"  # the Hub's AssertionError: a bug either side


def device(cli, data: bytes, tmp_path, instrument: str) -> list[dict] | dict:
    path = tmp_path / "upload.mid"
    path.write_bytes(data)
    out = subprocess.run(
        [str(cli), "--song", str(path), instrument], capture_output=True, text=True
    )
    lines = [json.loads(line) for line in out.stdout.splitlines()]
    if out.returncode:
        (refusal,) = lines
        if refusal["error"].startswith(REPAIR_FAILED):  # the device says which violation
            return {"error": REPAIR_FAILED}
        return refusal
    return lines


def repaired(data: bytes, instrument: str):
    score = read_midi(data, duo=Duo(bot_instrument=instrument))[0]
    robot, keyboard = robot_profile(instrument), keyboard_profile()
    return repair_bots(score, in_use(robot, keyboard)), robot, keyboard


def hub(data: bytes, instrument: str) -> list[dict] | dict:
    """What `duet song` and the server make of the file for the rig."""
    try:
        result, robot, keyboard = repaired(data, instrument)
        song = compile_song(result.score, robot, keyboard, RIG_CHANNELS)
    except AssertionError as exc:
        assert str(exc).startswith(REPAIR_FAILED)
        return {"error": REPAIR_FAILED}
    except SongError as exc:
        return {"error": str(exc)}
    return [json.loads(m.to_json()) for m in song.commands]


def track(name: str, *spec, channel=0):
    return [meta(0, "track_name", name=name), *notes(*spec, channel=channel)]


def run(start: int, step: int, pitches, length: int | None = None, vel: int = 90):
    """Notes every ``step`` ticks from ``start``, each ``length`` long (default: legato)."""
    length = length or step
    return [(start + i * step, start + i * step + length, p, vel) for i, p in enumerate(pitches)]


SCALE = [72, 74, 76, 77, 79, 81, 83, 84]  # the bottles, low to high
LEAPS = [72, 84] * 12  # end to end of the carriage
ACCOMPANIMENT = track("pianist", *run(0, 480, [48, 52, 55, 60] * 4))


def random_duet(seed: int) -> bytes:
    """A bot part that is often too fast, too wide or too dense, over a playable piano."""
    rng = random.Random(seed)
    beats, unit = rng.choice([(2, 2), (3, 4), (4, 4), (6, 8), (7, 8)])
    step = rng.choice([30, 60, 120, 240])
    bot, start = [], 0
    for _ in range(rng.randint(5, 80)):
        start += rng.choice([0, step, step, 2 * step, 3 * step])
        bot.append(
            (start, start + rng.randrange(1, 4 * step), rng.randint(55, 100), rng.randint(1, 127))
        )
    human = [
        (rng.randrange(0, start + 1), 0, rng.randint(21, 108), 60)
        for _ in range(rng.randint(0, 40))
    ]
    human = [(s, s + rng.randrange(1, 960), p, v) for s, _, p, v in human]
    return midi(
        [signature(beats, unit), tempo(rng.uniform(40, 220))],
        track("robot", *bot),
        track("pianist", *human, channel=1),
        ticks_per_beat=rng.choice([96, 480, 1000]),
    )


PLANNER_CASES = {
    "playable-scale": midi([tempo(90)], track("robot", *run(0, 480, SCALE)), ACCOMPANIMENT),
    "out-of-range-bot-notes": midi(
        [tempo(80)],
        track("robot", *run(0, 480, [40, 61, 66, 71, 90, 100, 127, 0])),  # folds both ways
        ACCOMPANIMENT,
    ),
    "bot-chords": midi(
        [tempo(70)],
        track("robot", *[(t, t + 480, p, 80) for t in (0, 960, 1920) for p in (72, 76, 79)]),
        ACCOMPANIMENT,
    ),
    # Pairs of neighbouring bottles half a beat apart: each second note moves later.
    "near-pairs-shift": midi(
        [tempo(120)],
        track(
            "robot",
            *[
                (t, t + 240, p, 80)
                for i, t in enumerate(range(0, 6720, 960))
                for t, p in ((t, SCALE[i % 7]), (t + 240, SCALE[i % 7 + 1]))
            ],
        ),
        ACCOMPANIMENT,
    ),
    "faster-leaps-drop": midi([tempo(150)], track("robot", *run(0, 60, LEAPS)), ACCOMPANIMENT),
    # Too many drops, so the Hub tries a slower tempo: here it plays the scale at 95 bpm.
    "tempo-retry": midi(
        [tempo(120)], track("robot", *run(0, 240, SCALE + SCALE[-2::-1])), ACCOMPANIMENT
    ),
    "tempo-retry-to-the-slowest": midi(
        [tempo(300)], track("robot", *run(0, 40, [72, 84, 76, 83] * 10)), ACCOMPANIMENT
    ),
    # Even 40 bpm drops as many: the tempo stays.
    "tempo-retry-no-better": midi(
        [tempo(240)], track("robot", *run(0, 120, LEAPS * 2)), ACCOMPANIMENT
    ),
    "duty-limit": midi(
        [tempo(120)], track("robot", *run(0, 120, [79] * 160, length=60, vel=127)), ACCOMPANIMENT
    ),
    "keyboard-edges": midi(
        [tempo(100)],
        track("robot", *run(0, 480, SCALE)),
        track(
            "pianist",
            (0, 480, 21, 70),
            (480, 960, 22, 70),
            (960, 1440, 107, 70),
            (1440, 1920, 108, 70),
            (1440, 1920, 21, 70),
            channel=1,
        ),
    ),
    "key-below-the-keyboard": midi(
        [tempo(100)], track("robot", *run(0, 480, SCALE)), track("pianist", (480, 960, 20, 70))
    ),
    "key-above-the-keyboard": midi(
        [tempo(100)],
        track("robot", *run(0, 480, SCALE)),
        track("pianist", (960, 1200, 109, 70), (480, 960, 127, 70)),  # the first in time counts
    ),
    # A gap that is the travel time give or take float noise: repair and check must agree
    # it is enough (they once disagreed, and repair failed).
    "gap-a-hair-short": midi(
        [tempo(40)], track("robot", (0, 21, 74, 80), (21, 50, 72, 80)), ticks_per_beat=100
    ),
    "only-the-pianist": midi(track("pianist", *run(0, 240, [60, 64, 67, 72]))),
    "only-the-bot": midi(track("robot", *run(0, 240, SCALE))),
    "too-many-commands": midi(
        [tempo(200)], track("pianist", *run(0, 120, [60 + i % 24 for i in range(1001)]))
    ),
    "six-eight-count-in": midi(
        [signature(6, 8), tempo(66)], track("robot", *run(0, 240, SCALE)), ACCOMPANIMENT
    ),
    **{f"random-duet-{seed}": random_duet(seed) for seed in range(60)},
}
ALL = {**CASES, **PLANNER_CASES}


@pytest.mark.parametrize("data", ALL.values(), ids=ALL.keys())
def test_device_and_hub_plan_the_same_song(data, firmware_cli, tmp_path):
    assert device(firmware_cli, data, tmp_path, "bottles-v1") == hub(data, "bottles-v1")


@pytest.mark.parametrize(
    "name", ["example", "near-pairs-shift", "tempo-retry", "duty-limit", "random-duet-3"]
)
def test_the_same_on_another_carriage_instrument(name, firmware_cli, tmp_path):
    data = ALL[name]
    assert device(firmware_cli, data, tmp_path, "glock-v1") == hub(data, "glock-v1")


def changes(name: str) -> set[str]:
    return {c.kind for c in repaired(ALL[name], "bottles-v1")[0].changes}


def test_the_cases_cover_what_they_claim():
    assert changes("playable-scale") == set()
    assert "fold" in changes("out-of-range-bot-notes")
    assert changes("bot-chords") == {"drop"}
    assert changes("near-pairs-shift") == {"shift"}
    assert changes("faster-leaps-drop") == {"drop"}
    assert "tempo" in changes("tempo-retry")
    assert repaired(ALL["tempo-retry"], "bottles-v1")[0].score.meta.tempo_bpm == 95
    slowest = repaired(ALL["tempo-retry-to-the-slowest"], "bottles-v1")[0].score.meta.tempo_bpm
    assert slowest == 40.0
    no_better = repaired(ALL["tempo-retry-no-better"], "bottles-v1")[0]
    assert no_better.count("drop") > 0.2 * 48 and no_better.count("tempo") == 0
    duty = repaired(ALL["duty-limit"], "bottles-v1")[0].changes
    assert duty and all(c.detail.endswith("duty cycle") for c in duty)
    edges = hub(ALL["keyboard-edges"], "bottles-v1")
    firsts = {(c["first"], c["count"]) for c in edges if c["type"] == "led_frame_at"}
    assert {(1, 2), (174, 2)} <= firsts  # A0 and C8: the strip's 176 LEDs end at 175
    assert hub(ALL["key-below-the-keyboard"], "bottles-v1") == {
        "error": "key 20 is not on the keyboard"
    }
    assert hub(ALL["key-above-the-keyboard"], "bottles-v1") == {
        "error": "key 127 is not on the keyboard"
    }
    assert [c["type"] for c in hub(ALL["gap-a-hair-short"], "bottles-v1")].count("strike_at") == 2
    assert f"at most {MAX_LINES}" in hub(ALL["too-many-commands"], "bottles-v1")["error"]
    kinds = [changes(f"random-duet-{seed}") for seed in range(60)]
    assert all(any(k in c for c in kinds) for k in ("fold", "shift", "drop", "tempo"))


def test_the_firmware_has_the_instruments_the_hub_has(tmp_path):
    """The planner's instrument data is generated from the Hub's instrument files and
    committed; it must not fall behind them (make -C firmware instruments)."""
    fresh = tmp_path / "duet_instrument_data.hpp"
    subprocess.run(
        [sys.executable, str(FIRMWARE / "tools" / "embed_instruments.py"),
         str(ROOT / "src" / "duet" / "profiles"), str(fresh)],
        check=True,
    )  # fmt: skip
    committed = FIRMWARE / "lib" / "duet_core" / "src" / "duet_instrument_data.hpp"
    assert committed.read_text() == fresh.read_text(), "run: make -C firmware instruments"
