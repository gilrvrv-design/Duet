#include "duet_executor.hpp"

#include <cstdio>

namespace duet {

Executor::Executor(Hal& hal, Sink& sink, Config config) : hal_(hal), sink_(sink), cfg_(config) {
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
  last_message_us_ = now_us;
  Command c;
  if (!parse(json, c)) {
    ack(c.seq, "error: cannot parse");
    return;
  }
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
      estopped_ = true;  // latched until power cycle: safety first
      hal_.stop();
      hal_.solenoid(false);
      queue_.clear();
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
    queue_.clear();
    homed_ = false;
    homing_ = true;
    homing_started_us_ = now_us;
    ack(c.seq, "ok");
    if (hal_.home_sensor()) {
      finish_homing();
    } else {
      hal_.move_to(-cfg_.travel_steps * 2, cfg_.homing_speed_steps_s,
                   cfg_.homing_speed_steps_s * 4.0f);
    }
    return;
  }
  if (!queue_.push(c)) {
    ack(c.seq, "error: queue full");
    return;
  }
  ack(c.seq, "ok");
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
  if (hal_.is_moving() && now_us - last_message_us_ > cfg_.watchdog_us) {
    hal_.stop();
    queue_.clear();
    homed_ = false;  // position is no longer trusted
    fault("WATCHDOG", "hub silent while moving");
    report();
    return;
  }
  while (!queue_.empty() && queue_.top().t_us <= now_us) {
    Command c = queue_.pop();
    int64_t late = now_us - c.t_us;
    if (late > cfg_.late_tolerance_us) {
      ++stats_.late;
      if (late > stats_.worst_late_us) stats_.worst_late_us = late;
    }
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
