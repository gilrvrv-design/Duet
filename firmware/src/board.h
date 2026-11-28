// Pin map and rig constants. Change these to match the wiring.
#pragma once
#include <cstdint>

constexpr int PIN_STEP = 25;
constexpr int PIN_DIR = 26;
constexpr int PIN_ENABLE = 27;
constexpr int PIN_SOLENOID = 32;  // "In" of the Adafruit MOSFET Driver (#5648) for the JF-1039B solenoid
constexpr int PIN_HOME = 34;      // LJ12A3 NPN sensor: open collector, 10 kOhm pull-up to 3.3 V
constexpr bool HOME_ACTIVE_LOW = true;
constexpr int PIN_LEDS = 13;
constexpr int PIN_ESTOP = 35;     // e-stop button to GND, active low; needs an EXTERNAL 10 kOhm
                                  // pull-up to 3.3 V (input-only pin, no internal pull-up)
constexpr int LED_COUNT = 176;    // 1.22 m of 144 LED/m strip over 88 keys
constexpr uint8_t LED_BRIGHTNESS = 80;  // keeps the 5 V supply within budget (FR-L5)

constexpr const char* DEVICE_ID = "duet-rig-1";
constexpr const char* PROFILE_ID = "bottles-v1";
constexpr uint16_t WS_PORT = 8765;
