// The serial link: one JSON message per line, in both directions. The rig uses it as a
// fallback to Wi-Fi; the QEMU build uses nothing else.
#pragma once
#include <Arduino.h>

#include "duet_executor.hpp"

// Read whatever has arrived; hand each complete line to the executor. A line longer
// than a message can be is read to its end and refused whole, never acted on in part.
inline void read_serial(duet::Executor& executor, int64_t now_us) {
  static char line[duet::kMaxMessage + 1];
  static size_t len = 0;
  static bool too_long = false;
  while (Serial.available()) {
    char c = static_cast<char>(Serial.read());
    if (c == '\n') {
      line[len] = '\0';
      if (too_long) {
        executor.on_oversize(now_us);
      } else if (len) {
        executor.on_message(line, now_us);
      }
      len = 0;
      too_long = false;
    } else if (c == '\r' || too_long) {
      continue;
    } else if (len == duet::kMaxMessage) {
      too_long = true;
    } else {
      line[len++] = c;
    }
  }
}
