# Duet

Back end for **Duet**: you describe a song (or hand it an audio file), the system writes it as a duet,
a robot plays one part on eight tuned glass bottles, and you play the other on a piano by following a strip of lights.

## Documentation

| Read this | When you want to |
|---|---|
| [Architecture](docs/architecture.md) | understand how the code fits together, with diagrams |
| [Device protocol](docs/device-protocol.md) | know exactly what the Hub and the rig say to each other |
| [Rig guide](docs/rig-guide.md) | wire, flash, test, calibrate and troubleshoot the rig |
| [Functional spec](docs/backend-functional-spec.md) | see what the system is meant to become |
| [Implementation plan](docs/implementation-plan.md) | see what has been built, in which order, and what is next |
| [Firmware README](firmware/README.md) | build the firmware and its native tests |

## Setup

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/) and FFmpeg (for MP3, M4A and video files).

```bash
make install
```

This installs exactly the versions pinned in `uv.lock`. After changing dependencies in
`pyproject.toml`, run `uv lock` and commit the new lockfile.

```bash
source .venv/bin/activate
```

```bash
make check
```

## Command line

Check whether the robot can play a score, and see the pianist's level:

```bash
duet check examples/rain-on-the-bottles.json
```

Perform it on the simulated rig:

```bash
duet play examples/rain-on-the-bottles.json --sim
```

Practise in wait mode: the robot pauses at each of your notes until you play it, then grades you.
Use `--midi-in "<port name>"` with a MIDI keyboard; without it a simulated pianist plays:

```bash
duet play examples/rain-on-the-bottles.json --sim --wait
```

Or in follow mode, where the robot keeps your tempo (here a simulated pianist plays 10% slower than written):

```bash
duet play examples/rain-on-the-bottles.json --sim --follow --stretch 1.1
```

With an acoustic piano, add `--mic` (needs `pip install sounddevice`); the listener ignores the bottles:

```bash
duet play examples/rain-on-the-bottles.json --sim --wait --mic
```

Play one part alone: `--only robot` for the bottles solo, `--only piano` to practise
your part with the light guide (and grading, in wait or follow mode):

```bash
duet play examples/rain-on-the-bottles.json --sim --only piano --wait
```

Play without a PC: store a song on the rig once, then press its play button. The Hub
compiles the song at upload time; the ESP32 homes and plays it on its own:

```bash
duet upload examples/rain-on-the-bottles.json --device ws://duet-rig-1.local:8765 --slot 0
```

Make a variation: `slower`, `faster`, `easier` and `swap` are instant; anything else ("in a minor key") asks Claude to edit the duet:

```bash
duet vary examples/rain-on-the-bottles.json easier rain-easier.json
```

Play a multi-track MIDI file as an ensemble: each line goes to the instrument that fits it best
(bottles, a robot glockenspiel and the pianist here):

```bash
duet ensemble trio.mid --robots bottles-v1,glock-v1 --pianist C2-C5 --sim
```

Teach me this song: lesson steps from a recording, from the easiest part slowly up to your target level:

```bash
duet teach my-song.m4a --target 3 --out lesson
```

Jam in call and response: you play a two-bar phrase, the robot answers with a variation of it
(`--midi-in` or `--mic` for a real piano; without them a simulated pianist plays):

```bash
duet jam --turns 4 --tempo 90
```

Grade a MIDI recording of the pianist part:

```bash
duet grade examples/rain-on-the-bottles.json my-take.mid
```

Make an unplayable score playable, or convert between DuetScore JSON and MIDI:

```bash
duet repair song.mid song-fixed.json
```

```bash
duet convert examples/rain-on-the-bottles.json rain.mid
```

Turn a recording (humming, a single instrument, or a song) into MIDI and a playable duet:

```bash
duet transcribe hum.m4a hum.mid --duet hum-duet.json --difficulty 1
```

Calibrate the rig: play the sweep on the rig while recording it with a microphone, then measure the recording.
Every other command accepts the result with `--robot calibrated.yaml`:

```bash
duet sweep sweep.json
```

```bash
duet calibrate sweep-recording.wav --out calibrated.yaml
```

Compose a duet from a text request with Claude (needs Anthropic credentials; set `DUET_MODEL` to change the model):

```bash
duet compose "a gentle lullaby in 3/4" lullaby.mid --difficulty 1 --bars 8
```

Measure composition quality (calls Claude for every case, so it costs money; `--limit` runs fewer).
Save a run as the baseline, then gate prompt or model changes against it:

```bash
duet eval --out evals/baseline.json
```

```bash
duet eval --baseline evals/baseline.json
```

## API

```bash
make serve
```

Set `DUET_DB=duet.db` to keep data in SQLite (default: in memory). Then open http://127.0.0.1:8000/docs. Main endpoints: `/v1/duets`, `/v1/duets/import`, `/v1/compositions`,
`/v1/transcriptions` and `/v1/transcriptions/{id}/arrangements`.

## Optional full-mix transcription

Separating full songs into instruments uses Demucs and Basic Pitch, which bring large ML frameworks:

```bash
uv pip install demucs basic-pitch
```

Without them, songs are transcribed with the melody route and a warning.
