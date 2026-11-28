// The rig, whatever board drives it: identity, the LED strip, the home sensor, the link.
#pragma once
#include <cstdint>

#include "duet_channels.hpp"

constexpr const char* DEVICE_ID = "duet-rig-1";
constexpr const char* PROFILE_ID = "bottles-v1";  // the instrument its carriage plays
constexpr const char* KEYBOARD_ID = "piano-88";   // the keyboard under its LED strip
constexpr uint16_t WS_PORT = 8765;   // the Hub's link
constexpr uint16_t HTTP_PORT = 80;  // the web app and device API
constexpr const char* SETUP_SSID = "Duet-setup";  // open; up only while no Wi-Fi is joined
constexpr uint32_t JOIN_TIMEOUT_MS = 20000;       // then the setup network opens too
constexpr bool HOME_ACTIVE_LOW = true;  // LJ12A3 NPN sensor: low when it sees the carriage
constexpr int LED_COUNT = 176;          // 1.22 m of 144 LED/m strip over 88 keys
constexpr uint8_t LED_BRIGHTNESS = 80;  // keeps the 5 V supply within budget (FR-L5)
constexpr uint32_t PLAY_DEBOUNCE_MS = 30;

// What the rig drives, one channel each, whatever board drives it (docs/device-protocol.md):
// 0 the carriage and its striker, 1 the LED strip over the keys, 2 MIDI out.
constexpr duet::Channel RIG_CHANNELS[] = {
    {duet::ChannelKind::CarriageStriker, 0},
    {duet::ChannelKind::LedStrip, LED_COUNT},
    {duet::ChannelKind::MidiOut, 0},
};
static_assert(duet::at_most_one_carriage(RIG_CHANNELS), "one carriage per rig");
constexpr duet::Channels BOARD_CHANNELS{RIG_CHANNELS, sizeof RIG_CHANNELS / sizeof RIG_CHANNELS[0]};
