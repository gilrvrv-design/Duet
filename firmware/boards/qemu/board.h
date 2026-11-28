// Espressif's QEMU ESP32 emulator: the core on the chip's CPU, clock and serial port,
// with stubbed hardware (src/main_qemu.cpp). No Wi-Fi, no flash storage, no buttons.
#pragma once
#include <cstdint>

#include "duet_features.hpp"

constexpr const char* BOARD = "qemu";
constexpr uint32_t FEATURES = 0;
