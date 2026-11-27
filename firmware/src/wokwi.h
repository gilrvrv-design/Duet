// Settings for the Wokwi simulator build (pio run -e wokwi). See firmware/WOKWI.md.
#pragma once
#include <cstdint>

// Wokwi's virtual access point: open, on channel 6 (docs.wokwi.com/guides/esp32-wifi).
constexpr const char* WIFI_SSID = "Wokwi-GUEST";
constexpr const char* WIFI_PASSWORD = "";
constexpr int32_t WIFI_CHANNEL = 6;

// Where the simulated carriage is at power-on, in steps from the home end. Homing at
// 4000 steps/s takes about a second.
constexpr int32_t WOKWI_START_STEPS = 4000;
