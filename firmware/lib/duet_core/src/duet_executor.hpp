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

struct Stats {  // for the contract CLI (tests/test_firmware_contract.py)
  uint32_t executed = 0;
  uint32_t late = 0;  // run later than Config::late_tolerance_us after their time
  uint32_t faults = 0;
};

class Executor {
 public:
  // ``channels``: what the board drives (board.h); timed commands must name one of them.
  Executor(Hal& hal, Sink& sink, Channels channels, Config config = Config{});

  void on_message(const char* json, int64_t now_us);  // parses it, then on_command
  void on_command(const Command& c, int64_t now_us);  // a message already parsed
  // Call instead of on_message when a frame or line was longer than kMaxMessage.
  void on_oversize(int64_t now_us);
  const Config& config() const { return cfg_; }
  void poll(int64_t now_us);  // call as often as possible (every loop iteration)

  // For commands that come from the device itself (playing a stored song) instead of
  // the Hub. Every safety rule still applies once a command is queued.
  bool submit(const Command& c);   // queue a timed command; false if refused
  bool accepts(const Command& c) const;  // a timed command for one of the board's channels
  void start_homing(int64_t now_us);
  void cancel();  // quiet, LEDs off, homing abandoned: a stopped song or performance
  void estop();   // quiet, and latched until power-off: nothing more plays
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
  void silence();  // MIDI out: All Notes Off on every MIDI channel, nothing sounding
  void quiet();    // nothing moving, struck or sounding, and nothing more queued
  bool sounding() const { return sounding_ > 0; }

  Hal& hal_;
  Sink& sink_;
  Channels channels_;
  Config cfg_;
  CommandQueue<kQueueSize> queue_;
  bool homed_ = false;
  bool homing_ = false;
  int64_t homing_started_us_ = 0;
  bool estopped_ = false;
  int64_t last_message_us_ = 0;
  int64_t pulse_end_us_ = -1;
  int32_t target_steps_ = 0;
  uint16_t notes_[128] = {};  // MIDI out: per pitch, a bit per MIDI channel sounding it
  uint32_t sounding_ = 0;     // how many notes are sounding
  int64_t duty_time_[kDutySlots] = {};
  int32_t duty_pulse_[kDutySlots] = {};
  size_t duty_next_ = 0;
  Stats stats_;
};

}  // namespace duet
