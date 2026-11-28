// Rig constants the firmware needs. Musical facts (bottle positions, pitches) stay on
// the Hub; the device only needs what keeps the hardware safe.
#pragma once
#include <cstdint>

namespace duet {

struct Config {
  float steps_per_mm = 80.0f;         // GT2 belt, 20T pulley, 1/16 microstepping
  int32_t travel_steps = 48000;       // soft limit: 0 .. travel_steps
  int32_t homing_speed_steps_s = 4000;
  int64_t homing_timeout_us = 20000000;
  int64_t watchdog_us = 1000000;      // stop moving if the Hub is silent this long (FR-D6)
  int64_t duty_window_us = 10000000;  // solenoid on-time limit window (FR-R6)
  float duty_limit = 0.2f;
  int32_t max_pulse_us = 50000;
  int64_t late_tolerance_us = 5000;   // later than this counts as late (Stats::late)
};

}  // namespace duet
