import pytest

from duet.audio.arranger import arrange, best_transpose, coverage, suggest_retuning
from duet.audio.notes import NoteEvent
from duet.audio.pipeline import Transcription
from duet.difficulty import check_pianist, pianist_difficulty
from duet.feasibility import check_robot
from duet.profile import keyboard_profile, robot_profile

BOTTLES = robot_profile()
PIANO = keyboard_profile()


def melody(pitches, beat_s=0.5):
    return Transcription(
        notes=[NoteEvent(i * beat_s, i * beat_s + beat_s * 0.9, p) for i, p in enumerate(pitches)],
        tempo_bpm=60 / beat_s,
        key="C major",
        duration_s=len(pitches) * beat_s,
        model="test",
    )


# "Twinkle" in G major, an octave below the bottles.
TWINKLE_G = [55, 55, 62, 62, 64, 64, 62, 60, 60, 59, 59, 57, 57, 55]


def test_transpose_finds_the_bottle_key():
    assert best_transpose([60, 64, 67], BOTTLES.pitches) == 12
    assert best_transpose([72, 76, 79], BOTTLES.pitches) == 0
    assert coverage([], BOTTLES.pitches) == 1.0


def test_arrangement_is_playable_and_easy():
    result = arrange(melody(TWINKLE_G, beat_s=0.75), difficulty=1)
    assert result.coverage_before < 0.5
    assert result.coverage_after == 1.0
    assert result.transpose == 17  # G major down here becomes C major on the bottles
    assert check_robot(result.score, BOTTLES).ok
    assert check_pianist(result.score, PIANO) == []
    assert pianist_difficulty(result.score) == 1
    assert len(result.chords) == result.score.bar_count


@pytest.mark.parametrize("level", [1, 2, 4])
def test_pianist_part_follows_level(level):
    result = arrange(melody(TWINKLE_G, beat_s=0.75), difficulty=level)
    assert pianist_difficulty(result.score) <= max(level, 2)
    pianist = result.score.part_events("pianist")
    if level >= 4:
        assert any(
            sum(1 for o in pianist if (o.bar, o.beat) == (e.bar, e.beat)) == 3 for e in pianist
        )


def test_chords_follow_the_melody():
    # Bar 1 outlines C major, bar 2 outlines G major (in the bottles' octave).
    notes = [72, 76, 79, 76, 79, 83, 74, 79]
    result = arrange(melody(notes), difficulty=1)
    assert result.chords[:2] == ["C", "G"]


def test_retuning_suggestion():
    # A melody that keeps using F#5, which the bottles do not have.
    pitches = [72, 74, 76, 78, 79, 78, 76, 74, 72, 78]
    (tip,) = suggest_retuning(pitches, BOTTLES)[:1]
    assert (tip.bottle, tip.to) == ("F5", "F#5")
    assert tip.cents == 100 and tip.coverage_after == 1.0
    assert "pour water out of" in tip.advice()


def test_end_to_end_from_audio(tmp_path):
    from duet.audio.pipeline import transcribe
    from helpers import synth

    audio = synth([(p, i * 0.5, 0.45) for i, p in enumerate([60, 64, 67, 72, 67, 64, 60])])
    result = arrange(transcribe(audio, 22050))
    assert result.coverage_after == 1.0
    assert check_robot(result.score, BOTTLES).ok
