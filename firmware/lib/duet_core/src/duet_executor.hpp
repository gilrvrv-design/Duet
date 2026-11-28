// The device's brain (spec §5.10, FR-R5, FR-R6, FR-D6): queue timed commands, run them
// on time, and keep the hardware safe whatever the Hub sends.
#pragma once
#include <cstddef>
#include <cstdint>

#include "duet_config.hpp"
#include "duet_hal.hpp"
#include "duet_protocol.hpp"
#include "duet_queue.hpp"

namespace duet {

constexpr size_t kQueueSize = 512;  // more than 2 s of a dense piece
constexpr size_t kDutySlots = 256;  // strike history; when full inside the window, refuse

// Where replies (acks, pongs, faults) go: a WebSocket, a serial port or a test buffer.
class Sink {
 public:
  virtual ~Sink() = default;
  virtual void send(const char* json) = 0;
};

struct Stats {
  uint32_t executed = 0;
  uint32_t late = 0;
  int64_t worst_late_us = 0;
  uint32_t faults = 0;
};

class Executor {
 public:
  Executor(Hal& hal, Sink& sink, Config config = Config{});

  void on_message(const char* json, int64_t now_us);
  // Call instead of on_message when a frame or line was longer than kMaxMessage.
  void on_oversize(int64_t now_us);
  const Config& config() const { return cfg_; }
  void poll(int64_t now_us);  // call as often as possible (every loop iteration)

  // For commands that come from the device itself (playing a stored song) instead of
  // the Hub. Every safety rule still applies once a command is queued.
  bool submit(const Command& c);   // queue a timed command; false if refused
  void start_homing(int64_t now_us);
  void cancel();                   // drop the queue, stop the carriage and the solenoid
  void keepalive(int64_t now_us);  // the device is its own conductor: no watchdog stop

  bool homed() const { return homed_; }
  bool homing() const { return homing_; }
  // Nothing queued and nothing running: no move, no homing, no solenoid pulse.
  bool at_rest() const {
    return queue_.empty() && !homing_ && !hal_.is_moving() && pulse_end_us_ < 0;
  }
  bool estopped() const { return estopped_; }
  size_t queued() const { return queue_.size(); }
  const Stats& stats() const { return stats_; }

 private:
  void run(const Command& c, int64_t now_us);
  void strike(const Command& c, int64_t now_us);
  void move(const Command& c);
  bool duty_allows(int32_t pulse_us, int64_t now_us);
  void fault(const char* code, const char* detail);
  void ack(int64_t seq, const char* status);
  void report();  // telemetry: homed, position, queue depth
  void finish_homing();

  Hal& hal_;
  Sink& sink_;
  Config cfg_;
  CommandQueue<kQueueSize> queue_;
  bool homed_ = false;
  bool homing_ = false;
  int64_t homing_started_us_ = 0;
  bool estopped_ = false;
  int64_t last_message_us_ = 0;
  int64_t pulse_end_us_ = -1;
  int32_t target_steps_ = 0;
  int64_t duty_time_[kDutySlots] = {};
  int32_t duty_pulse_[kDutySlots] = {};
  size_t duty_next_ = 0;
  Stats stats_;
};

}  // namespace duet
