// The serial link's framing: one JSON message per line. Shared by the rig (as a fallback
// to Wi-Fi), the QEMU build and the native device process, so all three frame alike.
#pragma once
#include <cstddef>
#include <cstdint>

#include "duet_executor.hpp"

namespace duet {

class LineReader {
 public:
  // Feed one received character. A complete line goes to the executor; a line longer
  // than a message can be is read to its end and refused whole, never acted on in part.
  void feed(char c, Executor& executor, int64_t now_us) {
    if (c == '\n') {
      line_[len_] = '\0';
      if (too_long_) {
        executor.on_oversize(now_us);
      } else if (len_) {
        executor.on_message(line_, now_us);
      }
      len_ = 0;
      too_long_ = false;
    } else if (c == '\r' || too_long_) {
      return;
    } else if (len_ == kMaxMessage) {
      too_long_ = true;
    } else {
      line_[len_++] = c;
    }
  }

 private:
  char line_[kMaxMessage + 1] = {};
  size_t len_ = 0;
  bool too_long_ = false;
};

}  // namespace duet
