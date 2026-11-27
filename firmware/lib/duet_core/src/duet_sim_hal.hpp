// A simulated carriage, solenoid and LED strip: for the native tests, and as the hardware
// of the QEMU build (src/main_qemu.cpp). Motion uses the same
// trapezoidal model as the Hub (duet.kinematics), so both sides agree on timing.
#pragma once
#include <cmath>
#include <cstdint>
#include <vector>

#include "duet_hal.hpp"

namespace duet {

struct SimEvent {
  const char* kind;  // "strike" or "led"
  int64_t t_us;
  int32_t a;  // strike: position; led: first
  int32_t b;  // led: count
};

class SimHal : public Hal {
 public:
  int64_t now_us = 0;
  int32_t start_position = 0;
  std::vector<SimEvent> events;

  void move_to(int32_t steps, float v, float a) override {
    from_ = position();
    to_ = steps;
    depart_ = now_us;
    double d = std::fabs(static_cast<double>(to_ - from_));
    double t = d <= v * v / a ? 2.0 * std::sqrt(d / a) : d / v + v / a;
    arrive_ = now_us + static_cast<int64_t>(t * 1e6);
  }
  void stop() override {
    from_ = to_ = position();
    arrive_ = now_us;
  }
  bool is_moving() const override { return now_us < arrive_; }
  int32_t position() const override {
    if (!is_moving()) return to_;
    double f = static_cast<double>(now_us - depart_) / static_cast<double>(arrive_ - depart_);
    return from_ + static_cast<int32_t>((to_ - from_) * f);
  }
  void set_position(int32_t s) override { from_ = to_ = s; }
  bool home_sensor() const override { return position() <= 0; }  // the motor end
  void solenoid(bool on) override {
    if (on) events.push_back({"strike", now_us, position(), 0});
  }
  void led_fill(int first, int count, uint8_t, uint8_t, uint8_t) override {
    events.push_back({"led", now_us, first, count});
  }
  void led_show() override {}

  void place(int32_t s) { from_ = to_ = s; }

 private:
  int32_t from_ = 0, to_ = 0;
  int64_t depart_ = 0, arrive_ = 0;
};

}  // namespace duet
