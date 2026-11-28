import json

import pytest

from duet.profile import keyboard_profile, robot_profile
from duet.protocol import TITLE_BYTES
from duet.score import load_score
from duet.sim import RIG_CHANNELS
from duet.songs import SongError, compile_song, song_title
from helpers import ROOT

RAIN = ROOT / "examples" / "rain-on-the-bottles.json"


def test_a_title_fits_the_device():
    assert song_title("Rain  on\nthe Bottles") == "Rain on the Bottles"  # one line
    long = song_title("Über " * 30)
    assert len(long.encode()) <= TITLE_BYTES and long.endswith("…")
    assert long.startswith("Über Über")


def test_a_song_file_is_its_title_then_its_commands():
    song = compile_song(load_score(RAIN), robot_profile(), keyboard_profile(), RIG_CHANNELS)
    lines = song.song_file().splitlines()
    assert json.loads(lines[0]) == {"title": "Rain on the Bottles"}
    assert lines[1:] == [m.to_json() for m in song.commands]


def test_a_rig_without_a_needed_channel_is_refused():
    with pytest.raises(SongError, match="the rig has no channel for: led_strip"):
        compile_song(load_score(RAIN), robot_profile(), keyboard_profile(), {"carriage_striker": 0})
