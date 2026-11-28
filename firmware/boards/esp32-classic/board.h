// ESP32 DevKitC (ESP32-WROOM-32, 4 MB flash): the rig as wired in docs/rig-guide.md.
#pragma once
#include <cstdint>

#include "duet_channels.hpp"
#include "duet_features.hpp"
#include "rig.h"

#ifdef DUET_WOKWI
constexpr const char* BOARD = "wokwi";  // the same board, in the Wokwi simulator
#else
constexpr const char* BOARD = "esp32-classic";
#endif
constexpr uint32_t FEATURES =
    duet::kWifi | duet::kFlash | duet::kPlayButton | duet::kEstopButton | duet::kWeb |
    duet::kModules;  // + the optional modules this build installs

constexpr int PIN_STEP = 25;
constexpr int PIN_DIR = 26;
constexpr int PIN_ENABLE = 27;
constexpr int PIN_SOLENOID = 32;  // "In" of the Adafruit MOSFET Driver (#5648)
constexpr int PIN_HOME = 34;      // through the sensor's divider; input-only, no pull-up
constexpr int PIN_LEDS = 13;      // through the 74AHCT125 to the strip
constexpr int PIN_PLAY = 33;      // play button to GND; internal pull-up
constexpr int PIN_ESTOP = 35;     // e-stop button to GND; input-only, so an EXTERNAL
                                  // 10 kOhm pull-up to 3.3 V is required
constexpr bool ESTOP_NEEDS_EXTERNAL_PULLUP = true;

constexpr int PIN_MIDI_TX = 17;  // MIDI out, 31250 baud: UART2's TX; free on a WROOM-32 DevKitC (WROVER modules use it for PSRAM)

