# Rig build and setup guide

How to wire, flash, test, calibrate and run the Duet rig. For what the firmware and the
Hub say to each other, see the [device protocol](device-protocol.md); for how the
software fits together, see the [architecture](architecture.md).

> **Status:** the firmware core is tested natively and against the Hub (contract test),
> but the ESP32 build (`firmware/src/main.cpp`) has **not yet been compiled or run on a
> real board**. Expect to fix small things on first flash. Part numbers below are
> suggestions; equivalents work.

## What you are building

![Rig front view](images/rig-layout.svg)

Eight tuned glass bottles hang by their necks from the gantry. A carriage runs on two
steel rods underneath, driven by a stepper motor and a timing belt. A solenoid on the
carriage fires a striker rod up into the bottle above it. An inductive sensor at the
motor end tells the firmware where zero is. One ESP32 runs the carriage, the striker and
the LED strip over the piano.

The bottle positions in the picture come from `src/duet/profiles/bottles-v1.yaml`
(placeholders until calibrated). Regenerate the picture with
`python tools/make_doc_images.py` after you change the profile.

### Parts

| Part | Used for | Notes |
|---|---|---|
| ESP32 DevKit (ESP32-WROOM-32) | the rig's controller | runs `firmware/` |
| NEMA 17 stepper + GT2 belt + 20T pulley + idler | carriage drive | 1/16 microstepping gives 80 steps per mm |
| Stepper driver: TMC2209 (quiet) or A4988 | drives the motor | set the current limit for your motor |
| 2 ground steel rods + linear bearings | carriage guides | |
| JF-1039B push-pull solenoid, 12 V | striker | on the carriage, rod pointing up |
| Logic-level N-MOSFET (IRLZ44N or similar) + 100 Ω + 10 kΩ | switches the solenoid | 10 kΩ gate-to-ground keeps it off at boot |
| Schottky diode (1N5819) | flyback across the solenoid | **required**; protects the MOSFET |
| LJ12A3-4-Z/BX inductive sensor (NPN, normally open) + 10 kΩ | home position | pull-up to 3.3 V, not 12 V |
| Emergency stop button (normally open) + 10 kΩ | stops everything | pull-up to 3.3 V; see the note on GPIO 35 |
| WS2812B strip, 144 LEDs/m, 1.22 m (176 LEDs) | lights over the keys | |
| 74AHCT125 level shifter + 330 Ω | LED data, 3.3 V to 5 V | |
| 1000 µF capacitor | across 5 V at the strip | |
| 12 V supply, 3 A or more, with an inline fuse | motor, solenoid, sensor | |
| 5 V supply, 4 A or more | LED strip | the firmware's brightness cap keeps it within budget |

## Wiring

![Rig wiring](images/wiring.svg)

| ESP32 pin | Goes to | Direction | Notes |
|---|---|---|---|
| GPIO 25 | driver STEP | out | step pulses from FastAccelStepper |
| GPIO 26 | driver DIR | out | if the carriage homes the wrong way, swap one motor coil pair |
| GPIO 27 | driver EN | out | enabled automatically while moving |
| GPIO 32 | MOSFET gate (via 100 Ω) | out | high = solenoid on |
| GPIO 34 | home sensor signal | in | active low (`HOME_ACTIVE_LOW = true`); external 10 kΩ pull-up to 3.3 V |
| GPIO 35 | emergency stop button | in | active low; **external** 10 kΩ pull-up to 3.3 V |
| GPIO 13 | level shifter → strip DIN | out | through 330 Ω at the strip end |
| GND | every ground | — | 12 V, 5 V, driver, MOSFET source, sensor, strip |

> **GPIO 34 and 35 are input-only and have no internal pull-up resistors.** Without the
> external 10 kΩ pull-ups the pins float, and the emergency stop can trip at random or
> never. The firmware sets them as plain inputs and relies on those resistors.

Change pins in `firmware/src/board.h` if your wiring differs.

### Before you power it on

```mermaid
flowchart TD
    a["All grounds joined?"] -->|"yes"| b["Flyback diode across the solenoid,<br/>stripe to +12 V?"]
    b -->|"yes"| c["10 kΩ pull-ups on GPIO 34 and 35<br/>go to 3.3 V, not 5 V or 12 V?"]
    c -->|"yes"| d["LED strip powered from the 5 V supply,<br/>not the ESP32?"]
    d -->|"yes"| e["Driver current limit set?<br/>Motor coils paired correctly?"]
    e -->|"yes"| f["Carriage moves freely by hand<br/>end to end?"]
    f -->|"yes"| go["Power on: 5 V first, then 12 V"]
    a -->|"no"| fix["Fix it first"]
    b -->|"no"| fix
    c -->|"no"| fix
    d -->|"no"| fix
    e -->|"no"| fix
    f -->|"no"| fix
```

## The LED strip over the keys

![Which LEDs light for which key](images/led-strip.svg)

- The strip runs along the cabinet edge just above the keys, LED 0 over the left edge of
  the lowest key (A0).
- Each key lights the LEDs centred over it, about two per semitone. The mapping is
  `plans.led_span()`; the picture above is drawn from it.
- If the lights sit a little left or right of the keys, set `first_led_mm` in
  `src/duet/profiles/piano-88.yaml` (millimetres from LED 0 to the left edge of A0).
- Colours: dim white before a note (pre-cue, one beat ahead), bright white to play now,
  blue for the count-in, soft blue over the whole strip for "your turn" in a jam.

## Mechanical setup

```mermaid
flowchart LR
    subgraph motor["Motor end (x = 0)"]
        m["Stepper + pulley"]
        s["Home sensor<br/>1–4 mm from the carriage's<br/>steel target"]
    end
    subgraph rail["Rail"]
        c["Carriage<br/>solenoid + striker rod"]
    end
    subgraph idler["Idler end"]
        i["Idler pulley"]
    end
    m ---|"belt"| c
    c ---|"belt"| i
    s -.->|"sees the carriage<br/>at home"| c
```

- **Homing direction:** on `home`, the carriage drives toward negative steps (the motor
  end) at 4000 steps/s until the sensor triggers. If it runs the other way, swap one
  motor coil pair (or invert DIR).
- **Sensor gap:** the LJ12A3 sees steel at up to about 4 mm. Put a small steel target on
  the carriage. Homing gives up after 20 s with `HOMING_TIMEOUT`.
- **Travel:** the firmware refuses moves outside 0 … 48 000 steps (600 mm). Make sure the
  carriage can really travel that far, or lower `travel_steps` in
  `firmware/lib/duet_core/src/duet_config.hpp` and in the profile.
- **Belt tension:** firm, no slack. A slipping belt shows up as `NOT_ARRIVED` faults or
  strikes that miss the bottle.
- **Bottles:** rubber caps on the necks let the glass ring and stop it swinging. The
  striker should hit the bottom of each bottle squarely when the carriage is at its
  position.

## Flashing the firmware

```mermaid
flowchart TD
    t["make -C firmware test<br/>(native core tests, no board)"] --> s["cp firmware/src/secrets.example.h<br/>firmware/src/secrets.h<br/>and add your Wi-Fi"]
    s --> p["Install PlatformIO"]
    p --> f["cd firmware && pio run -t upload"]
    f --> m["pio device monitor"]
    m --> ok{"Prints<br/>duet: duet-rig-1 on ws://IP:8765 ?"}
    ok -->|"yes"| next["Bench test over serial"]
    ok -->|"no, stuck"| wifi["Check SSID and password;<br/>the ESP32 needs 2.4 GHz Wi-Fi"]
```

Commands, in order:

```bash
make -C firmware test
```

```bash
cp firmware/src/secrets.example.h firmware/src/secrets.h
```

```bash
cd firmware && pio run -t upload && pio device monitor
```

`secrets.h` is ignored by git; never commit it.

## Bench test over serial

With the monitor open, type one JSON message per line. A command with `"t_us":0` is
already due, so it runs at once. That makes hand testing easy, though it also counts as
"late" in the device's statistics.

```mermaid
sequenceDiagram
    participant You as You (serial monitor)
    participant D as Device
    You->>D: {"type":"home","seq":1}
    D-->>You: ack ok
    D-->>You: telemetry {homed: true, position: 0}
    You->>D: {"type":"move_at","seq":2,"t_us":0,"target_steps":26800,"v_max_mm_s":200,"a_max_mm_s2":2000}
    D-->>You: ack ok  (the carriage goes to G5)
    You->>D: {"type":"strike_at","seq":3,"t_us":0,"pulse_us":20000}
    D-->>You: ack ok  (G5 rings)
    You->>D: {"type":"led_frame_at","seq":4,"t_us":0,"first":79,"count":2,"rgb":[255,255,255]}
    D-->>You: ack ok  (the light over C4)
```

Copy-paste versions:

```json
{"type":"home","seq":1}
{"type":"move_at","seq":2,"t_us":0,"target_steps":26800,"v_max_mm_s":200,"a_max_mm_s2":2000}
{"type":"strike_at","seq":3,"t_us":0,"pulse_us":20000}
{"type":"led_frame_at","seq":4,"t_us":0,"first":79,"count":2,"rgb":[255,255,255]}
{"type":"led_frame_at","seq":5,"t_us":0,"first":0,"count":176,"rgb":[0,0,0]}
```

Wait for each move to finish before sending the strike, or it is refused with
`NOT_ARRIVED`. Use slow speeds (200 mm/s) for first tests. Press the emergency-stop
button once to check it: everything should stop and further commands answer
`error: emergency stop` until you power-cycle.

> Watchdog: on serial there is no Hub sending heartbeats. A move that takes longer than
> 1 s after your last message is stopped with `WATCHDOG`. Send short moves, or any line
> (even `{"type":"heartbeat","seq":0}`) while it moves.

## First performance from the Hub

```bash
duet play examples/rain-on-the-bottles.json --device ws://duet-rig-1.local:8765
```

If `.local` names don't resolve on your network, use the IP address the serial monitor
printed. Rehearse without the rig first, on the simulated device:

```bash
duet device-sim --port 8765
```

```bash
duet play examples/rain-on-the-bottles.json --device ws://127.0.0.1:8765
```

```mermaid
sequenceDiagram
    autonumber
    participant Hub
    participant Rig
    Hub->>Rig: connect
    Rig-->>Hub: hello
    Hub->>Rig: 16 clock pings
    Note over Hub: prints the clock offset, e.g. "± 400 us"
    Hub->>Rig: home
    Rig-->>Hub: telemetry homed
    Hub->>Rig: count-in lights, then moves and strikes, 500 ms ahead
    Note over Hub,Rig: heartbeats every 250 ms, resync every 2 s
    Hub-->>Hub: "sent N commands, errors: 0"
```

## Calibration

The profile's numbers are placeholders until you measure your rig. Calibration measures
each bottle's real pitch, how long it rings, and the delay from strike command to sound.

```mermaid
sequenceDiagram
    autonumber
    participant You
    participant Hub as Hub (duet CLI)
    participant Rig
    participant Mic as Microphone

    You->>Hub: duet sweep sweep.json
    Hub-->>You: a score: every bottle once per second
    You->>Mic: start recording
    You->>Hub: duet play sweep.json --device ws://…
    Hub->>Rig: strikes C5, D5, … C6, 1 s apart
    Rig-->>Mic: eight rings
    You->>Mic: stop, save sweep.wav
    You->>Hub: duet calibrate sweep.wav --out calibrated.yaml
    Hub-->>You: pitch, latency and ring time per bottle,<br/>warnings like "bottle 3 (E5) is +25 cents off: add a little water"
    You->>Hub: use --robot calibrated.yaml from now on
```

```bash
duet sweep sweep.json
```

```bash
duet calibrate sweep.wav --out calibrated.yaml
```

```bash
duet --robot calibrated.yaml play examples/rain-on-the-bottles.json --device ws://duet-rig-1.local:8765
```

### Reading the results

| Result | What it means | What to do |
|---|---|---|
| `bottle N (E5) is +25 cents off: add a little water` | it sounds sharp | add water (lowers a struck bottle's pitch), then sweep again |
| `… -30 cents off: pour out a little water` | it sounds flat | pour a little out, then sweep again |
| `bottle N now sounds G#5, not G5; it was renamed` | more than 50 cents off | retune it, or keep the new note: the profile already uses it |
| `bottle N (C6) was not heard` | no strike in its window | check that bottle's position and the striker |
| latency far above 20 ms | slow solenoid or a far microphone | put the microphone near the bottles; the profile now compensates |

Each run writes a new version (`calibration.version`) with the date, so you can compare.
Warnings start at 15 cents.

### Strike positions

If a bottle sounds dull, the striker may be hitting off-centre. Jog the carriage over
serial (`move_at` with `t_us: 0`) in small steps around that bottle, strike at each one,
and note the position that rings best. Put that in `steps:` in the profile.
`calibration.best_strike_positions()` does this choice for you from a list of
(steps, loudness) measurements.

## Troubleshooting

```mermaid
flowchart TD
    start["Something is wrong"] --> q1{"Does the Hub connect?<br/>(prints 'connected to …')"}
    q1 -->|"no"| n1["Serial monitor: did it join Wi-Fi?<br/>Same network as the Hub?<br/>Try the IP instead of .local"]
    q1 -->|"yes"| q2{"Does it home?<br/>(telemetry homed true)"}
    q2 -->|"no: HOMING_TIMEOUT"| n2["Sensor LED lights near steel?<br/>Pull-up to 3.3 V fitted?<br/>Carriage moving toward the motor end?"]
    q2 -->|"yes"| q3{"Faults during the song?"}
    q3 -->|"NOT_ARRIVED"| n3["The carriage is slower than the profile says:<br/>check belt tension and driver current,<br/>or lower v_max / a_max in the profile"]
    q3 -->|"WATCHDOG"| n4["Wi-Fi dropped for a second:<br/>move the router closer,<br/>or use USB serial"]
    q3 -->|"DUTY_CYCLE"| n5["Too many strikes in 10 s:<br/>the score is too dense;<br/>run duet repair"]
    q3 -->|"SOFT_LIMIT"| n6["A bottle position is beyond travel:<br/>fix steps in the profile"]
    q3 -->|"none"| q4{"Notes sound late or early?"}
    q4 -->|"all by the same amount"| n7["Recalibrate: the latency is off"]
    q4 -->|"getting worse over time"| n8["Clock drift: check that resync runs<br/>(it is on by default)"]
    q4 -->|"no"| q5{"Lights over the wrong keys?"}
    q5 -->|"yes"| n9["Set first_led_mm in piano-88.yaml"]
```

| Symptom | Likely cause | Check |
|---|---|---|
| ESP32 resets when the solenoid fires | supply dip or missing flyback diode | diode across the coil; separate 12 V and 5 V supplies; common ground |
| Solenoid clicks at power-on | MOSFET gate floating at boot | 10 kΩ gate-to-ground resistor |
| Emergency stop trips by itself | GPIO 35 floating | external 10 kΩ pull-up to 3.3 V |
| First LED wrong colour or flickers | 3.3 V data into a 5 V strip | level shifter; 330 Ω at DIN; short data wire |
| LEDs dim or red at the far end | voltage drop | feed 5 V at both ends of the strip |
| Strikes miss the bottle | belt slip or wrong positions | belt tension; strike positions |
| Motor hot or stalls | driver current too high or too low | set the current limit for your motor |

## Safety

```mermaid
flowchart LR
    subgraph always["Always on, in the firmware"]
        w["Watchdog<br/>stop if the Hub is silent 1 s"]
        d["Solenoid duty limit<br/>20% of any 10 s"]
        p["Pulse cap 50 ms"]
        l["Soft travel limits"]
        e["Emergency stop latches<br/>until power cycle"]
        h["Nothing moves before homing"]
    end
    subgraph you["Your job"]
        f["Fuse on the 12 V rail"]
        b["E-stop button in reach"]
        g["Glass: secure the caps;<br/>check bottles for cracks"]
        c["Keep fingers off the rail<br/>while homed"]
    end
```

- The solenoid coil heats up if held on. The firmware caps every pulse at 50 ms and keeps
  on-time under 20% of any 10 s. **Do not raise these limits** without measuring the
  coil temperature.
- The emergency stop cuts motion and the solenoid and refuses all commands until power is
  cycled. Consider wiring it to also cut the 12 V rail through a relay.
- Glass can crack if struck too hard. Start with short pulses (15 ms) and raise them only
  as far as the sound needs.
- Children will want to touch it. The carriage moves fast (up to 500 mm/s): keep hands
  away from the rail and belt while the rig is homed.
