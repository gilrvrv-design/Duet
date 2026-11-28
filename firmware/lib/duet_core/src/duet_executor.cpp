#include "duet_executor.hpp"

#include <cstdio>

namespace duet {

Executor::Executor(Hal& hal, Sink& sink, Channels channels, Config config)
    : hal_(hal), sink_(sink), channels_(channels), cfg_(config) {
  for (size_t i = 0; i < kDutySlots; ++i) duty_time_[i] = INT64_MIN / 2;
}

void Executor::ack(int64_t seq, const char* status) {
  char buf[kMaxMessage + 1];
  write_ack(buf, sizeof buf, seq, status);
  sink_.send(buf);
}

void Executor::fault(const char* code, const char* detail) {
  char buf[192];
  write_fault(buf, sizeof buf, code, detail);
  sink_.send(buf);
  ++stats_.faults;
}

void Executor::report() {
  char buf[128];
  write_telemetry(buf, sizeof buf, homed_, hal_.position(), queue_.size());
  sink_.send(buf);
}

void Executor::finish_homing() {
  hal_.stop();
  hal_.set_position(0);
  homing_ = false;
  homed_ = true;
  target_steps_ = 0;
  report();
}

void Executor::on_oversize(int64_t now_us) {
  last_message_us_ = now_us;
  ack(0, "error: message too long");  // the seq is unknown: the frame was cut
}

void Executor::on_message(const char* json, int64_t now_us) {
  Command c;
  if (!parse(json, c)) {
    last_message_us_ = now_us;
    ack(c.seq, "error: cannot parse");
    return;
  }
  on_command(c, now_us);
}

void Executor::on_command(const Command& c, int64_t now_us) {
  last_message_us_ = now_us;
  switch (c.type) {
    case Type::Heartbeat:
      return;  // last_message_us_ is already updated
    case Type::TimePing: {
      char buf[128];
      write_pong(buf, sizeof buf, c.seq, c.t1, now_us, now_us);
      sink_.send(buf);
      return;
    }
    case Type::Estop:
      estop();
      ack(c.seq, "ok");
      return;
    default:
      break;
  }
  if (estopped_) {
    ack(c.seq, "error: emergency stop");
    return;
  }
  if (c.type == Type::Home) {
    ack(c.seq, "ok");
    start_homing(now_us);
    return;
  }
  if (!c.timed()) {  // song, play and stop are handled by duet::Device, not here
    ack(c.seq, "error: not supported");
    return;
  }
  if (!accepts(c)) {
    ack(c.seq, "error: no such channel");
    return;
  }
  if (!queue_.push(c)) {
    ack(c.seq, "error: queue full");
    return;
  }
  ack(c.seq, "ok");
}

void Executor::start_homing(int64_t now_us) {
  queue_.clear();
  homed_ = false;
  homing_ = true;
  homing_started_us_ = now_us;
  if (hal_.home_sensor()) {
    finish_homing();
  } else {
    hal_.move_to(-cfg_.travel_steps * 2, cfg_.homing_speed_steps_s,
                 cfg_.homing_speed_steps_s * 4.0f);
  }
}

bool Executor::accepts(const Command& c) const {
  return c.timed() && channels_.has(c.ch, c.channel_kind());
}

bool Executor::submit(const Command& c) {
  if (estopped_ || !accepts(c)) return false;
  return queue_.push(c);
}

void Executor::quiet() {
  queue_.clear();
  hal_.stop();
  hal_.solenoid(false);
  pulse_end_us_ = -1;
  silence();
}

void Executor::cancel() {
  quiet();
  hal_.led_clear();  // a stopped song must not leave a key lit
  homing_ = false;
}

void Executor::estop() {
  estopped_ = true;  // latched until power cycle: safety first
  quiet();
}

void Executor::keepalive(int64_t now_us) { last_message_us_ = now_us; }

void Executor::silence() {
  if (!channels_.any(ChannelKind::MidiOut)) return;  // no MIDI port: nothing to silence
  for (uint8_t ch = 0; ch < 16; ++ch) hal_.midi(static_cast<uint8_t>(0xB0 | ch), 123, 0);
  for (uint16_t& n : notes_) n = 0;
  sounding_ = 0;
}

void Executor::poll(int64_t now_us) {
  if (pulse_end_us_ >= 0 && now_us >= pulse_end_us_) {
    hal_.solenoid(false);
    pulse_end_us_ = -1;
  }
  if (estopped_) return;
  if (homing_) {
    if (hal_.home_sensor()) {
      finish_homing();
    } else if (now_us - homing_started_us_ > cfg_.homing_timeout_us) {
      hal_.stop();
      homing_ = false;
      fault("HOMING_TIMEOUT", "home sensor never triggered");
    }
    return;
  }
  if ((hal_.is_moving() || sounding()) && now_us - last_message_us_ > cfg_.watchdog_us) {
    quiet();
    homed_ = false;  // position is no longer trusted
    fault("WATCHDOG", "hub silent while playing");
    report();
    return;
  }
  while (!queue_.empty() && queue_.top().t_us <= now_us) {
    Command c = queue_.pop();
    int64_t late = now_us - c.t_us;
    if (late > cfg_.late_tolerance_us) ++stats_.late;
    run(c, now_us);
  }
}

void Executor::run(const Command& c, int64_t now_us) {
  ++stats_.executed;
  switch (c.type) {
    case Type::MoveAt:
      move(c);
      break;
    case Type::StrikeAt:
      strike(c, now_us);
      break;
    case Type::LedFrameAt:
      hal_.led_fill(c.first, c.count, c.rgb[0], c.rgb[1], c.rgb[2]);
      hal_.led_show();
      break;
    case Type::NoteAt: {  // note on, or off (velocity 0): no carriage, no homing needed
      uint16_t bit = static_cast<uint16_t>(1u << c.midi);
      bool was = notes_[c.pitch] & bit;
      if (c.vel && !was) ++sounding_;
      if (!c.vel && was) --sounding_;
      notes_[c.pitch] = c.vel ? (notes_[c.pitch] | bit) : (notes_[c.pitch] & ~bit);
      hal_.midi(static_cast<uint8_t>((c.vel ? 0x90 : 0x80) | c.midi), c.pitch, c.vel);
      break;
    }
    default:
      break;
  }
}

void Executor::move(const Command& c) {
  if (!homed_) {
    fault("NOT_HOMED", "move before homing");
    return;
  }
  if (c.target_steps < 0 || c.target_steps > cfg_.travel_steps) {
    fault("SOFT_LIMIT", "target outside travel");
    return;
  }
  if (hal_.is_moving()) {
    fault("MOVE_OVERLAP", "move started before the last one ended");
  }
  target_steps_ = c.target_steps;
  hal_.move_to(c.target_steps, c.v_max_mm_s * cfg_.steps_per_mm, c.a_max_mm_s2 * cfg_.steps_per_mm);
}

void Executor::strike(const Command& c, int64_t now_us) {
  if (!homed_) {
    fault("NOT_HOMED", "strike before homing");
    return;
  }
  if (hal_.is_moving() || hal_.position() != target_steps_) {
    fault("NOT_ARRIVED", "strike before the carriage arrived");
    return;
  }
  int32_t pulse = c.pulse_us > cfg_.max_pulse_us ? cfg_.max_pulse_us : c.pulse_us;
  if (pulse <= 0) return;
  if (!duty_allows(pulse, now_us)) {
    fault("DUTY_CYCLE", "solenoid duty limit reached");
    return;
  }
  hal_.solenoid(true);
  pulse_end_us_ = now_us + pulse;
}

bool Executor::duty_allows(int32_t pulse_us, int64_t now_us) {
  // The history holds kDutySlots strikes. If the slot we would overwrite is still inside
  // the window, older strikes there are no longer counted, so refuse: never undercount.
  if (now_us - duty_time_[duty_next_] < cfg_.duty_window_us) return false;
  int64_t on = pulse_us;
  for (size_t i = 0; i < kDutySlots; ++i) {
    if (now_us - duty_time_[i] < cfg_.duty_window_us) on += duty_pulse_[i];
  }
  if (on > static_cast<int64_t>(cfg_.duty_limit * cfg_.duty_window_us)) return false;
  duty_time_[duty_next_] = now_us;  // ring buffer of recent strikes
  duty_pulse_[duty_next_] = pulse_us;
  duty_next_ = (duty_next_ + 1) % kDutySlots;
  return true;
}

}  // namespace duet
