import pytest

from duet.listening import Expected, Grade, Report
from duet.pedagogy import SkillModel, note_features, teach_song
from helpers import make_score


def report(score, results):
    from duet.timing import timed_events

    grades = [
        Grade(Expected(round(t.start_s * 1e6), t.event.pitch, t.event.bar), r)
        for t, r in zip(timed_events(score, "pianist"), results, strict=True)
    ]
    return Report(grades, [], part="pianist")


EASY = make_score(pianist=[(b, 1, 4, "C4") for b in range(1, 9)], tempo=60)
JUMPY = make_score(
    pianist=[
        (b, beat, 1, p)
        for b in range(1, 5)
        for beat, p in ((1, "C4"), (2, "G4"), (3, "F#4"), (4, "D4"))
    ],
    tempo=60,
)


def test_note_features():
    feats = note_features(JUMPY, "pianist")
    assert feats[0] == {"steps"}
    assert "jump7" in feats[1]  # C4 -> G4
    assert "black_keys" in feats[2]  # F#4
    assert "jump5" not in feats[2]  # G4 -> F#4 is one step
    chords = make_score(
        pianist=[(1, 1, 2, "C4"), (1, 1, 2, "E4"), (1, 1, 2, "G4"), (1, 2.5, 1, "D4")]
    )
    feats = note_features(chords, "pianist")
    assert all("big_chords" in f for f in feats[:3]) and "offbeats" in feats[3]


def test_mastery_grows_with_evidence_and_unlocks_levels():
    model = SkillModel()
    assert model.level == 1 and model.next_request()[0] == 2
    newly = model.update(EASY, report(EASY, ["hit"] * 8))
    assert newly == ["steps"]
    assert model.skills["steps"].mastery == (8 + 1) / (8 + 2)
    offbeat = make_score(
        pianist=[
            (b, beat, 1, p) for b in range(1, 5) for beat, p in ((1, "C4"), (1.5, "D4"), (3, "G4"))
        ],
        tempo=60,
    )
    assert model.update(offbeat, report(offbeat, ["hit"] * 12)) == []  # 4 tries: not yet sure
    assert model.level == 1
    model.update(offbeat, report(offbeat, ["hit"] * 12))  # 8 tries: now it counts
    assert model.level == 2  # offbeats and five-key jumps mastered
    level, focus = model.next_request()
    assert level == 3 and focus in {
        "black keys",
        "two notes at once",
        "quicker notes",
        "jumps of up to seven keys",
    }


def test_mistakes_point_at_the_weak_feature():
    model = SkillModel()
    results = ["hit", "hit", "missed", "hit"] * 4  # always misses the black key
    model.update(JUMPY, report(JUMPY, results))
    assert model.skills["black_keys"].mastery < 0.2
    assert model.skills["jump7"].known is False  # only 4 tries so far
    assert model.skills["steps"].mastery > 0.7


def test_composition_request_carries_the_focus():
    from duet.compose import CompositionRequest
    from duet.compose.prompts import request_message

    request = CompositionRequest(prompt="x", focus="black keys")
    text = request_message(
        "x",
        difficulty=3,
        bars=4,
        lead="bot",
        pianist_range=("C4", "C5"),
        tempo_bpm=None,
        time_signature=None,
        focus=request.focus,
    )
    assert "Practice focus: include a few black keys" in text


def test_teach_me_this_song():
    from duet.audio.notes import NoteEvent
    from duet.audio.pipeline import Transcription

    tune = [55, 55, 62, 62, 64, 64, 62, 60, 60, 59, 59, 57, 57, 55]
    t = Transcription(
        [NoteEvent(i * 0.6, i * 0.6 + 0.5, p) for i, p in enumerate(tune)],
        100,
        "G major",
        9,
        "test",
    )
    path = teach_song(t, target_level=2, title="Twinkle")
    assert [(s.difficulty, s.tempo_factor) for s in path.steps] == [
        (1, 0.7),
        (1, 1.0),
        (2, 0.7),
        (2, 1.0),
    ]
    assert path.steps[0].score.meta.tempo_bpm == 70 and path.steps[1].score.meta.tempo_bpm == 100
    assert path.current == 0
    notes = len(path.steps[0].score.part_events("pianist"))
    assert not path.record(0, report(path.steps[0].score, ["missed"] * notes))
    assert path.record(0, report(path.steps[0].score, ["hit"] * notes)) and path.current == 1


def test_cli_teach(tmp_path, capsys):
    import soundfile

    from duet.cli import main
    from helpers import synth

    wav = tmp_path / "song.wav"
    tune = [(p, i * 0.5, 0.45) for i, p in enumerate([60, 64, 67, 72, 67])]
    soundfile.write(wav, synth(tune), 22050)
    assert main(["teach", str(wav), "--target", "2", "--out", str(tmp_path / "lesson")]) == 0
    files = sorted(p.name for p in (tmp_path / "lesson").iterdir())
    assert files == [
        "01-level1-70pct.json",
        "02-level1-100pct.json",
        "03-level2-70pct.json",
        "04-level2-100pct.json",
    ]


def test_a_skill_comes_from_a_graded_part():
    with pytest.raises(ValueError, match="grading a part"):
        SkillModel().update(EASY, Report([], []))
