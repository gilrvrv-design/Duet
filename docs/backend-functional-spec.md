# Duet — Back-End Functional Specification

**Status:** Draft v1.0 · 2026-11-27
**Scope:** Every non-UI software component behind Duet: composition, score processing, real-time performance orchestration, device control (robot and LED guide), listening, data, and platform services.
**Source:** xylophonebot.com ("Duet — human and robot duet · in progress") plus the assumptions in §2.

---

## 0. Vision

> *Recorded music is cheap now. Live playing still counts.*

Today Duet works like this: someone types a request, an LLM writes a two-part MIDI file, a robot plays one part on eight glass bottles, and a beginner plays the other part on a piano by following lights.

The bold version is a **musical partner, not a playback device**. The back end should grow into a system that:

1. **Composes for the instruments it actually has.** It knows how far the carriage must travel, how long a bottle rings, and how good this pianist is. It never writes a note that can't be played.
2. **Listens.** It follows the human, waits when they hesitate, speeds up when they're confident, and answers a phrase with a phrase.
3. **Teaches without sheet music.** Each session makes the pianist a little better. The system knows what they've learned and writes the next piece to stretch them.
4. **Scales from one bench to an ensemble.** Any robotic instrument (bottles today; marimba, drums or a second robot later) plugs in through an instrument profile. Duets become trios, and people in two different cities can play together.

All of this rests on one idea: a **constraint-aware score model** (the *DuetScore*). It sits between the LLM and the hardware. The LLM writes a DuetScore. The back end checks it against physics and pedagogy, repairs what fails, and compiles it to MIDI. A conductor then performs it live against the human.

---

## 1. Current State (from the site)

| Component | Site status | Notes |
|---|---|---|
| Robot mechanics | Done | 8 tuned bottles, NEMA 17 + timing belt carriage, push-pull solenoid striker (JF-1039B), inductive homing sensor (LJ12A3), ESP32 |
| Robot control | In progress | Stepper motion and solenoid firing |
| LED guide | In progress | 144 LED/m addressable RGB strip, ~1.22 m, ~2 LEDs per semitone, on the same ESP32 |
| MIDI parser | In progress | One parser splits the two-part file between the two players |
| LLM connection | Next | Typed request → two-part MIDI |
| Key-press sensing | Optional / undecided | (§2 decides: yes, from Phase 2) |
| Web simulation | Exists | Pre-written examples; keys A–K play C4–C5 |

Pipeline on the site: **ask → compose → parse → perform.**

---

## 2. Assumptions

The user approved working on assumptions, so these are decided rather than left open. Each one can be changed later through configuration.

| # | Assumption |
|---|---|
| A1 | The bottles form one diatonic octave (C major, 8 notes) by default. The real pitch of each bottle is measured during calibration and stored in the instrument profile (§7.2). |
| A2 | The robot is monophonic: one striker, so one note at a time. |
| A3 | A **Duet Hub** runs the real-time back end. It is a host on the same LAN as the ESP32 (laptop or Raspberry Pi 5 class). Cloud services do composition, storage and accounts. Real-time timing never depends on the internet. |
| A4 | ESP32 ↔ Hub uses WebSocket over Wi-Fi as the primary link, with USB serial as a fallback and for bench work. The ESP32 is a timed executor, not a decision maker. |
| A5 | The piano is any acoustic or digital piano. Digital pianos give MIDI over USB or BLE. Acoustic pianos are heard through a microphone with pitch detection. |
| A6 | The LLM is a hosted frontier model (the Claude family). A fast model handles interactive composition and a stronger model handles hard or long pieces. The model is configurable. |
| A7 | Target users are beginners, families, classrooms, makers and live audiences (exhibitions and demos). |
| A8 | The first deployment is one rig. Multi-rig and multi-user features come later (Phase 4). |

---

## 3. System Architecture

```
                        ┌──────────────────────── CLOUD ────────────────────────┐
   Web / Mobile UI ───► │ API Gateway ─► Session Svc ─► Composition Svc ─► LLM  │
                        │      │              │              │                  │
                        │  Identity Svc   Library Svc   Score Compiler          │
                        │      │              │         (validate/repair/MIDI)  │
                        │  Progress &     Object Store    Telemetry/Analytics   │
                        │  Pedagogy Svc   (MIDI, audio)                         │
                        └──────────────▲───────────────────────────────────────┘
                                       │ HTTPS + WSS (sync, not real-time)
                        ┌──────────────┴──────── DUET HUB (LAN) ────────────────┐
                        │ Hub Agent ─► Performance Conductor ◄─ Listening Engine│
                        │                 │        │               ▲            │
                        │        Robot Scheduler  LED Cue Planner   │            │
                        │                 │        │          Piano MIDI / Mic   │
                        │            Device Gateway (WS / Serial)               │
                        └─────────────────┬─────────────────────────────────────┘
                                          │ timestamped commands, telemetry
                        ┌─────────────────┴──────── ESP32 ──────────────────────┐
                        │ Motion executor · Solenoid driver · Homing · LED driver│
                        └───────────────────────────────────────────────────────┘
```

### 3.1 Services

| Service | Where | Responsibility |
|---|---|---|
| API Gateway | Cloud | Auth, rate limiting, REST + WebSocket entry point |
| Identity Service | Cloud | Users, households/classrooms, rigs, roles |
| Session Service | Cloud | Duet sessions from request to performance to review |
| Composition Service | Cloud | Prompting, LLM calls, the repair loop, explanations |
| Score Compiler | Cloud + Hub (shared library) | DuetScore validation, feasibility, repair hints, MIDI import/export |
| Library Service | Cloud | Saved, shared and curated duets; search; versions |
| Progress & Pedagogy Service | Cloud | Skill model, difficulty targeting, lesson paths |
| Telemetry & Analytics | Cloud | Device health, performance metrics, product analytics |
| Hub Agent | Hub | Pairing, sync, offline cache, updates |
| Performance Conductor | Hub | Master clock, run-time state machine, tempo control |
| Robot Scheduler | Hub | Motion planning, strike timing, latency compensation |
| LED Cue Planner | Hub | Key→LED mapping, look-ahead cues, feedback colors |
| Listening Engine | Hub | Piano input (MIDI/mic), score following, onset detection |
| Device Gateway | Hub | Protocol to the ESP32, clock sync, retries, telemetry |
| Firmware | ESP32 | Executes timed commands; safety interlocks |

The **Score Compiler is one shared library** (for example in Rust or TypeScript, compiled to native and WASM). The cloud, the Hub and the web simulation all run the same validation and timing math. This is the "one parser for both" rule from the site, extended to the whole system.

---

## 4. Core Data Model

### 4.1 DuetScore (canonical score format)

The LLM never writes raw MIDI bytes. It writes **DuetScore JSON** under a strict schema (structured output / tool call). MIDI is a compiled artifact.

```jsonc
{
  "schema": "duetscore/1",
  "meta": {
    "title": "Rain on the Bottles",
    "prompt": "a gentle lullaby, easy piano part",
    "key": "C major", "time_signature": [3, 4], "tempo_bpm": 84,
    "style_tags": ["lullaby", "waltz"], "difficulty_target": 2
  },
  "parts": {
    "robot":  { "instrument_profile": "bottles-v1", "role": "melody" },
    "pianist":{ "instrument_profile": "piano-88",   "role": "accompaniment",
                "hand": "right", "range": ["C4", "C5"] }
  },
  "events": [
    { "part": "robot",   "bar": 1, "beat": 1.0, "dur": 1.0, "pitch": "E5", "vel": 90 },
    { "part": "pianist", "bar": 1, "beat": 1.0, "dur": 2.0, "pitch": "C4", "vel": 70,
      "finger": 1, "hint": "hold" }
  ],
  "sections": [ { "name": "A", "bars": [1, 8], "repeat": 1 } ],
  "turns":    [ { "bars": [1, 2], "lead": "robot" }, { "bars": [3, 4], "lead": "pianist" } ],
  "annotations": [ { "bar": 5, "text": "Your turn to lead!" } ]
}
```

Rules:
- Pitches use scientific notation and are resolved against the instrument profile.
- `turns` makes call-and-response explicit. The LED guide and the conductor both use it.
- Optional pedagogy fields (`finger`, `hint`) support beginner guidance.
- The compiler adds derived data: absolute tick times, carriage positions, LED indices and per-event feasibility scores.

### 4.2 Main entities

| Entity | Key fields |
|---|---|
| `User` | id, display name, role (player / teacher / admin), locale, consent flags (minors) |
| `Rig` | id, owner, hub_id, devices[], instrument profiles, calibration version, status |
| `Device` | id, type (robot / led / piano-input), firmware version, last seen, health |
| `InstrumentProfile` | id, kind, notes[] (pitch → physical position), kinematics, timing, limits |
| `Calibration` | rig_id, version, bottle positions (steps), measured pitches (Hz, cents), LED offsets per key, latencies |
| `Duet` | id, DuetScore, compiled MIDI URI, provenance (prompt, model, repair log), version, visibility |
| `Session` | id, rig, players, duet version, state, timestamps |
| `Performance` | session id, event log (planned vs actual), pianist accuracy, recording URI |
| `SkillModel` | user id, per-skill estimates (range, rhythm, tempo, intervals, hands), history |
| `Lesson` / `Path` | ordered goals, generated or curated duets, completion rules |

---

## 5. Functional Requirements by Component

### 5.1 Composition Service

**FR-C1 Request intake.** Accept free text plus optional structured hints: style, mood, length (bars or seconds), tempo, piano difficulty (1–5), who leads, and a seed song name. Detect the language and keep the original prompt.

**FR-C2 Context assembly.** Each LLM call gets:
- the DuetScore schema and examples;
- the **instrument capabilities sheet** for the target rig: the actual bottle pitches, monophony, the reachability table (minimum time between two bottles, §5.3), and decay time;
- the pianist profile: allowed range, hands, target difficulty, recently mastered skills (from §5.8);
- style guides and safety rules.

**FR-C3 Generation.** Call the LLM with a structured-output schema. Defaults: fast model for under 32 bars; stronger model for long pieces, complex styles, or a second repair pass. Stream partial results so the UI can show "composing" progress.

**FR-C4 Validate–repair loop.** Run the Score Compiler (§5.2). If it reports violations, send them back to the LLM as a structured list ("bar 6 beat 2: robot needs 0.41 s to reach G5 but has 0.25 s") and ask for a fix of only the affected bars. At most 3 rounds. If violations remain, apply deterministic repair (§5.2 FR-S4). Record the whole repair log in provenance.

**FR-C5 Copyright guard.** For named copyrighted songs, write an original piece "in the style of" rather than reproducing the melody, unless the work is in the public domain (for example traditional tunes or classical works). Keep a public-domain melody list and a similarity check against it.

**FR-C6 Content safety.** Moderate titles, annotations and lyrics-like text. Settings for minors are stricter.

**FR-C7 Explanations.** Optionally write a short plain-language note ("The robot sings the melody; you play the bass notes on every first beat").

**FR-C8 Variations.** Support "easier", "harder", "slower", "make the robot lead", "add a section" and "same song in a minor key" as edits to an existing DuetScore. Each edit makes a new version and sends a diff to the model rather than regenerating everything.

**FR-C9 Determinism and caching.** Cache by (normalized prompt, profile hash, difficulty, model). A "Surprise me" flag skips the cache.

### 5.2 Score Compiler (validate / repair / compile)

**FR-S1 Schema validation** with exact error paths.

**FR-S2 Musical validation:** time signatures make sense, bars are complete, no zero-length notes, sections and turns are consistent.

**FR-S3 Physical feasibility (robot):**
- Every robot pitch must map to a bottle (±50 cents tolerance after calibration; otherwise transpose or substitute).
- No overlapping robot notes (monophonic).
- For consecutive robot notes *i → j*: `onset_j − onset_i ≥ travel_time(pos_i, pos_j) + strike_cycle + safety_margin`, using the trapezoidal motion model in §5.3.
- A repeated note on the same bottle needs at least `solenoid_recovery` time between strikes (default 60 ms, calibrated).

**FR-S4 Deterministic repair, in order:** (1) octave-fold an unplayable pitch to the nearest available bottle; (2) move a note that is slightly too fast to the nearest feasible sub-beat; (3) merge or drop ornamental notes (lowest priority first); (4) as a last resort, lower the tempo globally. Every change is logged and can be shown to the user.

**FR-S5 Pedagogical feasibility (pianist):** range limits, maximum interval jump, maximum notes per second, polyphony per hand, and rhythm vocabulary allowed at this difficulty (for example, no syncopation at level 1). Score difficulty 1–5 with a transparent formula (note density, interval entropy, rhythm complexity, hand independence).

**FR-S6 Compile to:**
- **MIDI Type 1**: track 1 robot (channel 1), track 2 pianist (channel 2), tempo map, markers for sections and turns. Downloadable and backwards compatible with the site's parser.
- **Robot plan**: a list of `{t_strike, bottle, vel, move_start, target_steps}`.
- **LED plan**: a list of `{t_on, t_off, led_range, color, cue_type}`.
- **Simulation bundle**: for the web simulation, with audio samples and the plan.

**FR-S7 MIDI import.** Accept user MIDI files. Classify tracks automatically (melody vs. accompaniment), suggest the split between robot and piano, then run the same validation and repair.

### 5.3 Robot Scheduler (Hub)

**FR-R1 Kinematic model.** Configurable parameters, measured during calibration:

| Parameter | Default (assumed) |
|---|---|
| Steps per mm | 80 (GT2 belt, 20T pulley, 1/16 microstepping) |
| Bottle positions | measured, in steps from home |
| v_max | 500 mm/s |
| a_max | 5 000 mm/s² |
| Strike pulse width | 15–30 ms, mapped from velocity |
| Strike-to-sound latency | measured (default 12 ms) |
| Solenoid recovery | 60 ms |
| Settle time after move | 15 ms |

With these defaults, adjacent bottles (~80 mm apart) need about 0.26 s and the full span (~560 mm) about 1.2 s. The compiler publishes this as a **reachability matrix** (8×8 minimum intervals). The matrix goes into the LLM prompt.

**FR-R2 Motion planning.** For each strike, move just in time: depart as late as the trapezoidal profile allows, so the carriage waits at the previous bottle while it rings. Also support a "lookahead parking" mode for dense passages, where the carriage moves to a midpoint during long rests.

**FR-R3 Timing.** Strikes are sent as absolute timestamps on the shared clock (§5.10), pre-compensated by `strike_to_sound_latency`, at least 300 ms ahead. Target: perceived onset within **±10 ms** of the plan (p95).

**FR-R4 Dynamics.** Map velocity 1–127 to pulse width using a per-bottle curve, so every bottle sounds equally loud at the same velocity.

**FR-R5 Homing and recovery.** Home on power-up, at session start, and after any fault. If position confidence drops (missed steps detected through stall-guard or because home does not match the expected count), stop, re-home and resume at the next bar line.

**FR-R6 Safety.** Soft travel limits; solenoid duty-cycle limit (no more than about 20% over any 10 s window) with thermal estimation; an emergency stop from the UI or a physical button cuts motion and solenoid power.

### 5.4 LED Cue Planner (Hub)

**FR-L1 Key mapping.** Map each MIDI pitch to a range of LEDs (about 2 LEDs per semitone at 144/m, ~23.5 mm octave width per 7 white keys). Calibrate per piano: the user taps the lowest and highest keys, and a fine-offset wizard lines up the light with each key.

**FR-L2 Cue language (colors configurable and color-blind safe):**

| Cue | Default |
|---|---|
| Next key (pre-cue) | dim white, `lead_time` before the onset (default 1 beat, adaptive) |
| Play now | bright, at the onset |
| Hold | stays lit for the duration, fading toward the end |
| Correct hit (Phase 2+) | short green flash |
| Wrong key (Phase 2+) | amber on the pressed key, the correct key pulses |
| Robot's turn | slow "breathing" ambient pattern over the robot's note range |
| Left / right hand | two hues |

**FR-L3 Look-ahead depth.** Show 1–3 upcoming notes at decreasing brightness, depending on difficulty level.

**FR-L4 Count-in.** Run a full-strip count-in animation in time with the tempo before the first note.

**FR-L5 Power budget.** Limit brightness and the number of lit LEDs to the 5 V supply rating (current estimate per frame).

### 5.5 Performance Conductor (Hub)

**FR-P1 State machine:**
`IDLE → PREPARING (home, sync, load plans) → COUNT_IN → PLAYING ⇄ WAITING/PAUSED → ENDING → REVIEW`, plus `FAULT` from any state.

**FR-P2 Playback modes:**

| Mode | Behavior | Phase |
|---|---|---|
| **Fixed tempo** | The robot keeps time; the lights lead the pianist | 1 |
| **Practice loop** | Loop selected bars, optionally slower | 1 |
| **Wait mode** | The system pauses at each pianist note until the right key is played | 2 |
| **Follow mode** | Tempo follows the pianist (score following, §5.6) within limits | 2 |
| **Call & response** | Turns are open; the robot answers what the pianist actually played | 3 |
| **Jam** | Real-time co-improvisation within a key and groove | 3 |

**FR-P3 Transport control:** play, pause, resume, stop, seek to a bar, change tempo (±50%), loop A–B, and mute either part (robot-only demo, piano-only practice).

**FR-P4 Event log.** Record every planned event alongside its actual outcome (sent, acknowledged, sounded, pianist hit time and pitch) for review and analytics.

**FR-P5 Degraded operation.** If the LED device fails, continue with robot-only plus on-screen keys. If the robot faults, the Hub plays its part as audio through a speaker so the session continues ("the show goes on").

### 5.6 Listening Engine (Hub) — Phase 2+

**FR-H1 Inputs:** USB/BLE MIDI from digital pianos (preferred; latency under 5 ms), or a microphone with polyphonic pitch and onset detection (target: under 40 ms, ≥95% note accuracy for one-hand beginner material).

**FR-H2 Robot self-filtering.** With a microphone, cancel or ignore the bottles: the scheduler knows exactly when and which bottle sounds, and the profile stores each bottle's spectrum.

**FR-H3 Score following.** Online alignment (for example online DTW or an HMM) of pianist input against the expected part. It reports position, local tempo and confidence 20 times per second.

**FR-H4 Hit grading.** Each expected note is graded `hit / early / late / wrong pitch / missed / extra`, with millisecond offset.

**FR-H5 Tempo coupling.** In follow mode, the conductor smooths tempo (limited rate of change). The robot's next strikes are re-planned, within kinematic limits, when the tempo shifts.

**FR-H6 Phrase capture.** In call-and-response, capture the pianist's phrase and send it to the Response Generator (§5.7).

### 5.7 Response Generator (Hub + Cloud) — Phase 3

**FR-G1 Fast local reply.** An on-Hub model (rule-based plus a small symbolic model) answers a captured phrase within one beat: echo, transpose, invert, or rhythmic variation, constrained to the bottles.

**FR-G2 LLM-enhanced reply.** When the turn structure allows at least 2 bars of look-ahead, ask the cloud LLM for a richer answer; use it if it arrives in time, otherwise fall back to FR-G1.

**FR-G3 Style memory.** Keep motifs from the session so the robot can develop the pianist's ideas over the piece.

### 5.8 Progress & Pedagogy Service — Phase 2+

**FR-E1 Skill model.** Bayesian estimates per skill (note range, rhythmic accuracy, tempo, interval jumps, hand independence, reading look-ahead), updated from graded performances.

**FR-E2 Targeted composition.** Supply the Composition Service with "target zone" constraints: about 85% familiar material and 15% new challenge.

**FR-E3 Paths.** Curated and generated lesson paths ("First five notes", "Waltz time", "Both hands"). Each step is a duet with completion rules (for example ≥90% hits at ≥80% tempo).

**FR-E4 Feedback.** After the performance: a summary, the hardest bars, a "try this bar slower" suggestion, a streak, and a recording.

**FR-E5 Teacher / classroom.** A teacher assigns paths, sees student progress, and runs a rig in "kiosk" mode for many players.

### 5.9 Library Service

**FR-B1** Save, rename, version, fork and delete duets.
**FR-B2** Visibility: private, link-shared, or public (public requires moderation).
**FR-B3** Search by style, difficulty, length, rig profile, and mood (embeddings over prompt and metadata).
**FR-B4** Curated "Featured" collections, including the site's pre-written simulation examples.
**FR-B5** Compatibility check: re-run validation when a duet is opened on a rig with a different profile, and offer an automatic re-fit.

### 5.10 Device Gateway & Protocol

**FR-D1 Transport.** WebSocket (JSON for control; compact CBOR for timed events) over Wi-Fi; the same message set over USB serial (framed with COBS). Discovery by mDNS (`_duet._tcp`).

**FR-D2 Clock sync.** NTP-style ping exchange every 2 s; the ESP32 keeps an offset and drift estimate. Target sync error under 2 ms. All timed commands use Hub-clock microseconds.

**FR-D3 Message set (minimum):**

| Direction | Message | Payload |
|---|---|---|
| Hub→Dev | `hello` / `config` | protocol version, profile, limits |
| Hub→Dev | `home` | — |
| Hub→Dev | `move_at` | t_us, target_steps, v_max, a_max |
| Hub→Dev | `strike_at` | t_us, pulse_us |
| Hub→Dev | `led_frame_at` | t_us, ranges[] {start, len, rgb} or pattern id |
| Hub→Dev | `estop` / `clear` | — |
| Dev→Hub | `ack` | seq, status |
| Dev→Hub | `telemetry` | position, homing state, solenoid temp estimate, Wi-Fi RSSI, heap, queue depth |
| Dev→Hub | `fault` | code, detail |
| Both | `time_ping` / `time_pong` | t1, t2, t3 |

**FR-D4 Buffering.** The device keeps a queue of at least 2 s of commands; the Hub keeps 300–2000 ms of look-ahead in it. Commands are idempotent by sequence number.

**FR-D5 Firmware updates** over the air, signed, A/B partitions with rollback, managed by the Hub Agent.

**FR-D6 Device-side safety** does not depend on the Hub: soft limits, a solenoid duty limit, a watchdog (stop if the Hub is silent for more than 1 s while moving), and an estop input.

### 5.11 Calibration Service (Hub)

**FR-K1 Bottle positions.** A guided jog wizard finds each bottle's strike position; an optional automatic sweep uses the microphone to find the loudest strike point.
**FR-K2 Tuning.** Strike each bottle, measure fundamental frequency and decay, store pitch in cents. Warn if a bottle has drifted (for example water evaporated) by more than 15 cents. Phase 3: suggest how much water to add or remove.
**FR-K3 Latency.** Measure strike-to-sound latency per bottle with the microphone.
**FR-K4 LED alignment.** See FR-L1.
**FR-K5 Versioning.** Each calibration gets a version; duets compile against a specific version.

### 5.12 Identity, Sessions & Rigs

**FR-I1** Sign in with email magic link or OAuth; guest mode on a rig for demos.
**FR-I2** Households and classrooms with roles. Child accounts are created by a parent or teacher, with parental consent (COPPA/GDPR-K) and no public sharing by default.
**FR-I3** Pair a rig to an account with a one-time code shown on the Hub.
**FR-I4** A rig can be "claimed" for a session; one active session per rig at a time; spectator links for a live audience.

### 5.13 Telemetry, Recording & Analytics

**FR-T1** Device health dashboard and alerts (offline, repeated faults, thermal limits).
**FR-T2** Performance metrics: timing error distribution, pianist accuracy, mode use, composition success rate, repair rate, LLM latency and cost per duet.
**FR-T3** Optional audio/video recording of a performance, with a shareable clip (consent required).
**FR-T4** Product analytics with privacy-preserving defaults; no raw audio leaves the Hub without consent.

---

## 6. API Surface (public, versioned `/v1`)

### 6.1 REST

| Method & Path | Purpose |
|---|---|
| `POST /v1/compositions` | Create a duet from a prompt (async; returns `composition_id`) |
| `GET /v1/compositions/{id}` | Status, DuetScore, repair log |
| `POST /v1/compositions/{id}/variations` | Easier / harder / edit instruction |
| `POST /v1/duets/import` | Upload MIDI |
| `GET /v1/duets/{id}` · `PATCH` · `DELETE` | Library management |
| `GET /v1/duets/{id}/midi` | Compiled MIDI download |
| `GET /v1/duets?query=&difficulty=&style=` | Search |
| `POST /v1/rigs/pair` · `GET /v1/rigs/{id}` | Rig pairing and status |
| `GET /v1/rigs/{id}/profile` · `PUT /v1/rigs/{id}/calibration` | Profiles and calibration |
| `POST /v1/sessions` | Start a session (rig, duet, mode) |
| `POST /v1/sessions/{id}/transport` | play / pause / seek / tempo / loop |
| `GET /v1/performances/{id}` | Results and grading |
| `GET /v1/users/me/progress` | Skill model and paths |

### 6.2 Real-time streams (WebSocket)

- `wss://…/v1/compositions/{id}/stream` — composition progress events (`thinking`, `draft`, `validating`, `repairing`, `ready`).
- `wss://hub.local/v1/sessions/{id}/live` — conductor state, current bar and beat, upcoming cues, hit grades, tempo, faults. The UI uses this to draw the on-screen keyboard and robot animation that mirror the real rig.

### 6.3 Errors

Errors use RFC 9457 problem details, with stable codes such as `SCORE_INFEASIBLE`, `RIG_OFFLINE`, `CALIBRATION_STALE`, `LLM_TIMEOUT` and `CONTENT_BLOCKED`.

---

## 7. Configuration Artifacts

### 7.1 Composition prompt pack
Versioned system prompts, the schema, few-shot examples per style, and evaluation results. Prompts change only through the evaluation gate (§9.3).

### 7.2 Instrument profile (example)

```yaml
id: bottles-v1
kind: robot.mallet.monophonic
notes:
  - { name: C5, hz: 523.4, steps: 1200 }
  - { name: D5, hz: 587.1, steps: 7600 }
  # … 8 entries, from calibration
kinematics: { steps_per_mm: 80, v_max_mm_s: 500, a_max_mm_s2: 5000, settle_ms: 15 }
striker:   { pulse_us: [15000, 30000], recovery_ms: 60, latency_ms: 12, duty_limit: 0.2 }
sound:     { decay_ms: 1800, sustain: natural }
```

Every new robotic instrument (Phase 4) is a new profile plus a firmware driver. The Compiler, Composition Service and Conductor stay the same.

---

## 8. Non-Functional Requirements

| Area | Requirement |
|---|---|
| Real-time timing | Robot onset error ≤ ±10 ms p95; LED cue error ≤ ±15 ms p95; Hub→device command jitter ≤ 2 ms |
| Listening latency | MIDI input→grade ≤ 20 ms; microphone input→grade ≤ 60 ms |
| Composition latency | First draft streamed in ≤ 3 s; validated 16-bar duet ready in ≤ 10 s p90; ≤ 25 s for 64 bars |
| Composition quality | ≥ 98% of generated duets pass feasibility after repair; ≥ 90% pass with no deterministic repair (by Phase 2) |
| Availability | Cloud 99.9%; the Hub can play cached duets fully offline |
| Scale (Phase 4) | 10 000 rigs, 1 000 concurrent compositions, 100 concurrent remote duets |
| Security | TLS everywhere; device identity by per-device keys; signed firmware; least-privilege API tokens; secrets never stored on the ESP32 in plain text |
| Privacy | Audio is processed on the Hub by default; child data minimized; data export and deletion |
| Cost | LLM cost per composed duet tracked; target ≤ $0.05 average through caching, a fast default model and partial-bar repair |
| Observability | Structured logs, traces across cloud→Hub→device (correlation id per session), metrics dashboards |

---

## 9. Testing & Quality

### 9.1 Digital twin
A simulated rig with a kinematic model, virtual ESP32 and synthetic audio runs the full stack in CI. The website's simulation becomes a client of this twin, so the "pre-written examples" become live compositions.

### 9.2 Hardware-in-the-loop
A bench rig with a contact microphone measures real onset timing against the plan on every firmware or scheduler release.

### 9.3 Composition evaluation gate
A fixed set of 200 or more prompts across styles and difficulties. Metrics: feasibility pass rate, repair count, difficulty accuracy (target vs. scored), musicality (listener ratings plus an LLM judge), copyright similarity. A prompt or model change ships only if it doesn't regress.

### 9.4 Contract tests
Versioned Device Protocol and DuetScore schema tests for backwards compatibility (old firmware with new Hub, old duets with a new compiler).

---

## 10. Phased Roadmap

Each phase leaves a working, demo-ready system.

### Phase 0 — "It Plays" (finish the current build)
**Goal:** the robot and the lights perform a hand-written two-part MIDI file together, locally.

- Firmware: homing, `move_at` / `strike_at`, LED frames, estop, watchdog (§5.10, FR-D6).
- Score Compiler v0: MIDI import (FR-S7), robot feasibility check (FR-S3), robot and LED plans (FR-S6).
- Hub v0: a CLI or local app with a simple fixed-tempo conductor (FR-P1 subset), serial transport, basic clock sync.
- Calibration v0: manual bottle positions and LED key mapping.

**Exit criteria:** a 32-bar duet plays end to end; robot onset error ≤ ±20 ms p95; no missed strikes at 120 bpm eighth notes between adjacent bottles.

### Phase 1 — "First Duet" (the LLM connection)
**Goal:** type a request, hear the duet a minute later.

- DuetScore schema v1, Composition Service with validate–repair loop (FR-C1…C4, C6, C9).
- Reachability matrix in the prompt; deterministic repair (FR-S4); difficulty scoring (FR-S5).
- Wi-Fi WebSocket transport, mDNS discovery, 2 ms clock sync (FR-D1…D4).
- Transport controls and practice loop (FR-P3); cloud library basics (FR-B1, B4); accounts and rig pairing (FR-I1, I3).
- Live session stream for the UI; the web simulation driven by real compositions.
- Calibration wizard with microphone tuning (FR-K1…K3).

**Exit criteria:** ≥ 95% of evaluation prompts produce playable duets; 16-bar duet ready in ≤ 10 s p90; onset error ≤ ±10 ms p95; a non-technical person completes a duet with no help.

### Phase 2 — "It Listens"
**Goal:** the system hears the pianist and plays with them, not just next to them.

- Listening Engine: MIDI input, then microphone with robot self-filtering (FR-H1…H4).
- Wait mode and follow mode (FR-P2, FR-H5); hit and miss LED feedback (FR-L2).
- Performance review and grading (FR-E4); skill model v1 (FR-E1) feeding composition (FR-E2).
- Variations ("easier", "harder") as diff edits (FR-C8); lesson paths v1 (FR-E3).
- Degraded-mode audio fallback (FR-P5); telemetry dashboards (FR-T1, T2).

**Exit criteria:** score following stays locked on ≥ 95% of beginner performances; measurable improvement (accuracy +15%) over 5 sessions for test users; follow mode feels "natural" in user testing (≥ 4/5).

### Phase 3 — "It Responds"
**Goal:** a real musical conversation.

- Call-and-response and jam modes (FR-P2); Response Generator with local fast replies and LLM-enhanced replies (FR-G1…G3).
- Voice requests ("play something happy") through speech-to-text on the Hub.
- Expressive robot dynamics per bottle (FR-R4 full); lookahead parking (FR-R2).
- Water-level tuning suggestions (FR-K2); classroom and kiosk mode (FR-E5); performance recording and sharing (FR-T3).
- Copyright guard with similarity check (FR-C5); explanations (FR-C7).

**Exit criteria:** the robot answers a phrase within one beat ≥ 99% of the time; users rate responses "musical" ≥ 4/5; a classroom runs 20 students through one rig in a lesson.

### Phase 4 — "Ensemble & Platform"
**Goal:** Duet becomes a platform for human–robot music anywhere.

- **Instrument profiles as plugins:** marimba, glockenspiel, drum robot, polyphonic multi-striker bottles; an SDK and reference firmware for makers to add their own robots.
- **Ensembles:** N robots plus M humans, with the compiler assigning parts to instruments by range and capability; a trio or quartet from one prompt.
- **Remote duets:** two rigs in different places; the human on rig A plays with the robot on rig B and vice versa, with network latency hidden through look-ahead and turn-based structures.
- **Community library:** public duets, remixes and forks, moderation, featured artists and teachers, rating.
- **Live show mode:** audience votes on the next style; a projector view; multi-rig synchronized performance.
- **Open API and webhooks** for schools, museums and creative coders.
- Scale and NFR targets for Phase 4 (§8).

**Exit criteria:** at least 3 instrument types supported by profile alone; a remote duet across continents rated playable; 3rd-party robot integrated using only the SDK.

### Phase summary

| | Phase 0 | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|---|---|---|---|---|---|
| Theme | It plays | First duet | It listens | It responds | Ensemble |
| Composition | hand-written MIDI | LLM + repair | skill-targeted | real-time replies | multi-part ensembles |
| Pianist | follows lights | follows lights | graded, wait/follow | conversation | anywhere, remote |
| Robot | fixed tempo | fixed tempo | tempo-following | expressive, improvising | many instruments |
| Platform | local CLI | accounts + library | progress + lessons | classrooms, sharing | community + SDK |

---

## 11. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LLM writes musically weak or infeasible scores | Constraint-aware prompts, reachability matrix, validate–repair loop, evaluation gate, curated fallback library |
| The carriage is too slow for interesting melodies | Composition is designed around the reachability matrix; parking moves; a Phase 4 multi-striker profile |
| Wi-Fi jitter at exhibitions | Absolute-time commands with ≥ 300 ms buffer; USB serial fallback; device watchdog |
| Bottle tuning drift | Re-tune check at session start; pitch-tolerant mapping; water-level hints |
| Microphone confuses bottles with piano | Robot self-filtering from known schedule; prefer MIDI input on digital pianos |
| Children's privacy | On-Hub audio processing, parental consent, no public sharing for minors by default |
| Copyright | Style-not-melody policy, public-domain list, similarity check |
| LLM cost and latency | Caching, fast default model, partial repair, streaming |

---

## 12. Glossary

- **DuetScore** — canonical JSON score with robot and pianist parts plus turns and annotations.
- **Reachability matrix** — minimum time between strikes for every pair of bottles.
- **Hub** — the local machine that runs real-time services next to the rig.
- **Rig** — one robot, LED guide, piano and Hub.
- **Instrument profile** — the data that describes what an instrument can play and how fast.
- **Wait / follow mode** — the robot waits for the pianist, or follows their tempo.
