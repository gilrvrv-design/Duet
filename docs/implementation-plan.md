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

| # | Delivery | Spec | Test that proves it |
|---|---|---|---|
| 0 | Project skeleton: package, `make check`, lint, CI | — | `pytest` runs; CI green |
| 1 | Pitch utilities | §4.1 | Note names round-trip; A4 = 440 Hz |
| 2 | DuetScore model with validation | §4.1, FR-S1, FR-S2 | Valid JSON loads; bad bars, beats, pitches rejected |
| 3 | Timing: bar/beat → seconds | FR-S6 | Known events land at known times |
| 4 | Instrument profile + kinematics + reachability matrix | §5.3 FR-R1, §7.2 | Travel time matches hand-worked trapezoid maths |
| 5 | Robot feasibility checker | FR-S3 | Each rule triggers on a crafted score and passes on a good one |
| 6 | Deterministic repair | FR-S4 | Infeasible score becomes feasible; every change logged |
| 7 | Pianist difficulty score | FR-S5 | Harder parts score higher; range violations reported |
| 8 | MIDI export and import | FR-S6, FR-S7 | DuetScore → MIDI → DuetScore round-trip |
| 9 | Robot plan and LED plan | FR-S6, §5.3, §5.4 | Move starts before strikes; LED indices match keys |
| 10 | Simulated rig + fixed-tempo conductor + CLI (**tracer bullet**) | §5.5, §5.10 | `duet play song.mid --sim` performs; event log matches plan |
| 11 | Composition service with a fake LLM and the validate–repair loop | §5.1 | Fake LLM's bad draft gets repaired; feedback loop runs |
| 12 | Claude provider for composition | §5.1 FR-C3 | Unit test with a stubbed client; live test skipped without a key |
| 13 | Audio → MIDI, melody route (pYIN) with `Transcriber` interface | §5.14 FR-A3 | A synthesized tune is transcribed to the right notes |
| 14 | Arranger: transcription → playable DuetScore | §5.14.3 | Transcribed melody fits the bottles and passes feasibility |
| 15 | REST API for compositions, transcriptions and MIDI download | §6 | API tests with the test client |
| 16 | Full-mix route adapters (Demucs, Basic Pitch) as optional extras | §5.14 | Adapter tests skipped unless the extras are installed |

Later deliveries (device firmware, WebSocket gateway, listening engine, pedagogy) follow the phases in the spec.
