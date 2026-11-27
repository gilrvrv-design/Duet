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
| NEMA 17 stepper + GT2 belt + 20T pulley + idler | carriage drive | 1/16 microstepping gives 80 steps per mm (200 × 16 steps per 40 mm) |
| Stepper driver A4988 (on a carrier board) | drives the motor | logic VDD from **3.3 V**; MS1–MS3, SLEEP and RESET tied to 3.3 V; set the current limit |
| 2 ground steel rods + linear bearings | carriage guides | |
| JF-1039B push-pull solenoid, 12 V | striker | on the carriage, rod pointing up; about 0.4 A (seller data, no datasheet found) |
| N-MOSFET IRLZ44N + 220 Ω + 10 kΩ | switches the solenoid | gate driven at **5 V** through the level shifter, not straight from the ESP32 |
| Schottky diode 1N5819 | flyback across the solenoid | **required**; 40 V, 1 A |
| LJ12A3-4-Z/BX inductive sensor (NPN, normally open, 6–36 V) + 4.7 kΩ, 27 kΩ, 10 kΩ | home position | pull-up to 12 V and a divider into GPIO 34; see below |
| Emergency stop button (normally open) + 10 kΩ | stops everything | pull-up to 3.3 V; see the note on GPIO 35 |
| WS2812B strip, 144 LEDs/m, 1.22 m (176 LEDs) | lights over the keys | |
| 74AHCT125 quad buffer + 330 Ω + 10 kΩ | LED data and solenoid gate, 3.3 V to 5 V | two of its four channels used; the other two tied off |
| 1000 µF capacitor | across 5 V at the strip | |
| 12 V supply, 3 A or more, with an inline fuse | motor, solenoid, sensor | size is an estimate |
| 5 V supply, 4 A or more | LED strip, level shifter | size is an estimate; the firmware's brightness cap helps |

## Wiring

![Rig wiring](images/wiring.svg)

| ESP32 pin | Goes to | Direction | Notes |
|---|---|---|---|
| GPIO 25 | A4988 STEP | out | step pulses from FastAccelStepper (A4988 needs ≥ 1 µs high and low) |
| GPIO 26 | A4988 DIR | out | if the carriage homes the wrong way, swap one motor coil pair |
| GPIO 27 | A4988 ENABLE | out | active low; enabled automatically while moving |
| GPIO 32 | 74AHCT125 2A → 2Y → 220 Ω → MOSFET gate | out | high = solenoid on; 10 kΩ from 2A to GND keeps it off during boot |
| GPIO 34 | home sensor, through the divider | in | active low (`HOME_ACTIVE_LOW = true`) |
| GPIO 35 | emergency stop button | in | active low; **external** 10 kΩ pull-up to 3.3 V |
| GPIO 13 | 74AHCT125 1A → 1Y → 330 Ω → strip DIN | out | |
| 3V3 | A4988 VDD, MS1–MS3, SLEEP, RESET, e-stop pull-up | — | |
| GND | every ground | — | 12 V, 5 V, driver, MOSFET source, sensor, strip |

> **GPIO 34 and 35 are input-only and have no internal pull-up resistors** (ESP32
> datasheet). Without the external resistors the pins float, and the emergency stop can
> trip at random or never. The firmware sets them as plain inputs and relies on those
> resistors.

### Why each connection is the way it is

These come from the component datasheets (see [Checked against datasheets](#checked-against-datasheets)).

```mermaid
flowchart LR
    esp["ESP32 output<br/>high ≥ 2.64 V"]
    esp -->|"needs ≥ 0.7 × VDD"| a4988["A4988 inputs<br/>VDD 3.3 V → 2.31 V ✓<br/>VDD 5 V → 3.5 V ✗"]
    esp -->|"needs ≥ 0.7 × 5 V = 3.5 V ✗"| ws["WS2812B DIN"]
    esp -->|"needs ≥ 2 V ✓"| ahct["74AHCT125<br/>outputs 5 V"]
    ahct -->|"5 V ✓"| ws
    ahct -->|"VGS 5 V: Rds(on) specified ✓"| fet["IRLZ44N gate"]
    esp -.->|"VGS 3.3 V: not specified"| fet
```

- **A4988 logic at 3.3 V.** Its inputs need at least 0.7 × VDD. At 5 V that is 3.5 V, more
  than the ESP32 guarantees (2.64 V). At 3.3 V it is 2.31 V.
- **A4988 microstep pins tied high.** MS1–MS3 have internal pull-downs, so if left open
  the driver runs in **full steps** and every move goes 16 times too far. All three high
  gives 1/16 step. SLEEP and RESET must be high too: STEP is ignored while RESET is low.
- **MOSFET gate at 5 V.** The IRLZ44N's on-resistance is specified only at VGS 4 V and
  above, and its threshold can be as high as 2 V. Driving the gate from a spare 74AHCT125
  channel gives 5 V. The 220 Ω keeps the buffer's output current under its 25 mA rating.
- **74AHCT125 tidy-up.** Its output enables (1OE, 2OE) are active low, so tie them to
  GND. Unused inputs must not float: tie 3A and 4A to GND, and 3OE and 4OE to 5 V.
- **Home sensor through a divider.** The sensor's sheet gives only "NPN, sink, 6–36 V",
  not its output circuit, and some modules have an internal pull-up to their own supply.
  So the output is pulled up to 12 V (4.7 kΩ) and divided down (27 kΩ / 10 kΩ). The sheet
  gives no output-low voltage either, which is why the triggered case is a condition:

  | Sensor state | GPIO 34 voltage | ESP32 needs |
  |---|---|---|
  | idle, 11.4 V supply, no internal pull-up | 11.4 × (37 / 41.7) × (10 / 37) = **2.73 V** | high ≥ 2.475 V |
  | idle, 12.6 V supply, strong internal pull-up | 12.6 × (10 / 37) = **3.40 V** | at most 3.6 V |
  | triggered (output sinking) | V_low × 10 / 37: **under 0.825 V while the sensor's low output is under 3 V** | low ≤ 0.825 V |

  **Measure before connecting:** power the sensor, hold steel near it and away from it,
  and check GPIO 34's side of the divider reads in those ranges before you plug it in.

### Before you power it on

```mermaid
flowchart TD
    a["All grounds joined?"] -->|"yes"| b["Flyback diode across the solenoid,<br/>stripe to +12 V?"]
    b -->|"yes"| c["10 kΩ pull-ups on GPIO 34 and 35<br/>go to 3.3 V, not 5 V or 12 V?"]
    c -->|"yes"| c2["Sensor divider measured:<br/>GPIO 34 side 2.7–3.4 V idle?"]
    c2 -->|"yes"| c3["A4988 VDD, MS1–MS3, SLEEP, RESET<br/>on 3.3 V?"]
    c3 -->|"yes"| d["LED strip powered from the 5 V supply,<br/>not the ESP32?"]
    d -->|"yes"| e["Driver current limit set?<br/>Motor coils paired correctly?"]
    e -->|"yes"| f["Carriage moves freely by hand<br/>end to end?"]
    f -->|"yes"| go["Power on"]
    a -->|"no"| fix["Fix it first"]
    b -->|"no"| fix
    c -->|"no"| fix
    c2 -->|"no"| fix
    c3 -->|"no"| fix
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
| Solenoid clicks at power-on | gate or buffer input floating at boot | 10 kΩ gate-to-ground and 10 kΩ from 2A to GND |
| Carriage moves 16 times too far | A4988 in full-step mode | MS1–MS3 tied to 3.3 V |
| Motor does not move at all | A4988 asleep or held in reset | SLEEP and RESET on 3.3 V; ENABLE low |
| MOSFET gets warm | gate under-driven | gate fed from the 74AHCT125 at 5 V, not from GPIO 32 directly |
| Emergency stop trips by itself | GPIO 35 floating | external 10 kΩ pull-up to 3.3 V |
| First LED wrong colour or flickers | 3.3 V data into a 5 V strip | level shifter; 1OE to GND; 330 Ω at DIN; short data wire |
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

## Checked against datasheets

The wiring above was checked against these documents (downloaded from the makers' own
sites, except the sensor sheet, which is a distributor's):

| Part | Source | What was checked |
|---|---|---|
| ESP32 | [ESP32 Series Datasheet](https://www.espressif.com/sites/default/files/documentation/esp32_datasheet_en.pdf) (Espressif) | GPIO 34–39 input-only with no pull-ups; strapping pins 0, 2, 5, 12, 15 (none used); input high ≥ 0.75 × VDD, low ≤ 0.25 × VDD, max VDD + 0.3 V; output high ≥ 0.8 × VDD |
| A4988 | [A4988 datasheet](https://www.allegromicro.com/-/media/files/datasheets/a4988-datasheet.pdf) (Allegro) | microstep table (all high = 1/16); MSx pull-downs; ENABLE active low; SLEEP and RESET; VDD 3–5.5 V; input high ≥ 0.7 × VDD; VBB 8–35 V; STEP ≥ 1 µs; I = VREF / (8 × Rs) |
| 74AHCT125 | [SN74AHCT125](https://www.ti.com/lit/ds/symlink/sn74ahct125.pdf) (Texas Instruments) | VCC 4.5–5.5 V; input high ≥ 2 V; OE active low; output ±25 mA; unused inputs tied |
| IRLZ44N | [IRLZ44NPbF](https://www.infineon.com/dgdl/irlz44npbf.pdf?fileId=5546d462533600a40153567217c32725) (Infineon) | Rds(on) given at VGS 10, 5 and 4 V only; threshold 1–2 V; VGS max ±16 V |
| WS2812B | [WS2812B](https://cdn-shop.adafruit.com/datasheets/WS2812B.pdf) (Worldsemi, hosted by Adafruit) | supply 3.5–5.3 V (absolute maximum); DIN high ≥ 0.7 × VDD; current per LED not given |
| 1N5819 | [1N5817–1N5819](https://www.onsemi.com/pdf/datasheet/1n5817-d.pdf) (onsemi) | 40 V reverse, 1 A average |
| LJ12A3-4-Z/BX | [distributor sheet](https://www.electrokit.com/upload/product/41014/41014825/LJ12A3-4.pdf) (Electrokit) | 6–36 V, NPN normally open, sink output, 4 mm range, wire colours; **output circuit not documented** |

**Not verified:**
- **TMC2209:** the maker's site refused automated downloads, so its standalone
  microstep-pin table was not checked. Sources found disagree. If you use one instead of
  the A4988, check its datasheet's MS1/MS2 table before relying on 80 steps per mm.
- **JF-1039B solenoid:** no manufacturer datasheet found. The ~0.4 A figure comes from
  seller listings.
- **Supply sizes** (12 V 3 A, 5 V 4 A) are estimates, not datasheet values.
- **Nothing has been built yet.** These checks are on paper; measure before connecting.
