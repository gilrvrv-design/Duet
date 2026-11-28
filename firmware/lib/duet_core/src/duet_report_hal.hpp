// Simulated hardware that reports what it does as console lines, for the builds that run
// without a rig (QEMU and the native device process). Tests read these lines:
//   # strike t_us=<device us> position=<steps>
//   # led t_us=<device us> first=<led> count=<n> rgb=<r>,<g>,<b>
// The carriage always arrives and the home sensor trips at the motor end: stubs that
// assume the hardware works, so the loop tests the logic, not the parts.
#pragma once
#include <cstdio>

#include "duet_sim_hal.hpp"

namespace duet {

class ReportingHal : public SimHal {
 public:
  using Out = void (*)(const char* line);
  explicit ReportingHal(Out out) : out_(out) {}

  void solenoid(bool on) override {
    if (!on) return;
    char line[80];
    std::snprintf(line, sizeof line, "# strike t_us=%lld position=%ld", (long long)now_us,
                  (long)position());
    out_(line);
  }
  void led_fill(int first, int count, uint8_t r, uint8_t g, uint8_t b) override {
    char line[96];
    std::snprintf(line, sizeof line, "# led t_us=%lld first=%d count=%d rgb=%u,%u,%u",
                  (long long)now_us, first, count, r, g, b);
    out_(line);
  }
  void led_clear() override {
    char line[48];
    std::snprintf(line, sizeof line, "# led clear t_us=%lld", (long long)now_us);
    out_(line);
  }

 private:
  Out out_;
};

}  // namespace duet
