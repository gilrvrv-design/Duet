# Duet rig firmware (ESP32)

One ESP32 drives the robot (stepper carriage, solenoid striker, homing sensor) and the
pianist's LED strip (spec §5.10, §5.3, §5.4). It can also play stored songs on its own.

## Layout

| Path | What it is | Tested here |
|---|---|---|
| `lib/duet_core/` | Protocol, time-ordered command queue, executor and safety rules, stored songs (`Device`). Plain C++17, no Arduino, no board | `make test`, the Hub's contract tests and the full loop |
| `boards/<board>/board.h` | One folder per board: pins, the board's name, the features it compiles in | every board builds (`pio run`), also in CI |
| `src/rig.h` | The rig, whatever board drives it: identity, LED strip, home sensor, port | — |
| `src/main.cpp` | Board glue: FastAccelStepper, NeoPixel, WebSocket server, mDNS, serial, flash songs, buttons | compiled for every hardware board |
| `src/main_qemu.cpp` | The core in Espressif's QEMU emulator, with stubbed hardware (QEMU.md) | compiled; run by the full loop when QEMU is installed |
| `host/duet_device.cpp` | The core as a Linux process, with stubbed hardware: the full-loop tests' device | the full loop, in `make check` |
| `test/native/` | Unit tests, and `duet_core_cli` for the contract tests | `make test` |

## Boards

| Board (`pio run -e …`) | Hardware | Features |
|---|---|---|
| `esp32-classic` | ESP32 DevKitC, 4 MB flash: the rig as wired in the rig guide | wifi, flash, play_button, estop_button |
| `esp32-s3` | ESP32-S3-DevKitC-1 N16R8: 16 MB flash, 8 MB PSRAM (pins in the rig guide) | wifi, flash, play_button, estop_button |
| `wokwi` | `esp32-classic` in the Wokwi simulator (WOKWI.md) | as `esp32-classic` |
| `qemu` | Espressif's QEMU emulator (QEMU.md) | none beyond the core |
| native (`make -C firmware device`) | a Linux process, for tests | play_button (`press` on stdin) |

Every board has the core: the executor and its safety rules, the serial link, and songs
(in RAM without flash storage). The device names its board and features in `hello`
(docs/device-protocol.md); the Hub and the app decide from those. The feature list lives
in `lib/duet_core/src/duet_features.hpp` and, for the Hub, `duet.device.features`; a
contract test keeps them in step.

**Adding a board:** a `boards/<name>/board.h` with `BOARD`, `FEATURES` and the pins, and
a `[env:<name>]` in `platformio.ini` that adds `-Iboards/<name>`. Declare only features
the code has; add the board to the CI matrix (`.github/workflows/ci.yml`).

## What the firmware guarantees

- Timed commands run in time order on the device's own clock; the Hub converts times.
- A strike only fires when the carriage has arrived where the last move sent it.
- Moves outside `0..travel_steps` are refused; nothing moves before homing.
- Solenoid on-time stays under 20% of any 10 s window.
- If the Hub is silent for 1 s while the carriage moves, it stops and asks to re-home.
  The Hub's gateway sends a heartbeat every 250 ms, so this only fires when the link is lost.
- Emergency stop (button or message) latches until power is cycled.
- A stored song plays through the same queue and rules, from home.

## Build

Native tests (any machine with g++):

```bash
make -C firmware test
```

A board (needs [PlatformIO](https://platformio.org)); for the boards with Wi-Fi, copy
`src/secrets.example.h` to `src/secrets.h` first:

```bash
cd firmware && pio run -e esp32-classic -t upload
```

The rig's page is then at `http://duet-rig-1.local` (docs/device-api.md). On the Hub:

```bash
duet play examples/rain-on-the-bottles.json --device ws://duet-rig-1.local:8765
```
