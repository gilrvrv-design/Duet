# Duet

Back end for **Duet**: you describe a song (or hand it an audio file), the system writes it as a duet,
a robot plays one part on eight tuned glass bottles, and you play the other on a piano by following a strip of lights.

- Functional spec: [docs/backend-functional-spec.md](docs/backend-functional-spec.md)
- Implementation plan and status: [docs/implementation-plan.md](docs/implementation-plan.md)

## Setup

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/) and FFmpeg (for MP3, M4A and video files).

```bash
make install
```

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
