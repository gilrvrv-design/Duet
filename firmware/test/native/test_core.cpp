// Native unit tests for the firmware core. Build and run: make -C firmware test
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "duet_device.hpp"
#include "duet_executor.hpp"
#include "duet_protocol.hpp"
#include "duet_queue.hpp"
#include "duet_sim_hal.hpp"

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

// Play from memory -------------------------------------------------------------

struct Rig {
  SimHal hal;
  Capture out;
  Executor ex{hal, out};
  MemorySongStore store;
  Device dev{ex, store, out};

  void msg(const char* json) { dev.on_message(json, hal.now_us); }
  void run_until(int64_t t_us) {
    for (; hal.now_us <= t_us; hal.now_us += 50) dev.poll(hal.now_us);
  }
  int strikes() const {
    int n = 0;
    for (auto& e : hal.events) n += e.kind[0] == 's';
    return n;
  }
  const SimEvent* first_strike() const {
    for (auto& e : hal.events)
      if (e.kind[0] == 's') return &e;
    return nullptr;
  }
};

// A tiny song: move to 6400 steps at 0.1 s, strike at 0.5 s, light a key at 0.5 s.
static const char* kSong[] = {
    R"({"type":"move_at","seq":0,"t_us":100000,"target_steps":6400,"v_max_mm_s":500.0,"a_max_mm_s2":5000.0})",
    R"({"type":"strike_at","seq":1,"t_us":500000,"pulse_us":20000})",
    R"({"type":"led_frame_at","seq":2,"t_us":500000,"first":10,"count":2,"rgb":[255,255,255]})",
};

static void upload(Rig& r, int slot, int seq = 7) {
  char header[96];
  std::snprintf(header, sizeof header, R"({"type":"song","seq":%d,"slot":%d,"lines":3})", seq,
                slot);
  r.msg(header);
  r.msg(kSong[0]);
  r.msg(R"({"type":"heartbeat","seq":0})");  // the Hub's heartbeats go on during uploads
  r.msg(kSong[1]);
  size_t replies = r.out.sent.size();
  r.msg(kSong[2]);
  CHECK(r.out.sent.size() == replies + 1);  // one ack, only after the last line
}

static void test_upload_then_play_from_memory() {
  Rig r;
  r.hal.place(4000);  // power-on: not homed, away from home
  upload(r, 2);
  CHECK(r.out.has(R"({"type":"ack","seq":7,"status":"ok"})"));
  CHECK(r.store.has(2) && !r.store.has(0));
  CHECK(r.strikes() == 0);  // stored, not played

  r.msg(R"({"type":"play","seq":8,"slot":2})");
  CHECK(r.out.has(R"({"type":"ack","seq":8,"status":"ok"})") && r.dev.playing());
  while (!r.ex.homed() && r.hal.now_us < 3000000) r.run_until(r.hal.now_us);
  int64_t homed_at = r.hal.now_us;
  r.run_until(5000000);
  CHECK(r.ex.homed() && !r.dev.playing());  // homed by itself, played, finished
  CHECK(r.strikes() == 1);
  const SimEvent* s = r.first_strike();
  CHECK(s && s->a == 6400);  // on the bottle the song moved to
  // The song's t_us 0 is the lead after homing; the strike is at t_us 0.5 s.
  int64_t due = homed_at + kPlayLeadUs + 500000;
  CHECK(s && s->t_us >= due && s->t_us <= due + 200);
  CHECK(!r.out.has("fault"));
}

static void test_a_bad_song_is_refused_whole() {
  Rig r;
  r.msg(R"({"type":"song","seq":3,"slot":0,"lines":2})");
  r.msg(kSong[0]);
  r.msg(R"({"type":"strike_at","seq":1,"t_us":-5,"pulse_us":20000})");  // before the start
  CHECK(r.out.has(R"({"type":"ack","seq":3,"status":"error: bad song line"})"));
  CHECK(!r.store.has(0));
  r.msg(R"({"type":"play","seq":4,"slot":0})");
  CHECK(r.out.has(R"({"type":"ack","seq":4,"status":"error: no song in that slot"})"));
  r.msg(R"({"type":"song","seq":5,"slot":9,"lines":2})");
  CHECK(r.out.has(R"({"type":"ack","seq":5,"status":"error: bad song slot"})"));
  r.msg(R"({"type":"song","seq":6,"slot":1,"lines":0})");
  CHECK(r.out.has(R"({"type":"ack","seq":6,"status":"error: bad song length"})"));
}

static void test_a_stalled_upload_is_dropped() {
  Rig r;
  r.msg(R"({"type":"song","seq":3,"slot":0,"lines":3})");
  r.msg(kSong[0]);
  r.run_until(kUploadTimeoutUs + 1000);
  CHECK(r.out.has(R"({"type":"ack","seq":3,"status":"error: upload stalled"})"));
  CHECK(!r.store.has(0));
  // Timed commands are live commands again, not song lines.
  r.msg(R"({"type":"strike_at","seq":4,"t_us":99999999,"pulse_us":20000})");
  CHECK(r.out.has(R"({"type":"ack","seq":4,"status":"ok"})") && r.ex.queued() == 1);
}

static void test_the_button_plays_the_next_song_and_stops() {
  Rig r;
  upload(r, 1, 7);
  upload(r, 4, 8);
  r.dev.button(r.hal.now_us);
  CHECK(r.dev.playing() && r.dev.slot() == 1);
  r.run_until(r.hal.now_us + 200000);
  r.dev.button(r.hal.now_us);  // a press while playing stops
  CHECK(!r.dev.playing() && r.ex.queued() == 0);
  bool cleared = false;
  for (auto& e : r.hal.events) cleared = cleared || e.kind[0] == 'c';
  CHECK(cleared);  // no key left lit
  r.dev.button(r.hal.now_us);
  CHECK(r.dev.playing() && r.dev.slot() == 4);  // the next stored song
  r.run_until(r.hal.now_us + 5000000);
  r.dev.button(r.hal.now_us);
  CHECK(r.dev.slot() == 1);  // and round again
}

static void test_no_watchdog_stop_while_playing_from_memory() {
  // A slow move: 6400 steps at 10 mm/s (800 steps/s) takes 8 s.
  Rig r;
  r.msg(R"({"type":"song","seq":1,"slot":0,"lines":1})");
  r.msg(R"({"type":"move_at","seq":0,"t_us":0,"target_steps":6400,"v_max_mm_s":10.0,"a_max_mm_s2":5000.0})");
  r.msg(R"({"type":"play","seq":2,"slot":0})");
  r.run_until(3000000);  // seconds with no Hub message, the carriage moving all along
  CHECK(r.hal.is_moving() && r.dev.playing() && !r.out.has("WATCHDOG"));
  r.run_until(10000000);
  CHECK(!r.dev.playing() && r.hal.position() == 6400 && r.ex.homed());
}

static void test_playing_from_memory_keeps_the_rig_safe() {
  Rig r;
  upload(r, 0);
  r.msg(R"({"type":"play","seq":8,"slot":0})");
  r.msg(R"({"type":"strike_at","seq":9,"t_us":1,"pulse_us":20000})");  // the Hub interrupts
  CHECK(r.out.has(R"({"type":"ack","seq":9,"status":"error: playing from memory"})"));
  r.msg(R"({"type":"play","seq":10,"slot":0})");
  CHECK(r.out.has(R"({"type":"ack","seq":10,"status":"error: already playing"})"));
  r.msg(R"({"type":"estop","seq":11})");
  CHECK(!r.dev.playing() && r.ex.estopped());
  r.msg(R"({"type":"play","seq":12,"slot":0})");
  CHECK(r.out.has(R"({"type":"ack","seq":12,"status":"error: emergency stop"})"));
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
  test_upload_then_play_from_memory();
  test_a_bad_song_is_refused_whole();
  test_a_stalled_upload_is_dropped();
  test_the_button_plays_the_next_song_and_stops();
  test_no_watchdog_stop_while_playing_from_memory();
  test_playing_from_memory_keeps_the_rig_safe();
  if (failures) {
    std::printf("%d check(s) failed\n", failures);
    return 1;
  }
  std::printf("firmware core: all checks passed\n");
  return 0;
}
