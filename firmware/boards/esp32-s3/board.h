// ESP32-S3-DevKitC-1 N16R8 (16 MB flash, 8 MB octal PSRAM).
// Not usable here (Espressif's user guide): GPIO 35-37 (octal PSRAM), 38 (on-board RGB
// LED), 19-20 (USB, kept free for a MIDI keyboard), 43-44 (UART0, the serial link);
// strapping pins 0, 3, 45, 46 are avoided.
#pragma once
#include <cstdint>

#include "duet_channels.hpp"
#include "duet_features.hpp"
#include "rig.h"

constexpr const char* BOARD = "esp32-s3";
constexpr uint32_t FEATURES =
    duet::kWifi | duet::kFlash | duet::kPlayButton | duet::kEstopButton | duet::kWeb |
    duet::kModules;  // + the optional modules this build installs

constexpr int PIN_STEP = 4;
constexpr int PIN_DIR = 5;
constexpr int PIN_ENABLE = 6;
constexpr int PIN_SOLENOID = 7;
constexpr int PIN_HOME = 15;
constexpr int PIN_LEDS = 18;
constexpr int PIN_PLAY = 17;   // play button to GND; internal pull-up
constexpr int PIN_ESTOP = 16;  // e-stop button to GND; every S3 GPIO has an internal pull-up
constexpr bool ESTOP_NEEDS_EXTERNAL_PULLUP = false;

constexpr int PIN_MIDI_TX = 8;  // MIDI out, 31250 baud: free on the DevKitC-1, not a strapping pin

