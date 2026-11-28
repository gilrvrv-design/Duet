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

The Hub is Python 3.12+ (the audio and ML libraries in the spec are Python): one package,
`duet`, under `src/`, with its tests in `tests/`. The firmware is C++17 under `firmware/`:
a core library shared by every board, the native device and the tests, and a thin layer
per board. The [architecture](architecture.md#module-map) has the module map; it is the
one place that lists the modules.

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

| # | Delivery | Spec | Test that proves it | Status |
|---|---|---|---|---|
| 17 | Persistent store (SQLite/Postgres) behind the `MemoryStore` interface | §4.2 | API tests run against both stores | Done (SQLite) |
| 18 | Async jobs for composition and transcription, with progress streams | §6.2, FR-A5 | Job states and stream events in order | Done |
| 19 | WebSocket device gateway and clock sync with the simulated rig over a real socket | §5.10 | Sync error under 2 ms on localhost | Done |
| 19b | Periodic clock resync during long sessions (every 2 s) and drift estimate | FR-D2 | Simulated drifting clock stays within 2 ms over 10 minutes | Done (tested at 2000 ppm) |
| 20 | ESP32 firmware executor for `move_at` / `strike_at` / `led_frame_at` | §5.10 | Hardware-in-the-loop timing test | Done: every board builds in CI, and the firmware runs the full loop in QEMU and as a native process; not yet run on hardware |
| 20b | Conductor waits for "homed" telemetry before the count-in; device reports position and homing state | FR-R5, FR-D3 | Slow homing on the simulated device delays the start instead of faulting | Done |
| 21 | Calibration: bottle positions, measured pitch, strike latency | §5.11 | Recorded strikes update the profile | Done (tested on synthesized recordings) |
| 22 | Listening engine: MIDI input, hit grading, wait mode | §5.6 | Recorded performance graded correctly | Done (MIDI path; real keyboard not tested here) |
| 22b | Follow mode: score following and tempo coupling | FR-H3, FR-H5 | Robot follows a pianist who speeds up and slows down | Done (sequential follower; online DTW later if needed) |
| 22c | Microphone input with robot self-filtering | FR-H1, FR-H2 | Acoustic piano notes graded while bottles ring | Done (synthesized piano and glass; no real microphone tested) |
| 23 | Composition evaluation set and gate | §9.3 | Pass rate reported per prompt-pack change | Done (30 cases; not yet run against the live API) |
| 24 | Call and response: capture the pianist's phrase, answer on the bottles within one beat, recall earlier motifs | FR-H6, FR-G1, FR-G3 | Answers start within a beat and stay playable | Done (answers 62 ms after the turn) |
| 25 | Skill model, difficulty-targeted composition, lesson paths, "teach me this song" | FR-E1–E3, FR-A26 | A pianist's estimate moves with their results; paths step up | Done |
| 26 | Variations as edits and a library with versions, forks and search | FR-C8, FR-B1–B5 | "Easier" lowers difficulty; versions and forks are kept | Done (search is keyword-based; embeddings later) |
| 27 | Copyright guard: public-domain list and melody similarity | FR-C5 | A copied melody is flagged; public-domain tunes pass | Done (protected list supplied by the operator) |
| 28 | Ensembles: a second robot (glockenspiel), part assignment from multi-track MIDI, one conductor for several rigs | Phase 4 | Each line goes to the instrument that fits it; all rigs play from one clock | Done (simulated rigs) |

## After the back end

The rig became the main interface: its own web page, songs stored on the board, servers
optional. That work, steps 0 to 6, is planned and tracked in the
[ESP-first design](design/esp-first.md#plan).
