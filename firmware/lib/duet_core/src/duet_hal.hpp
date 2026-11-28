// What the executor needs from the hardware. The ESP32 build implements it with real
// drivers; native tests implement it with a simulator.
#pragma once
#include <cstdint>

namespace duet {

class Hal {
 public:
  virtual ~Hal() = default;
  virtual void move_to(int32_t steps, float speed_steps_s, float accel_steps_s2) = 0;
  virtual void stop() = 0;  // stop the carriage now
  virtual bool is_moving() const = 0;
  virtual int32_t position() const = 0;          // current step count
  virtual void set_position(int32_t steps) = 0;  // after homing
  virtual bool home_sensor() const = 0;          // true at the motor end
  virtual void solenoid(bool on) = 0;
  virtual void led_fill(int first, int count, uint8_t r, uint8_t g, uint8_t b) = 0;
  virtual void led_show() = 0;
  virtual void led_clear() = 0;  // every LED off, shown at once
};

}  // namespace duet
