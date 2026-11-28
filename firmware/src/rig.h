// The rig, whatever board drives it: identity, the LED strip, the home sensor, the link.
#pragma once
#include <cstdint>

constexpr const char* DEVICE_ID = "duet-rig-1";
constexpr const char* PROFILE_ID = "bottles-v1";
constexpr uint16_t WS_PORT = 8765;   // the Hub's link
constexpr uint16_t HTTP_PORT = 80;  // the web app and device API
constexpr bool HOME_ACTIVE_LOW = true;  // LJ12A3 NPN sensor: low when it sees the carriage
constexpr int LED_COUNT = 176;          // 1.22 m of 144 LED/m strip over 88 keys
constexpr uint8_t LED_BRIGHTNESS = 80;  // keeps the 5 V supply within budget (FR-L5)
constexpr uint32_t PLAY_DEBOUNCE_MS = 30;
