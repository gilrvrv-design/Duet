// Native unit tests for the firmware core. Build and run: make -C firmware test
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "duet_executor.hpp"
#include "duet_protocol.hpp"
#include "duet_queue.hpp"
#include "sim_hal.hpp"

using namespace duet;

static int failures = 0;
#define CHECK(cond)                                                    \
  do {                                                                 \
    if (!(cond)) {                                                     \
      std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);      \
      ++failures;                                                      \
    }                                                                  \
  } while (0)

struct Capture : Sink {
  std::vector<std::string> sent;
  void send(const char* json) override { sent.emplace_back(json); }
  bool has(const char* text) const {
    for (auto& s : sent)
      if (s.find(text) != std::string::npos) return true;
    return false;
  }
};

static void test_parse() {
  Command c;
  CHECK(parse(R"({"type":"move_at","seq":3,"t_us":1500,"target_steps":6400,"v_max_mm_s":500.0,"a_max_mm_s2":5000.0})", c));
  CHECK(c.type == Type::MoveAt && c.seq == 3 && c.t_us == 1500 && c.target_steps == 6400);
  CHECK(c.v_max_mm_s == 500.0f && c.a_max_mm_s2 == 5000.0f);
  CHECK(parse(R"({"type":"led_frame_at","seq":4,"t_us":9,"first":10,"count":2,"rgb":[255,40,0]})", c));
  CHECK(c.type == Type::LedFrameAt && c.first == 10 && c.count == 2 && c.rgb[0] == 255 && c.rgb[1] == 40);
  CHECK(parse(R"({"type":"strike_at","seq":5,"t_us":123456789012,"pulse_us":20000})", c));
  CHECK(c.t_us == 123456789012LL && c.pulse_us == 20000);
  CHECK(parse(R"({"type":"time_ping","seq":7,"t1":42})", c) && c.t1 == 42);
  CHECK(parse(R"({"type":"heartbeat","seq":0})", c) && c.type == Type::Heartbeat);
  CHECK(!parse(R"({"type":"dance"})", c));
  CHECK(!parse(R"({"type":"strike_at","seq":1})", c));  // missing fields
  CHECK(!parse(R"({"type":"led_frame_at","t_us":1,"first":0,"count":1,"rgb":[300,0,0]})", c));
}

static void test_queue_orders_by_time() {
  CommandQueue<8> q;
  int64_t times[] = {50, 10, 30, 10, 20};
  for (int i = 0; i < 5; ++i) {
    Command c;
    c.t_us = times[i];
    c.seq = i;
    CHECK(q.push(c));
  }
  int64_t prev_t = -1, prev_seq = -1;
  while (!q.empty()) {
    Command c = q.pop();
    CHECK(c.t_us > prev_t || (c.t_us == prev_t && c.seq > prev_seq));
    prev_t = c.t_us;
    prev_seq = c.seq;
  }
  CommandQueue<2> small;
  Command c;
  CHECK(small.push(c) && small.push(c) && !small.push(c));
}

static void run_until(Executor& ex, SimHal& hal, int64_t end_us) {
  for (; hal.now_us <= end_us; hal.now_us += 100) ex.poll(hal.now_us);
}

static void test_home_move_strike() {
  SimHal hal;
  hal.place(5000);
  Capture out;
  Executor ex(hal, out);
  ex.on_message(R"({"type":"home","seq":1})", 0);
  CHECK(!ex.homed());
  run_until(ex, hal, 3000000);
  CHECK(ex.homed() && hal.position() == 0);
  CHECK(out.has(R"({"type":"telemetry","seq":0,"homed":true,"position":0,"queued":0})"));
  int64_t t0 = hal.now_us;
  char msg[200];
  std::snprintf(msg, sizeof msg, R"({"type":"move_at","seq":2,"t_us":%lld,"target_steps":6400,"v_max_mm_s":500,"a_max_mm_s2":5000})", (long long)(t0 + 1000));
  ex.on_message(msg, t0);
  std::snprintf(msg, sizeof msg, R"({"type":"strike_at","seq":3,"t_us":%lld,"pulse_us":20000})", (long long)(t0 + 400000));
  ex.on_message(msg, t0);
  CHECK(out.has(R"("seq":2,"status":"ok")") && out.has(R"("seq":3,"status":"ok")"));
  run_until(ex, hal, t0 + 500000);
  CHECK(hal.events.size() == 1 && hal.events[0].a == 6400);
  CHECK(hal.events[0].t_us >= t0 + 400000 && hal.events[0].t_us < t0 + 400200);
  CHECK(ex.stats().faults == 0);
}

static void test_strike_before_arrival_is_refused() {
  SimHal hal;
  Capture out;
  Executor ex(hal, out);
  ex.on_message(R"({"type":"home","seq":1})", 0);
  ex.on_message(R"({"type":"move_at","seq":2,"t_us":1000,"target_steps":46000,"v_max_mm_s":500,"a_max_mm_s2":5000})", 0);
  ex.on_message(R"({"type":"strike_at","seq":3,"t_us":200000,"pulse_us":20000})", 0);
  run_until(ex, hal, 300000);
  CHECK(out.has("NOT_ARRIVED"));
  CHECK(hal.events.empty());
}

static void test_safety_rules() {
  SimHal hal;
  Capture out;
  Executor ex(hal, out);
  ex.on_message(R"({"type":"strike_at","seq":1,"t_us":10,"pulse_us":20000})", 0);
  run_until(ex, hal, 1000);
  CHECK(out.has("NOT_HOMED"));

  ex.on_message(R"({"type":"home","seq":2})", hal.now_us);
  ex.on_message(R"({"type":"move_at","seq":3,"t_us":2000,"target_steps":99999,"v_max_mm_s":500,"a_max_mm_s2":5000})", hal.now_us);
  run_until(ex, hal, 3000);
  CHECK(out.has("SOFT_LIMIT"));

  // Watchdog: a long move, then silence from the Hub.
  ex.on_message(R"({"type":"move_at","seq":4,"t_us":4000,"target_steps":46000,"v_max_mm_s":20,"a_max_mm_s2":5000})", hal.now_us);
  run_until(ex, hal, 1200000);
  CHECK(out.has("WATCHDOG") && !hal.is_moving() && !ex.homed());

  // Emergency stop latches and refuses new commands.
  ex.on_message(R"({"type":"estop","seq":5})", hal.now_us);
  ex.on_message(R"({"type":"home","seq":6})", hal.now_us);
  CHECK(ex.estopped() && out.has(R"("seq":6,"status":"error: emergency stop")"));
  ex.on_message("garbage", hal.now_us);
  CHECK(out.has("cannot parse"));
}

static void test_duty_cycle_limit() {
  SimHal hal;
  Capture out;
  Executor ex(hal, out);
  ex.on_message(R"({"type":"home","seq":1})", 0);
  char msg[160];
  // 50 ms pulses every 100 ms = 50% duty; the limit is 20% over 10 s (2 s on).
  for (int i = 0; i < 60; ++i) {
    std::snprintf(msg, sizeof msg, R"({"type":"strike_at","seq":%d,"t_us":%d,"pulse_us":50000})", i + 2, 1000 + i * 100000);
    ex.on_message(msg, hal.now_us);
  }
  for (; hal.now_us <= 6100000; hal.now_us += 100) {
    if (hal.now_us % 500000 == 0) ex.on_message(R"({"type":"time_ping","seq":0,"t1":0})", hal.now_us);
    ex.poll(hal.now_us);
  }
  CHECK(hal.events.size() == 40);  // 40 * 50 ms = 2 s
  CHECK(out.has("DUTY_CYCLE"));
}

static void test_duty_cannot_be_bypassed_with_short_pulses() {
  // Review finding: 1000 strikes of 5 ms, 10 ms apart, is 50% on-time. With a history of
  // only 256 strikes, the old check forgot the oldest strikes and let all of them fire.
  SimHal hal;
  Capture out;
  Executor ex(hal, out);
  ex.on_message(R"({"type":"home","seq":1})", 0);
  char msg[160];
  int64_t fired_on_us = 0;
  for (int i = 0; i < 1000; ++i) {
    int64_t t = 1000 + i * 10000LL;
    std::snprintf(msg, sizeof msg, R"({"type":"strike_at","seq":%d,"t_us":%lld,"pulse_us":5000})", i + 2, (long long)t);
    hal.now_us = t - 500;
    ex.on_message(msg, hal.now_us);
    size_t before = hal.events.size();
    for (; hal.now_us <= t + 100; hal.now_us += 100) ex.poll(hal.now_us);
    if (hal.events.size() > before) fired_on_us += 5000;
  }
  CHECK(fired_on_us <= 2000000);  // at most 20% of the 10 s window
  CHECK(out.has("DUTY_CYCLE"));
}

static void test_hello_reports_limits_and_oversize_is_rejected() {
  Config cfg;
  char buf[kMaxMessage + 1];
  int n = write_hello(buf, sizeof buf, "rig", "bottles-v1", cfg);
  CHECK(n > 0 && n <= static_cast<int>(kMaxMessage));
  CHECK(std::string(buf).find(R"("travel_steps":48000)") != std::string::npos);
  CHECK(std::string(buf).find(R"("duty_limit":0.200)") != std::string::npos);
  SimHal hal;
  Capture out;
  Executor ex(hal, out);
  ex.on_oversize(0);
  CHECK(out.has("error: message too long"));
}

static void test_time_ping() {
  SimHal hal;
  Capture out;
  Executor ex(hal, out);
  ex.on_message(R"({"type":"time_ping","seq":9,"t1":111})", 5555);
  CHECK(out.has(R"({"type":"time_pong","seq":9,"t1":111,"t2":5555,"t3":5555})"));
}

int main() {
  test_parse();
  test_queue_orders_by_time();
  test_home_move_strike();
  test_strike_before_arrival_is_refused();
  test_safety_rules();
  test_duty_cycle_limit();
  test_duty_cannot_be_bypassed_with_short_pulses();
  test_hello_reports_limits_and_oversize_is_rejected();
  test_time_ping();
  if (failures) {
    std::printf("%d check(s) failed\n", failures);
    return 1;
  }
  std::printf("firmware core: all checks passed\n");
  return 0;
}
