// The firmware as a Linux process (host/duet_device.cpp), for tests: stubbed hardware,
// the serial link over TCP, songs in RAM, and "press" on stdin as the play button.
#pragma once
#include <cstdint>

#include "duet_features.hpp"

constexpr const char* BOARD = "native";
constexpr uint32_t FEATURES = duet::kPlayButton;
