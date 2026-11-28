// The serial link on the ESP32: one JSON message per line, in both directions. The rig
// uses it as a fallback to Wi-Fi; the QEMU build uses nothing else.
#pragma once
#include <Arduino.h>

#include "duet_line_reader.hpp"

// Read whatever has arrived and hand each complete line to the executor.
inline void read_serial(duet::Executor& executor, int64_t now_us) {
  static duet::LineReader reader;
  while (Serial.available()) reader.feed(static_cast<char>(Serial.read()), executor, now_us);
}
