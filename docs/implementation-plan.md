# Duet back end — implementation plan

This plan turns the [functional spec](backend-functional-spec.md) into small deliveries.
Each delivery is one commit (or a few), ships with tests, and leaves `make check` green.

## Principles (from *The Pragmatic Programmer*)

- **Tracer bullets.** Get a thin path working end to end early (prompt or MIDI → score → robot and LED plans → simulated performance), then thicken it.
- **Small steps, test as you go.** No delivery lands without tests. `make check` runs lint and tests; CI runs the same command.
- **DRY.** One source of truth for each piece of knowledge: pitch maths in `duet.pitch`, timing in `duet.timing`, motion physics in `duet.kinematics`. Everything else calls them.
- **Orthogonality.** The score model knows nothing about MIDI, LLMs or hardware. Adapters (MIDI, LLM, transcription, device) sit at the edges behind small interfaces.
- **Design by contract.** Models validate their inputs (pydantic). Functions fail loudly with clear errors instead of guessing.
- **Don't live with broken windows.** Lint stays clean; no skipped tests.
- **Configuration over code.** Instrument facts (bottle pitches, speeds) live in YAML profiles, not in code.
- **Easy to change.** The LLM and the transcription models are behind interfaces with fake implementations for tests, so tests never need the network or a GPU.

## Language and layout

Python 3.12+ (the audio and ML libraries in the spec are Python). One package, `duet`, under `src/`.

```
src/duet/
  pitch.py          note names <-> MIDI numbers <-> Hz
  score.py          DuetScore model (spec §4.1)
  timing.py         bar/beat -> seconds
  profile.py        instrument profiles (spec §7.2)
  kinematics.py     carriage motion, reachability matrix (spec §5.3)
  feasibility.py    robot checks -> violations (spec §5.2 FR-S3)
  repair.py         deterministic repair (FR-S4)
  difficulty.py     pianist difficulty score (FR-S5)
  midi_io.py        DuetScore <-> MIDI (FR-S6, FR-S7)
  plans.py          robot plan + LED plan (FR-S6)
  conductor.py      fixed-tempo conductor + simulated devices (spec §5.5)
  compose/          LLM composition with validate-repair loop (spec §5.1)
  audio/            audio -> MIDI transcription and arranger (spec §5.14)
  api/              REST API (spec §6)
  cli.py            command line entry point
  profiles/         instrument profile YAML files (shipped with the package)
tests/
```

## Deliveries

| # | Delivery | Spec | Test that proves it | Status |
|---|---|---|---|---|
| 0 | Project skeleton: package, `make check`, lint, CI | — | `pytest` runs; CI green | Done |
| 1 | Pitch utilities | §4.1 | Note names round-trip; A4 = 440 Hz | Done |
| 2 | DuetScore model with validation | §4.1, FR-S1, FR-S2 | Valid JSON loads; bad bars, beats, pitches rejected | Done |
| 3 | Timing: bar/beat → seconds | FR-S6 | Known events land at known times | Done |
| 4 | Instrument profile + kinematics + reachability matrix | §5.3 FR-R1, §7.2 | Travel time matches hand-worked trapezoid maths | Done |
| 5 | Robot feasibility checker | FR-S3 | Each rule triggers on a crafted score and passes on a good one | Done |
| 6 | Deterministic repair | FR-S4 | Infeasible score becomes feasible; every change logged | Done |
| 7 | Pianist difficulty score | FR-S5 | Harder parts score higher; range violations reported | Done |
| 8 | MIDI export and import | FR-S6, FR-S7 | DuetScore → MIDI → DuetScore round-trip | Done |
| 9 | Robot plan and LED plan | FR-S6, §5.3, §5.4 | Move starts before strikes; LED indices match keys | Done |
| 10 | Simulated rig + fixed-tempo conductor + CLI (**tracer bullet**) | §5.5, §5.10 | `duet play song.mid --sim` performs; event log matches plan | Done |
| 11 | Composition service with a fake LLM and the validate–repair loop | §5.1 | Fake LLM's bad draft gets repaired; feedback loop runs | Done |
| 12 | Claude provider for composition | §5.1 FR-C3 | Unit test with a stubbed client; live test skipped without a key | Done |
| 13 | Audio → MIDI, melody route (pYIN) with `Transcriber` interface | §5.14 FR-A3 | A synthesized tune is transcribed to the right notes | Done |
| 14 | Arranger: transcription → playable DuetScore | §5.14.3 | Transcribed melody fits the bottles and passes feasibility | Done |
| 15 | REST API for compositions, transcriptions and MIDI download | §6 | API tests with the test client | Done |
| 16 | Full-mix route adapters (Demucs, Basic Pitch) as optional extras | §5.14 | Adapter tests skipped unless the extras are installed | Done |

## Next deliveries

| # | Delivery | Spec | Test that proves it |
|---|---|---|---|
| 17 | Persistent store (SQLite/Postgres) behind the `MemoryStore` interface | §4.2 | API tests run against both stores | Done (SQLite) |
| 18 | Async jobs for composition and transcription, with progress streams | §6.2, FR-A5 | Job states and stream events in order |
| 19 | WebSocket device gateway and clock sync with the simulated rig over a real socket | §5.10 | Sync error under 2 ms on localhost |
| 20 | ESP32 firmware executor for `move_at` / `strike_at` / `led_frame_at` | §5.10 | Hardware-in-the-loop timing test |
| 21 | Calibration: bottle positions, measured pitch, strike latency | §5.11 | Recorded strikes update the profile |
| 22 | Listening engine: MIDI input, hit grading, wait mode | §5.6 | Recorded performance graded correctly |
| 23 | Composition evaluation set and gate | §9.3 | Pass rate reported per prompt-pack change |
