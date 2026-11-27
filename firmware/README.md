# Duet rig firmware (ESP32)

One ESP32 drives the robot (stepper carriage, solenoid striker, homing sensor) and the
pianist's LED strip (spec §5.10, §5.3, §5.4).

## Layout

| Path | What it is | Tested here |
|---|---|---|
| `lib/duet_core/` | Protocol parsing, time-ordered command queue, executor and safety rules. Plain C++17, no Arduino. | Yes: `make test` and the Hub's contract test |
| `test/native/` | Simulated hardware, unit tests, and `duet_core_cli` for the contract test | Yes |
| `src/main.cpp` | ESP32 glue: FastAccelStepper, NeoPixel, WebSocket server, mDNS, serial fallback | **Not compiled yet** (needs the ESP32 toolchain) |
| `src/board.h` | Pin map and rig constants | — |

## What the firmware guarantees

- Timed commands run in time order on the device's own clock; the Hub converts times.
- A strike only fires when the carriage has arrived where the last move sent it.
- Moves outside `0..travel_steps` are refused; nothing moves before homing.
- Solenoid on-time stays under 20% of any 10 s window.
- If the Hub is silent for 1 s while the carriage moves, it stops and asks to re-home.
  The Hub's gateway sends a heartbeat every 250 ms, so this only fires when the link is lost.
- Emergency stop (button or message) latches until power is cycled.

## Build

Native tests (any machine with g++):

```bash
make -C firmware test
```

ESP32 (needs [PlatformIO](https://platformio.org)); copy `src/secrets.example.h` to `src/secrets.h` first:

```bash
cd firmware && pio run -t upload
```

Then, on the Hub:

```bash
duet play examples/rain-on-the-bottles.json --device ws://duet-rig-1.local:8765
```
