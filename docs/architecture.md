# Duet architecture (as built)

How the code that exists today fits together. For what the system *should* do, see the
[functional spec](backend-functional-spec.md); for the build order, see the
[implementation plan](implementation-plan.md). For the wire format between the Hub and
the rig, see the [device protocol](device-protocol.md); for building the rig, see the
[rig guide](rig-guide.md).

## The big picture

Everything turns into one score format, the **DuetScore**. A score is checked against the
robot's physics and the pianist's level, repaired if needed, turned into timed plans, and
performed by the conductor through the device gateway to the rig.

```mermaid
flowchart LR
    subgraph inputs["Ways in"]
        prompt["Text request"]
        audio["Audio or video file"]
        midi["MIDI file"]
        json["DuetScore JSON"]
        phrase["Pianist's phrase<br/>(call and response)"]
    end

    subgraph core["Score core"]
        score[("DuetScore")]
        check["Check<br/>robot physics + pianist level"]
        repair["Repair<br/>fold · shift · drop · slow"]
    end

    subgraph perform["Performance"]
        plans["Plans<br/>robot moves + strikes<br/>LED cues"]
        conductor["Conductor<br/>fixed · wait · follow"]
        gateway["Device gateway<br/>clock sync · heartbeat"]
    end

    rig["Rig<br/>ESP32 firmware"]

    prompt -->|"compose (Claude)"| score
    audio -->|"transcribe + arrange"| score
    midi -->|"import"| score
    json --> score
    phrase -->|"respond"| score
    score --> check
    check -->|"problems"| repair
    repair --> score
    check -->|"playable"| plans
    plans --> conductor
    conductor --> gateway
    gateway -->|"WebSocket"| rig
```

## Where it runs

```mermaid
flowchart TB
    subgraph cloud["Cloud (optional)"]
        claude["Claude API<br/>composition"]
    end

    subgraph hub["Duet Hub: laptop or Raspberry Pi"]
        cli["duet CLI"]
        api["REST API<br/>FastAPI + jobs"]
        db[("SQLite store")]
        lib["duet package<br/>score · plans · conductor"]
        gw["Device gateway"]
        listen["Listening<br/>MIDI keyboard · microphone"]
    end

    subgraph rig["Rig"]
        esp["ESP32<br/>duet_core executor"]
        motor["Stepper + belt<br/>carriage"]
        sol["Solenoid striker"]
        sensor["Home sensor"]
        leds["LED strip<br/>over the piano"]
    end

    app["Phone / web app"] -->|"HTTPS"| api
    cli --> lib
    api --> lib
    api --- db
    lib -->|"HTTPS"| claude
    lib --> gw
    listen --> lib
    gw <-->|"WebSocket on the LAN<br/>or USB serial"| esp
    esp --> motor
    esp --> sol
    sensor --> esp
    esp --> leds
```

Real-time timing never depends on the internet: the Hub and the rig talk on the local
network, and every command is sent ahead of time with an absolute time stamp.

## Module map

All Python code is in `src/duet/`. Arrows mean "uses".

```mermaid
flowchart TB
    subgraph foundation["Foundation"]
        pitch["pitch<br/>names · MIDI · Hz"]
        score_m["score<br/>DuetScore model"]
        timing["timing<br/>bars → seconds"]
        profile["profile<br/>instrument YAML"]
        kin["kinematics<br/>travel time · reachability"]
    end

    subgraph checks["Checks and fixes"]
        feas["feasibility<br/>robot rules"]
        diff["difficulty<br/>pianist levels"]
        rep["repair"]
        var["variations<br/>slower · easier · swap"]
        copy["copyright<br/>melody guard"]
    end

    subgraph io["Formats"]
        midio["midi_io"]
    end

    subgraph make["Making scores"]
        compose["compose/<br/>Claude composer"]
        audio["audio/<br/>transcribe · arrange"]
        respond["respond<br/>call and response"]
        ens["ensemble<br/>tracks → one score, a part per member"]
    end

    subgraph play["Playing"]
        plans["plans"]
        cond["conductor"]
        follow["follow"]
        listening["listening<br/>grading · MIDI keys"]
        mic["mic"]
        session["session<br/>jam turns"]
        proto["protocol"]
        sim["sim<br/>simulated rig"]
        device["device/<br/>gateway · clock · sim server"]
    end

    subgraph learn["Learning and service"]
        ped["pedagogy<br/>skills · lessons"]
        cal["calibration"]
        evalm["evaluation"]
        api["api/<br/>app wiring · routes · views"]
        storage["storage<br/>records by kind and id"]
        lib["library · learning<br/>versions · skills · lessons"]
        jobs["jobs"]
        cli["cli"]
    end

    score_m --> pitch
    timing --> score_m
    profile --> score_m
    kin --> profile
    feas --> kin
    feas --> timing
    rep --> feas
    diff --> timing
    var --> diff
    var --> rep
    midio --> score_m
    compose --> rep
    compose --> diff
    compose --> copy
    audio --> rep
    respond --> rep
    ens --> rep
    plans --> feas
    cond --> plans
    cond --> proto
    cond --> follow
    cond --> listening
    mic --> listening
    session --> cond
    session --> respond
    device --> proto
    sim --> proto
    ped --> listening
    ped --> audio
    cal --> profile
    evalm --> compose
    api --> jobs
    api --> lib
    lib --> storage
    jobs --> storage
    lib --> ped
    api --> compose
    api --> audio
    api --> ped
    api --> var
    cli --> cond
    cli --> device
```

| Layer | Modules | One-line purpose |
|---|---|---|
| Foundation | `pitch`, `score`, `timing`, `profile`, `kinematics` | The vocabulary: notes, scores, time, instruments, motion physics |
| Checks and fixes | `feasibility`, `difficulty`, `repair`, `variations`, `copyright` | Can it be played? How hard is it? Make it playable, easier, original |
| Making scores | `compose/`, `audio/`, `respond`, `ensemble`, `midi_io` | Every way of getting a DuetScore |
| Playing | `plans`, `conductor`, `follow`, `listening`, `mic`, `session`, `protocol`, `sim`, `device/` | Turn a score into timed commands and listen to the pianist |
| Learning and service | `pedagogy`, `calibration`, `evaluation`, `library`, `learning`, `storage`, `api/`, `jobs`, `cli` | Skills, lessons, measuring the rig and the composer; the library and learning rules as plain functions over a store; the outside interfaces (`api/app.py` only wires; routes live in `api/routes/`, one module per area) |
| Firmware | `firmware/lib/duet_core/` (C++) | Runs timed commands on the rig and keeps the hardware safe |

## The score: one format for everything

```mermaid
classDiagram
    class DuetScore {
        schema: "duetscore/2"
        meta: Meta
        parts: name → PartInfo
        events: Event[]
        sections: Section[]
        turns: Turn[]
    }
    class Meta {
        title
        key
        time_signature: (beats, unit)
        tempo_bpm
        difficulty_target: 1..5
    }
    class Event {
        part: a part's name
        bar: 1-based
        beat: 1-based
        dur: beats
        pitch: "C4" or MIDI number
        vel: 1..127
    }
    class PartInfo {
        instrument: "bottles-v1"
        performer: bot | human
        range: (low, high)
    }
    DuetScore --> Meta
    DuetScore --> "many" Event
    DuetScore --> "many" PartInfo
```

- Scores are **immutable** (frozen pydantic models). Every change makes a new score.
- Each part names an **instrument** (`duet.instruments`) and its **performer**: a bot or
  a human (`duet.performers`), which owns the rule for what it can play. Version-1 files
  (exactly "robot" and "pianist", with `instrument_profile`) are read as version 2.
- Code never asks for "the robot part". Things that make a duet (the composer, MIDI
  import, the arranger, call and response) make it for a `Duo` (part names and
  instruments as data); features made for duets (swap, teaching a part, live playing
  until step 1e) ask for `score.part_played_by("bot")`, which says clearly when a score
  is not a duet.
- Pitches are stored as MIDI numbers and written as names (`"E5"`), so JSON stays readable.
- `timing` is the only module that turns bars and beats into seconds.
- Claude never writes a DuetScore directly. It writes a smaller, strict **draft** JSON
  (`compose/draft.py`), and code converts it. That lets the API enforce the draft's shape.

## Check, repair, plan

```mermaid
flowchart LR
    s["DuetScore"] --> fr{"Robot rules<br/>feasibility.check_robot"}
    fr -->|"NOT_ON_BOTTLE"| fold["Octave-fold<br/>to a bottle"]
    fr -->|"SIMULTANEOUS"| top["Keep the<br/>highest note"]
    fr -->|"TOO_FAST"| shift{"Small move?<br/>≤ 0.5 beat"}
    shift -->|"yes"| later["Shift to the<br/>next grid point"]
    shift -->|"no"| drop["Drop the note"]
    fr -->|"DUTY_CYCLE"| drop
    drop --> many{"More than 20%<br/>dropped?"}
    many -->|"yes, and tempo may change"| slow["Slow the tempo<br/>and start again"]
    fr -->|"ok"| plan["plans.robot_plan<br/>plans.led_plan"]
```

The robot rules come from the **reachability matrix**: the minimum time between strikes
on any two bottles, from the trapezoid motion model in `kinematics.py`. The same table is
put in Claude's prompt, so drafts are usually playable before any repair.

<details>
<summary>Reachability matrix for <code>bottles-v1</code> (ms between consecutive strikes)</summary>

| from \ to | C5 | D5 | E5 | F5 | G5 | A5 | B5 | C6 |
|---|---|---|---|---|---|---|---|---|
| **C5** | 60 | 305 | 465 | 625 | 785 | 945 | 1105 | 1265 |
| **D5** | 305 | 60 | 305 | 465 | 625 | 785 | 945 | 1105 |
| **E5** | 465 | 305 | 60 | 305 | 465 | 625 | 785 | 945 |
| **F5** | 625 | 465 | 305 | 60 | 305 | 465 | 625 | 785 |
| **G5** | 785 | 625 | 465 | 305 | 60 | 305 | 465 | 625 |
| **A5** | 945 | 785 | 625 | 465 | 305 | 60 | 305 | 465 |
| **B5** | 1105 | 945 | 785 | 625 | 465 | 305 | 60 | 305 |
| **C6** | 1265 | 1105 | 945 | 785 | 625 | 465 | 305 | 60 |

The diagonal is the solenoid's recovery time. Off the diagonal: the 30 ms pulse, then
travel, then 15 ms to settle. Regenerate with `reachability(robot_profile()).as_table()`.
</details>

### How a strike is planned

The carriage leaves **as late as possible**, so it waits at the last bottle while that
bottle rings. The solenoid fires early by the strike-to-sound latency, so the sound lands
on the beat.

![Move and strike timing](images/strike-timeline.svg)

## The conductor

The conductor turns plans into device messages and streams them ahead of time. Every
part is played: each bot part's moves and strikes, each human part's light cues (the
first human part's lights also count everyone in). ``routes`` say which devices play
each part: ``one_rig(score, devices)`` for the usual single board, or a rig per part for
an ensemble. Two bot parts on one device are refused: one carriage cannot be in two
places. ``instruments`` are the ones in use (say, a calibrated rig), before the
built-in ones.

```mermaid
stateDiagram-v2
    [*] --> IDLE
    IDLE --> PREPARING: perform()
    PREPARING --> COUNT_IN: every device reports homed
    COUNT_IN --> PLAYING: first beat
    PLAYING --> WAITING: wait mode, pianist note due
    WAITING --> PLAYING: right key pressed
    PLAYING --> ENDING: last message sent
    ENDING --> REVIEW
    REVIEW --> [*]
    PREPARING --> FAULT: homing timeout
    PLAYING --> FAULT: device fault
```

| Mode | Who sets the time | How it works | Lookahead |
|---|---|---|---|
| **Fixed** | The score | Every command at its planned time | 500 ms |
| **Wait** | The pianist | Commands up to the next pianist note are sent; later ones wait until the key is pressed, then shift by the wait | 500 ms |
| **Follow** | The pianist | Every command is timed through the follower's tempo map; speed-ups are capped by the robot's slack | 150 ms |
| **Call and response** | Turns | The pianist plays a phrase; the robot answers right after | 500 ms |
| **Ensemble** | The score | One stream for several rigs; each message goes to its own rig | 500 ms |

```mermaid
sequenceDiagram
    autonumber
    participant C as Conductor
    participant K as Key input<br/>(MIDI or mic)
    participant F as Follower
    participant D as Device

    Note over C,D: Follow mode: the robot keeps the pianist's tempo
    loop until the score ends
        C->>K: poll()
        K-->>C: notes played since the last poll
        C->>F: hear(note)
        F-->>F: re-anchor at this note,<br/>blend the new tempo,<br/>cap by the robot's slack
        C->>F: when is the next command?
        F-->>C: clock time
        C->>D: move_at / strike_at / led_frame_at<br/>(150 ms ahead)
    end
```

## Background jobs

Composition and transcription can take seconds to minutes, so the API can run them in
the background and stream progress.

```mermaid
sequenceDiagram
    participant App
    participant API
    participant Runner as Job runner
    participant Store
    participant Work as compose / transcribe

    App->>API: POST /v1/compositions?background=true
    API->>Runner: submit(work)
    Runner->>Store: job queued
    API-->>App: 202 { id, links.stream }
    App->>API: WebSocket /v1/jobs/{id}/stream
    Runner->>Work: run(progress)
    Work-->>Runner: progress("drafting")
    Runner->>Store: event
    API-->>App: { event: drafting }
    Work-->>Runner: progress("checking") ... ("ready")
    Runner->>Store: state = succeeded, result
    API-->>App: { job: succeeded, result }
```

Jobs live in the store, so they work the same with the in-memory store and SQLite.

## Extension points

Each of these is a small interface with a fake implementation in the tests, so tests
never need the network, a GPU or hardware.

| Interface | Where | Real implementations | Test stand-in |
|---|---|---|---|
| `Composer.write(system, messages)` | `compose/service.py` | `ClaudeComposer` | `ScriptedComposer` |
| `Transcriber.transcribe(audio, sr)` | `audio/notes.py` | `PyinTranscriber`, `BasicPitchTranscriber` | synthesized audio |
| `Separator.separate(path)` | `audio/fullmix.py` | `DemucsSeparator` | `FakeSeparator` |
| `Store` (add, put, get, list, delete, update) | `storage.py` | `MemoryStore`, `SqliteStore` | both, in every API test |
| `Device.send(msg)` | `conductor.py` | `DeviceGateway` | `SimulatedRig` |
| `KeyInput` (poll, wait_for) | `listening.py` | `MidiKeys`, `MicKeys` | `SimulatedPianist`, `TempoPianist`, `PhrasePianist` |
| `Hal` (C++) | `firmware/lib/duet_core/src/duet_hal.hpp` | `Esp32Hal` | `SimHal` |

## Time

There is one clock on the Hub: `device.clock.hub_now_us()` (monotonic microseconds).

```mermaid
flowchart LR
    score["Score time<br/>bar 3 beat 2"] -->|"timing"| sec["Seconds from bar 1<br/>2.667 s"]
    sec -->|"+ start_us"| hub["Hub clock<br/>hub_now_us()"]
    hub -->|"+ offset + drift<br/>(gateway, per device)"| dev["Device clock<br/>esp_timer_get_time()"]
```

- Plans are in seconds from bar 1. The conductor adds the start time.
- The gateway converts Hub time to each device's own clock, so firmware never deals with
  offsets. See [device protocol: clock sync](device-protocol.md#clock-sync).

## How it is tested

```mermaid
flowchart TB
    unit["Unit tests<br/>pitch, kinematics, repair, grading..."]
    prop["Property tests<br/>repair always ends playable,<br/>'easier' always lowers the level"]
    sim["Simulated rig<br/>Python physics, checks every strike"]
    socket["Real socket<br/>simulated device on a WebSocket,<br/>offset and drifting clock"]
    contract["Contract test<br/>Hub command stream through the<br/>C++ firmware core and the Python sim"]
    native["Native firmware tests<br/>make -C firmware test"]
    hw["Hardware in the loop<br/>(not yet)"]

    unit --> prop --> sim --> socket --> contract --> hw
    native --> contract
```

`make check` runs lint, every Python test and the native firmware tests. CI runs the same.
