"""A bot that plays an instrument over MIDI (``duet.instruments.MidiOut``): a digital
piano or a synth, sent notes by the board's MIDI out.

Nothing moves, so its rule is short: every note in the instrument's range, and no more
notes at once than its polyphony. Repair moves a note into range by octaves and drops
notes beyond the polyphony; planning turns each note into a note on and a note off.
"""

from __future__ import annotations

from duet.instruments import Instrument, MidiOut
from duet.pitch import midi_to_name
from duet.protocol import NoteAt
from duet.repair import Change, RepairResult
from duet.score import DuetScore, Event
from duet.timing import EPSILON, timed_events


def _mechanism(inst: Instrument) -> MidiOut:
    if not isinstance(inst.bot, MidiOut):
        raise TypeError(f"{inst.id} is not played over MIDI")
    return inst.bot


def problems(score: DuetScore, part: str, inst: Instrument) -> list[str]:
    mech = _mechanism(inst)
    low, high = inst.pitches[0], inst.pitches[-1]
    found = [
        f"bar {e.bar} beat {e.beat:g}: {midi_to_name(e.pitch)} is outside "
        f"{midi_to_name(low)}-{midi_to_name(high)}"
        for e in score.part_events(part)
        if e.pitch not in inst.pitches
    ]
    timed = timed_events(score, part)
    for t in timed:
        at_once = sum(1 for o in timed if o.start_s <= t.start_s + EPSILON < o.end_s)
        if at_once > mech.polyphony:
            found.append(
                f"bar {t.event.bar} beat {t.event.beat:g}: {at_once} notes at once "
                f"(polyphony {mech.polyphony})"
            )
            break
    return found


def repair(score: DuetScore, part: str, inst: Instrument) -> RepairResult:
    """Every note into range (nearest octave), then at most ``polyphony`` at once (the
    highest notes stay)."""
    mech = _mechanism(inst)
    low, high = inst.pitches[0], inst.pitches[-1]
    changes: list[Change] = []
    events: list[Event] = []
    for e in score.events:
        if e.part != part or low <= e.pitch <= high:
            events.append(e)
            continue
        pitch = e.pitch
        while pitch < low:
            pitch += 12
        while pitch > high:
            pitch -= 12
        if not low <= pitch <= high:  # a range narrower than an octave
            pitch = min(high, max(low, e.pitch))
        changes.append(
            Change("fold", e.bar, e.beat, f"{midi_to_name(e.pitch)} -> {midi_to_name(pitch)}")
        )
        events.append(e.revised({"pitch": pitch}))
    score = score.with_events(events)
    timed = sorted(timed_events(score, part), key=lambda t: (t.start_s, -t.event.pitch))
    dropped: set[int] = set()
    kept = []
    for t in timed:
        sounding = [k for k in kept if k.start_s <= t.start_s + EPSILON < k.end_s]
        if len(sounding) >= mech.polyphony:
            dropped.add(id(t.event))
            changes.append(
                Change(
                    "drop", t.event.bar, t.event.beat, f"{midi_to_name(t.event.pitch)} polyphony"
                )
            )
            continue
        kept.append(t)
    score = score.with_events([e for e in score.events if id(e) not in dropped])
    return RepairResult(score, changes)


def messages(score: DuetScore, part: str, inst: Instrument, us) -> list[NoteAt]:
    """A note on at each note's start and a note off at its end (``us``: seconds from bar
    1 to clock microseconds). Offs come before ons at the same moment, so a repeated
    note is re-struck."""
    mech = _mechanism(inst)
    out: list[tuple[int, int, NoteAt]] = []
    for t in timed_events(score, part):
        e = t.event
        out.append((us(t.start_s), 1, NoteAt(us(t.start_s), mech.midi_channel, e.pitch, e.vel)))
        out.append((us(t.end_s), 0, NoteAt(us(t.end_s), mech.midi_channel, e.pitch, 0)))
    return [m for _, _, m in sorted(out, key=lambda x: (x[0], x[1]))]
