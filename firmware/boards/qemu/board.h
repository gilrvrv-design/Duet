// Espressif's QEMU ESP32 emulator: the core on the chip's CPU, clock and serial port,
// with stubbed hardware (src/main_qemu.cpp). No Wi-Fi, no flash storage, no buttons.
#pragma once
#include <cstdint>

#include "duet_channels.hpp"
#include "duet_features.hpp"
#include "rig.h"

constexpr const char* BOARD = "qemu";
constexpr uint32_t FEATURES = 0;

// Channel 0: the carriage and its striker; 1: the LED strip over the keys; 2: MIDI out.
constexpr duet::Channel CHANNELS[] = {
    {duet::ChannelKind::CarriageStriker, 0},
    {duet::ChannelKind::LedStrip, LED_COUNT},
    {duet::ChannelKind::MidiOut, 0},
};
static_assert(duet::at_most_one_carriage(CHANNELS), "one carriage per board");
constexpr duet::Channels BOARD_CHANNELS{CHANNELS, sizeof CHANNELS / sizeof CHANNELS[0]};
