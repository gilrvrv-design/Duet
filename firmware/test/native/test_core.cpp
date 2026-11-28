// Native unit tests for the firmware core. Build and run: make -C firmware test
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "duet_api.hpp"
#include "rig.h"
#include "duet_json.hpp"
#include "duet_device.hpp"
#include "duet_executor.hpp"
#include "duet_features.hpp"
#include "duet_midi.hpp"
#include "duet_midi_planner.hpp"
#include "duet_planner.hpp"
#include "duet_protocol.hpp"
#include "duet_queue.hpp"
#include "duet_sim_hal.hpp"
#include "duet_instrument_data.hpp"

using namespace duet;

// The rig's channels, exactly as every board has them (src/rig.h).
static constexpr const Channels& kRig = BOARD_CHANNELS;

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
  CHECK(parse(R"({"type":"move_at","seq":3,"ch":0,"t_us":1500,"target_steps":6400,"v_max_mm_s":500.0,"a_max_mm_s2":5000.0})", c));
  CHECK(c.type == Type::MoveAt && c.seq == 3 && c.t_us == 1500 && c.target_steps == 6400);
  CHECK(c.v_max_mm_s == 500.0f && c.a_max_mm_s2 == 5000.0f);
  CHECK(parse(R"({"type":"led_frame_at","seq":4,"ch":1,"t_us":9,"first":10,"count":2,"rgb":[255,40,0]})", c));
  CHECK(c.type == Type::LedFrameAt && c.first == 10 && c.count == 2 && c.rgb[0] == 255 && c.rgb[1] == 40);
  CHECK(parse(R"({"type":"strike_at","seq":5,"ch":0,"t_us":123456789012,"pulse_us":20000})", c));
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
  Executor ex(hal, out, kRig);
  ex.on_message(R"({"type":"home","seq":1})", 0);
  CHECK(!ex.homed());
  run_until(ex, hal, 3000000);
  CHECK(ex.homed() && hal.position() == 0);
  CHECK(out.has(R"({"type":"telemetry","seq":0,"homed":true,"position":0,"queued":0})"));
  int64_t t0 = hal.now_us;
  char msg[200];
  std::snprintf(msg, sizeof msg, R"({"type":"move_at","seq":2,"ch":0,"t_us":%lld,"target_steps":6400,"v_max_mm_s":500,"a_max_mm_s2":5000})", (long long)(t0 + 1000));
  ex.on_message(msg, t0);
  std::snprintf(msg, sizeof msg, R"({"type":"strike_at","seq":3,"ch":0,"t_us":%lld,"pulse_us":20000})", (long long)(t0 + 400000));
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
  Executor ex(hal, out, kRig);
  ex.on_message(R"({"type":"home","seq":1})", 0);
  ex.on_message(R"({"type":"move_at","seq":2,"ch":0,"t_us":1000,"target_steps":46000,"v_max_mm_s":500,"a_max_mm_s2":5000})", 0);
  ex.on_message(R"({"type":"strike_at","seq":3,"ch":0,"t_us":200000,"pulse_us":20000})", 0);
  run_until(ex, hal, 300000);
  CHECK(out.has("NOT_ARRIVED"));
  CHECK(hal.events.empty());
}

static void test_safety_rules() {
  SimHal hal;
  Capture out;
  Executor ex(hal, out, kRig);
  ex.on_message(R"({"type":"strike_at","seq":1,"ch":0,"t_us":10,"pulse_us":20000})", 0);
  run_until(ex, hal, 1000);
  CHECK(out.has("NOT_HOMED"));

  ex.on_message(R"({"type":"home","seq":2})", hal.now_us);
  ex.on_message(R"({"type":"move_at","seq":3,"ch":0,"t_us":2000,"target_steps":99999,"v_max_mm_s":500,"a_max_mm_s2":5000})", hal.now_us);
  run_until(ex, hal, 3000);
  CHECK(out.has("SOFT_LIMIT"));

  // Watchdog: a long move, then silence from the Hub.
  ex.on_message(R"({"type":"move_at","seq":4,"ch":0,"t_us":4000,"target_steps":46000,"v_max_mm_s":20,"a_max_mm_s2":5000})", hal.now_us);
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
  Executor ex(hal, out, kRig);
  ex.on_message(R"({"type":"home","seq":1})", 0);
  char msg[160];
  // 50 ms pulses every 100 ms = 50% duty; the limit is 20% over 10 s (2 s on).
  for (int i = 0; i < 60; ++i) {
    std::snprintf(msg, sizeof msg, R"({"type":"strike_at","seq":%d,"ch":0,"t_us":%d,"pulse_us":50000})", i + 2, 1000 + i * 100000);
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
  Executor ex(hal, out, kRig);
  ex.on_message(R"({"type":"home","seq":1})", 0);
  char msg[160];
  int64_t fired_on_us = 0;
  for (int i = 0; i < 1000; ++i) {
    int64_t t = 1000 + i * 10000LL;
    std::snprintf(msg, sizeof msg, R"({"type":"strike_at","seq":%d,"ch":0,"t_us":%lld,"pulse_us":5000})", i + 2, (long long)t);
    hal.now_us = t - 500;
    ex.on_message(msg, hal.now_us);
    size_t before = hal.events.size();
    for (; hal.now_us <= t + 100; hal.now_us += 100) ex.poll(hal.now_us);
    if (hal.events.size() > before) fired_on_us += 5000;
  }
  CHECK(fired_on_us <= 2000000);  // at most 20% of the 10 s window
  CHECK(out.has("DUTY_CYCLE"));
}

static void test_greeting_hello_then_channels_and_oversize_is_rejected() {
  {
    SimHal hal;
    Capture out;
    Executor ex(hal, out, kRig);
    MemorySongStore store;
    Device dev(ex, store, out,
               Identity{"duet-rig-1", "esp32-classic", "bottles-v1", kWifi | kPlayButton, kRig});
    dev.greet();
    CHECK(out.sent.size() == 4);  // hello, then one message per channel
    CHECK(out.sent[0] ==
          R"({"type":"hello","seq":0,"protocol":5,"device_id":"duet-rig-1","board":"esp32-classic",)"
          R"("profile":"bottles-v1","features":["wifi","play_button"],"channels":3})");
    CHECK(out.sent[1].find(R"({"type":"channel","seq":0,"ch":0,"kind":"carriage_striker")") == 0);
    CHECK(out.sent[1].find(R"("travel_steps":48000)") != std::string::npos);
    CHECK(out.sent[1].find(R"("duty_limit":0.200)") != std::string::npos);
    CHECK(out.sent[2] == R"({"type":"channel","seq":0,"ch":1,"kind":"led_strip","count":176})");
    CHECK(out.sent[3] == R"({"type":"channel","seq":0,"ch":2,"kind":"midi_out","count":0})");
    // On a serial link the Hub asks for the greeting, and hears the same again.
    dev.on_message(R"({"type":"greet","seq":0})", 0);
    CHECK(out.sent.size() == 8 && out.sent[4] == out.sent[0] && out.sent[7] == out.sent[3]);
  }
  // The longest hello possible (every feature, long names) still fits one message.
  char buf[kMaxMessage + 1];
  uint32_t all = 0;
  for (const FeatureName& f : kFeatureNames) all |= f.feature;
  int n = write_hello(buf, sizeof buf,
                      Identity{"a-device-id-of-32-characters-xxx", "a-board-name-24-chars-xx",
                               "a-profile-id-24-chars-xx", all, kRig});
  CHECK(n > 0 && n <= static_cast<int>(kMaxMessage));
  CHECK(write_channel(buf, sizeof buf, 0, RIG_CHANNELS[0], Config{}) <= int(kMaxMessage));
  SimHal hal;
  Capture out;
  Executor ex(hal, out, kRig);
  ex.on_oversize(0);
  CHECK(out.has("error: message too long"));
}

static void test_time_ping() {
  SimHal hal;
  Capture out;
  Executor ex(hal, out, kRig);
  ex.on_message(R"({"type":"time_ping","seq":9,"t1":111})", 5555);
  CHECK(out.has(R"({"type":"time_pong","seq":9,"t1":111,"t2":5555,"t3":5555})"));
}

// Play from memory -------------------------------------------------------------

struct Rig {
  SimHal hal;
  Capture out;
  Executor ex{hal, out, kRig};
  MemorySongStore store;
  Device dev{ex, store, out, Identity{"duet-rig-1", "native", "bottles-v1", kPlayButton, kRig}};

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
    R"({"type":"move_at","seq":0,"ch":0,"t_us":100000,"target_steps":6400,"v_max_mm_s":500.0,"a_max_mm_s2":5000.0})",
    R"({"type":"strike_at","seq":1,"ch":0,"t_us":500000,"pulse_us":20000})",
    R"({"type":"led_frame_at","seq":2,"ch":1,"t_us":500000,"first":10,"count":2,"rgb":[255,255,255]})",
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

static void test_a_song_keeps_its_title() {
  Rig r;
  r.msg(R"({"type":"song","seq":3,"slot":1,"lines":1,"title":"Rain \"on\" the Bottles \u00e9"})");
  r.msg(kSong[0]);
  CHECK(r.out.has(R"({"type":"ack","seq":3,"status":"ok"})"));
  CHECK(r.store.title(1) == "Rain \"on\" the Bottles \xc3\xa9");

  const char* bad[] = {
      R"({"type":"song","seq":4,"slot":1,"lines":1,"title":"two\nlines"})",
      R"({"type":"song","seq":4,"slot":1,"lines":1,"title":"x)"
      R"(xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"})",  // 65 bytes
      R"({"type":"song","seq":4,"slot":1,"lines":1,"title":5})",
  };
  for (const char* header : bad) {
    r.out.sent.clear();
    r.msg(header);
    CHECK(r.out.has(R"({"type":"ack","seq":4,"status":"error: bad song title"})"));
  }
  CHECK(r.store.title(1) == "Rain \"on\" the Bottles \xc3\xa9");  // the stored song stays
}

static void test_a_key_is_never_read_from_inside_a_value() {
  // A title that reads like a key, before that key: the key's own value is read.
  Rig r;
  r.msg(R"({"type":"song","seq":5,"title":"slot \"lines\": 9","slot":2,"lines":1})");
  r.msg(kSong[0]);
  CHECK(r.out.has(R"({"type":"ack","seq":5,"status":"ok"})") && r.store.has(2));
  CHECK(r.store.title(2) == "slot \"lines\": 9");
  Command c;
  CHECK(parse(R"({"title":"type","type":"stop","seq":3})", c) && c.type == Type::Stop);
  CHECK(!parse(R"({"note":"\"type\":\"stop\""})", c));  // only inside a value: not a stop
}

static void test_a_bad_song_is_refused_whole() {
  Rig r;
  r.msg(R"({"type":"song","seq":3,"slot":0,"lines":2})");
  r.msg(kSong[0]);
  r.msg(R"({"type":"strike_at","seq":1,"ch":0,"t_us":-5,"pulse_us":20000})");  // before the start
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
  r.msg(R"({"type":"strike_at","seq":4,"ch":0,"t_us":99999999,"pulse_us":20000})");
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

static void test_stop_clears_what_the_hub_queued() {
  Rig r;
  r.hal.place(0);
  r.msg(R"({"type":"home","seq":1})");
  r.run_until(500000);
  CHECK(r.ex.homed());
  // A live performance: a move now and strikes later, from the Hub.
  r.msg(R"({"type":"move_at","seq":2,"ch":0,"t_us":600000,"target_steps":6400,"v_max_mm_s":500.0,"a_max_mm_s2":5000.0})");
  r.msg(R"({"type":"strike_at","seq":3,"ch":0,"t_us":2000000,"pulse_us":20000})");
  r.msg(R"({"type":"heartbeat","seq":0})");
  r.run_until(700000);
  CHECK(r.ex.queued() == 1);
  r.msg(R"({"type":"stop","seq":4})");  // the page stopped the practice
  CHECK(r.out.has(R"({"type":"ack","seq":4,"status":"ok"})") && r.ex.queued() == 0);
  r.run_until(3000000);
  CHECK(r.strikes() == 0);  // nothing more plays
}

static void test_no_watchdog_stop_while_playing_from_memory() {
  // A slow move: 6400 steps at 10 mm/s (800 steps/s) takes 8 s.
  Rig r;
  r.msg(R"({"type":"song","seq":1,"slot":0,"lines":1})");
  r.msg(R"({"type":"move_at","seq":0,"ch":0,"t_us":0,"target_steps":6400,"v_max_mm_s":10.0,"a_max_mm_s2":5000.0})");
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
  r.msg(R"({"type":"strike_at","seq":9,"ch":0,"t_us":1,"pulse_us":20000})");  // the Hub interrupts
  CHECK(r.out.has(R"({"type":"ack","seq":9,"status":"error: playing from memory"})"));
  r.msg(R"({"type":"play","seq":10,"slot":0})");
  CHECK(r.out.has(R"({"type":"ack","seq":10,"status":"error: already playing"})"));
  r.msg(R"({"type":"estop","seq":11})");
  CHECK(!r.dev.playing() && r.ex.estopped());
  r.msg(R"({"type":"play","seq":12,"slot":0})");
  CHECK(r.out.has(R"({"type":"ack","seq":12,"status":"error: emergency stop"})"));
}

static void test_commands_must_name_a_channel_of_their_kind() {
  SimHal hal;
  Capture out;
  Executor ex(hal, out, kRig);
  ex.on_message(R"({"type":"strike_at","seq":1,"t_us":5,"pulse_us":20000})", 0);  // no ch
  CHECK(out.has(R"({"type":"ack","seq":1,"status":"error: cannot parse"})"));
  ex.on_message(R"({"type":"strike_at","seq":2,"ch":1,"t_us":5,"pulse_us":20000})", 0);
  CHECK(out.has(R"({"type":"ack","seq":2,"status":"error: no such channel"})"));  // a strip
  ex.on_message(R"({"type":"led_frame_at","seq":3,"ch":7,"t_us":5,"first":0,"count":1,"rgb":[1,2,3]})", 0);
  CHECK(out.has(R"({"type":"ack","seq":3,"status":"error: no such channel"})"));
  ex.on_message(R"({"type":"led_frame_at","seq":4,"ch":1,"t_us":5,"first":0,"count":1,"rgb":[1,2,3]})", 0);
  CHECK(out.has(R"({"type":"ack","seq":4,"status":"ok"})") && ex.queued() == 1);
}

static int midi_count(const SimHal& hal, int status_and_data1) {
  int n = 0;
  for (auto& e : hal.events) n += e.kind[0] == 'm' && e.a == status_and_data1;
  return n;
}

static void test_midi_notes_play_and_are_silenced_when_the_hub_goes_quiet() {
  SimHal hal;
  Capture out;
  Executor ex(hal, out, kRig);
  ex.on_message(R"({"type":"note_at","seq":1,"ch":2,"t_us":1000,"midi":0,"pitch":60,"vel":90})", 0);
  CHECK(out.has(R"({"type":"ack","seq":1,"status":"ok"})"));  // no homing needed
  hal.now_us = 1000;
  ex.poll(1000);
  CHECK(midi_count(hal, 0x90 << 8 | 60) == 1);  // note on, MIDI channel 1
  // The note is held and the Hub goes silent: the watchdog stops everything.
  for (hal.now_us = 1000; hal.now_us < 1'200'000; hal.now_us += 1000) ex.poll(hal.now_us);
  CHECK(out.has("WATCHDOG"));
  CHECK(midi_count(hal, 0xB0 << 8 | 123) == 1);   // All Notes Off on MIDI channel 1...
  CHECK(midi_count(hal, 0xBF << 8 | 123) == 1);   // ...and on channel 16
}

static void test_midi_notes_off_and_estop_and_boards_without_midi() {
  SimHal hal;
  Capture out;
  Executor ex(hal, out, kRig);
  ex.on_message(R"({"type":"note_at","seq":1,"ch":2,"t_us":0,"midi":3,"pitch":64,"vel":80})", 0);
  ex.on_message(R"({"type":"note_at","seq":2,"ch":2,"t_us":5,"midi":3,"pitch":64,"vel":0})", 0);
  ex.poll(10);
  CHECK(midi_count(hal, 0x93 << 8 | 64) == 1 && midi_count(hal, 0x83 << 8 | 64) == 1);
  // A note released in time: silence for a whole second does not trip the watchdog.
  for (hal.now_us = 10; hal.now_us < 2'000'000; hal.now_us += 1000) ex.poll(hal.now_us);
  CHECK(!out.has("WATCHDOG"));
  ex.on_message(R"({"type":"estop","seq":3})", hal.now_us);
  CHECK(midi_count(hal, 0xB3 << 8 | 123) == 1);  // the e-stop silences MIDI too
  ex.on_message(R"({"type":"note_at","seq":4,"ch":2,"t_us":0,"midi":0,"pitch":99,"vel":200})", 0);
  CHECK(out.has(R"({"type":"ack","seq":4,"status":"error: cannot parse"})"));  // vel > 127

  static constexpr Channel kNoMidi[] = {{ChannelKind::CarriageStriker, 0}};
  SimHal hal2;
  Capture out2;
  Executor plain(hal2, out2, Channels{kNoMidi, 1});
  plain.on_message(R"({"type":"note_at","seq":5,"ch":2,"t_us":0,"midi":0,"pitch":60,"vel":90})", 0);
  CHECK(out2.has(R"({"type":"ack","seq":5,"status":"error: no such channel"})"));
  plain.on_message(R"({"type":"estop","seq":6})", 0);
  CHECK(midi_count(hal2, 0xB0 << 8 | 123) == 0);  // no MIDI port: nothing sent to it
}

// The device API ------------------------------------------------------------------

static void test_the_api_reports_the_device_and_plays_its_songs() {
  Rig r;
  r.hal.place(4000);
  MemorySettingsStore settings;
  Api api(r.dev, settings);
  Response info = api.handle("GET", "/api/info", "", r.hal.now_us);
  CHECK(info.status == 200);
  CHECK(info.body.find(R"({"hello":{"type":"hello")") == 0);  // as the Hub hears it
  CHECK(info.body.find(R"("features":["play_button"])") != std::string::npos);
  CHECK(info.body.find(R"("kind":"midi_out")") != std::string::npos);
  CHECK(info.body.find(R"("state":"idle","slot":-1,"estopped":false,"network":"station","link":""})") != std::string::npos);

  CHECK(api.handle("GET", "/api/songs", "", 0).body == R"({"slots":8,"songs":[]})");
  upload(r, 2);
  upload(r, 5, 9);
  CHECK(api.handle("GET", "/api/songs", "", 0).body ==
        R"({"slots":8,"songs":[{"slot":2,"title":""},{"slot":5,"title":""}]})");

  Response none = api.handle("POST", "/api/songs/0/play", "", r.hal.now_us);
  CHECK(none.status == 404 && none.body == R"({"error":"no song in that slot"})");
  CHECK(api.handle("POST", "/api/songs/2/play", "", r.hal.now_us).status == 200);
  CHECK(r.dev.playing() && r.dev.slot() == 2);
  CHECK(api.handle("POST", "/api/songs/5/play", "", r.hal.now_us).body ==
        R"({"error":"already playing"})");
  CHECK(api.handle("GET", "/api/info", "", 0).body.find(R"("state":"homing","slot":2)") !=
        std::string::npos);
  CHECK(api.handle("POST", "/api/stop", "", r.hal.now_us).status == 200 && !r.dev.playing());

  CHECK(api.handle("POST", "/api/estop", "", r.hal.now_us).status == 200 && r.dev.estopped());
  CHECK(api.handle("POST", "/api/songs/2/play", "", r.hal.now_us).body ==
        R"({"error":"emergency stop"})");
}

static void test_the_api_refuses_unknown_paths_and_wrong_methods() {
  Rig r;
  MemorySettingsStore settings;
  Api api(r.dev, settings);
  CHECK(api.handle("GET", "/api/nothing", "", 0).status == 404);
  CHECK(api.handle("POST", "/api/songs/8/play", "", 0).status == 404);  // slots are 0-7
  CHECK(api.handle("POST", "/api/songs/x/play", "", 0).status == 404);
  CHECK(api.handle("POST", "/api/songs/1/playx", "", 0).status == 404);
  CHECK(api.handle("POST", "/api/info", "", 0).status == 405);
  CHECK(api.handle("GET", "/api/stop", "", 0).status == 405);
  CHECK(api.handle("GET", "/api/songs/1/play", "", 0).status == 405);
  CHECK(!r.dev.estopped());
}

static std::string song_file(const char* title) {
  std::string file = std::string(R"({"title":")") + title + "\"}\n";
  for (const char* line : kSong) file += std::string(line) + "\r\n";  // any line ending
  return file;
}

static void test_the_api_stores_a_song_file() {
  Rig r;
  MemorySettingsStore settings;
  Api api(r.dev, settings);
  Response stored = api.handle("PUT", "/api/songs/6", song_file("Rain").c_str(), 0);
  CHECK(stored.status == 200);
  CHECK(r.store.has(6) && r.store.title(6) == "Rain");
  CHECK(api.handle("GET", "/api/songs", "", 0).body ==
        R"({"slots":8,"songs":[{"slot":6,"title":"Rain"}]})");

  // In pieces, as the ESP32's web server hands them over: the same song.
  std::string file = song_file("In pieces");
  CHECK(api.begin_upload("/api/songs/2").status == 200);
  for (size_t at = 0; at < file.size(); at += 7)
    api.upload_data(file.c_str() + at, std::min<size_t>(7, file.size() - at));
  CHECK(api.end_upload().status == 200 && r.store.title(2) == "In pieces");

  // It plays like a song from the Hub.
  CHECK(api.handle("POST", "/api/songs/2/play", "", r.hal.now_us).status == 200);
  r.run_until(5000000);
  CHECK(r.strikes() == 1 && !r.out.has("fault"));

  CHECK(api.handle("DELETE", "/api/songs/6", "", 0).status == 200 && !r.store.has(6));
  CHECK(api.handle("DELETE", "/api/songs/6", "", 0).status == 404);
}

static void test_the_api_refuses_a_bad_song_file_whole() {
  Rig r;
  MemorySettingsStore settings;
  Api api(r.dev, settings);
  CHECK(api.handle("PUT", "/api/songs/1", song_file("Old").c_str(), 0).status == 200);
  std::string bad_line = song_file("New") +
                         R"({"type":"strike_at","seq":1,"ch":0,"t_us":-5,"pulse_us":20000})";
  Response refused = api.handle("PUT", "/api/songs/1", bad_line.c_str(), 0);
  CHECK(refused.status == 400 && refused.body == R"({"error":"bad song line 5"})");
  CHECK(r.store.title(1) == "Old");  // the stored song stays

  std::string no_title = std::string(kSong[0]) + "\n";
  CHECK(api.handle("PUT", "/api/songs/1", no_title.c_str(), 0).status == 400);
  CHECK(api.handle("PUT", "/api/songs/1", "", 0).body == R"({"error":"the song file is empty"})");
  CHECK(api.handle("PUT", "/api/songs/1", R"({"title":"only a title"})", 0).status == 400);
  std::string too_long = song_file("Long") + std::string(300, 'x') + "\n";
  CHECK(api.handle("PUT", "/api/songs/1", too_long.c_str(), 0).body ==
        R"({"error":"bad song line 5"})");
  CHECK(api.handle("PUT", "/api/songs/9", song_file("x").c_str(), 0).status == 404);
  CHECK(api.handle("POST", "/api/songs/1", "", 0).status == 405);
  CHECK(r.store.title(1) == "Old" && !r.dev.writing_song());

  // Not while a song plays, nor while the Hub is storing one.
  CHECK(api.handle("POST", "/api/songs/1/play", "", 0).status == 200);
  CHECK(api.handle("PUT", "/api/songs/2", song_file("x").c_str(), 0).body ==
        R"({"error":"the rig is busy playing"})");
  CHECK(api.handle("DELETE", "/api/songs/1", "", 0).status == 409);
  r.dev.stop();
  r.msg(R"({"type":"song","seq":3,"slot":0,"lines":3})");  // the Hub starts an upload
  CHECK(api.handle("PUT", "/api/songs/2", song_file("x").c_str(), 0).body ==
        R"({"error":"another song is being stored"})");
  CHECK(api.begin_upload("/api/songs/2").status == 409);
}

static void test_json_objects_of_strings_and_lists() {
  JsonObject o;
  CHECK(read_object(R"( {"a":"x\"y\\zé\n", "list":["1", "2"], "empty":[]} )", o));
  CHECK(o.strings["a"] == "x\"y\\z\xc3\xa9\n");
  CHECK((o.lists["list"] == std::vector<std::string>{"1", "2"}) && o.lists["empty"].empty());
  CHECK(read_object("{}", o) && o.strings.empty());
  CHECK(!read_object(R"({"a":1})", o));            // numbers are not settings
  CHECK(!read_object(R"({"a":"x"} trailing)", o));  // exactly one object
  CHECK(!read_object(R"({"a":"x)", o));
  CHECK(!read_object(R"({"a":"\ud83c"})", o));     // surrogate pairs: refused, not mangled
  CHECK(!read_object("", o));
  CHECK(json_string("say \"hi\"\\\n") == R"("say \"hi\"\\\u000a")");
}

static void test_settings_are_saved_and_the_password_never_leaves() {
  Rig r;
  MemorySettingsStore store;
  Api api(r.dev, store);
  api.set_network(Network::Setup);
  CHECK(api.handle("GET", "/api/info", "", 0).body.find(R"("network":"setup")") !=
        std::string::npos);
  CHECK(api.handle("GET", "/api/settings", "", 0).body ==
        R"({"wifi_ssid":"","wifi_password_set":false,"servers":[]})");

  Response joined = api.handle(
      "POST", "/api/settings",
      R"({"wifi_ssid":"Home \"5\"","wifi_password":"correct horse","servers":["https://duet.example"]})",
      0);
  CHECK(joined.status == 200 && joined.restart);  // a new network: restart to join it
  CHECK(store.load().wifi_password == "correct horse");
  CHECK(api.handle("GET", "/api/settings", "", 0).body ==
        R"({"wifi_ssid":"Home \"5\"","wifi_password_set":true,"servers":["https://duet.example"]})");

  // Only the servers change: the password is kept, and there is no restart.
  Response servers = api.handle(
      "POST", "/api/settings", R"({"wifi_ssid":"Home \"5\"","servers":["http://10.0.0.2:8000"]})", 0);
  CHECK(servers.status == 200 && !servers.restart);
  CHECK(store.load().wifi_password == "correct horse");
  CHECK(store.load().servers == std::vector<std::string>{"http://10.0.0.2:8000"});
}

static void test_bad_settings_are_refused_and_nothing_is_saved() {
  Rig r;
  MemorySettingsStore store;
  Api api(r.dev, store);
  const char* bad[] = {
      R"({"wifi_ssid":"","servers":[]})",
      R"({"wifi_ssid":"123456789012345678901234567890123","servers":[]})",
      R"({"wifi_ssid":"home","wifi_password":"short","servers":[]})",
      R"({"wifi_ssid":"home","servers":["ftp://x"]})",
      R"({"wifi_ssid":"home","servers":["http://a","http://b","http://c","http://d","http://e"]})",
      R"({"wifi_ssid":"home"})",
      R"(not json)",
  };
  for (const char* body : bad) CHECK(api.handle("POST", "/api/settings", body, 0).status == 400);
  CHECK(!store.load().has_wifi());
  CHECK(api.handle("POST", "/api/settings", R"({"wifi_ssid":"open cafe","servers":[]})", 0).status ==
        200);  // an open network needs no password
}

// A MIDI file of format 1 (or 0 for one track): header, then each track's events.
using Bytes = std::vector<uint8_t>;
static Bytes smf(std::vector<Bytes> tracks, uint16_t division = 480, uint16_t format = 1) {
  Bytes out = {'M', 'T', 'h', 'd', 0, 0, 0, 6, 0, static_cast<uint8_t>(format), 0,
               static_cast<uint8_t>(tracks.size()), static_cast<uint8_t>(division >> 8),
               static_cast<uint8_t>(division & 0xFF)};
  for (const Bytes& t : tracks) {
    Bytes body = t;
    body.insert(body.end(), {0x00, 0xFF, 0x2F, 0x00});  // end of track
    uint32_t n = static_cast<uint32_t>(body.size());
    out.insert(out.end(), {'M', 'T', 'r', 'k', static_cast<uint8_t>(n >> 24),
                           static_cast<uint8_t>(n >> 16), static_cast<uint8_t>(n >> 8),
                           static_cast<uint8_t>(n)});
    out.insert(out.end(), body.begin(), body.end());
  }
  return out;
}

static bool import(const Bytes& file, MidiScore& score) {
  std::string why;
  return read_midi(file.data(), file.size(), score, why);
}

static std::string refusal(const Bytes& file) {
  MidiScore score;
  std::string why;
  return read_midi(file.data(), file.size(), score, why) ? "" : why;
}

static void test_midi_running_status_and_note_on_releases() {
  // One status byte, then data bytes only; a note on of velocity 0 releases.
  Bytes track = {0x00, 0x90, 60, 100, 0x60, 60, 0, 0x00, 62, 80, 0x81, 0x70, 62, 0};
  MidiScore s;
  CHECK(import(smf({track}, 480, 0), s));
  CHECK(s.events.size() == 2 && s.warnings.empty());
  CHECK(s.tempo_bpm == 120.0 && s.beats_per_bar == 4 && s.beat_unit == 4);  // MIDI's defaults
  const ScoreEvent& a = s.events[0];
  CHECK(a.pitch == 60 && a.vel == 100 && a.bar == 1 && a.beat == 1.0 && a.dur == 0.2);
  const ScoreEvent& b = s.events[1];  // 0x81 0x70: 240 ticks, half a beat
  CHECK(b.pitch == 62 && b.vel == 80 && b.beat == 1.2 && b.dur == 0.5);
  CHECK(refusal(smf({{0x00, 60, 100}})) == "track 0 uses running status with no status before it");
}

static void test_midi_truncated_or_malformed_is_refused() {
  Bytes file = smf({{0x00, 0xFF, 0x51, 0x03, 0x07, 0xA1, 0x20, 0x00, 0x90, 60, 100, 0x60, 0x80,
                     60, 0}});
  MidiScore s;
  CHECK(import(file, s));
  for (size_t n = 0; n < file.size(); ++n) {  // every cut is refused, none read past it
    Bytes cut(file.begin(), file.begin() + static_cast<long>(n));
    CHECK(!refusal(cut).empty());
  }
  Bytes tail = file;  // the track says it is a byte longer than the file
  tail[21] += 1;      // the low byte of its length, after MThd (14 bytes) and MTrk
  CHECK(refusal(tail) == "track 0 runs past the end of the file");
  CHECK(refusal(Bytes(kMaxMidiBytes + 1, 0)).find("larger than") != std::string::npos);
  CHECK(refusal({'R', 'I', 'F', 'F', 0, 0, 0, 6, 0, 0, 0, 0, 0, 0}) ==
        "not a MIDI file: no MThd header");
  CHECK(refusal(smf({{0x00, 0x90, 60, 100}}, 0xE728)).find("SMPTE") != std::string::npos);
  CHECK(refusal(smf({{0x00, 0x90, 60, 200}})) == "track 0 has a data byte above 127");
  CHECK(refusal(smf({{0x00, 0xF1, 0x00}})).find("0xF1") != std::string::npos);
  CHECK(refusal(smf({{0x00, 0xFF, 0x58, 0x04, 5, 5, 24, 8}})) ==
        "unsupported time signature 5/32");
  CHECK(refusal(smf({{0x00, 0xFF, 0x51, 0x02, 0x07, 0xA1}})).find("tempo") != std::string::npos);
  CHECK(refusal(smf({{0x00, 0x90, 60, 100}})) == "the file has no notes");  // never released
  CHECK(refusal(smf({{0x00, 0x90, 60, 100}}, 480, 2)).find("format 2") != std::string::npos);
}

static void test_midi_tracks_by_mean_pitch() {
  Bytes low = {0x00, 0x90, 48, 70, 0x83, 0x60, 0x80, 48, 0,   // C3 for a beat
               0x00, 0x90, 50, 70, 0x83, 0x60, 0x80, 50, 0};  // D3
  Bytes high = {0x00, 0x91, 72, 90, 0x83, 0x60, 0x81, 72, 0};  // C5 on its own channel
  MidiScore s;
  CHECK(import(smf({low, high}), s) && s.events.size() == 3);
  for (const ScoreEvent& e : s.events)
    CHECK(e.part == (e.pitch == 72 ? DuoPart::Bot : DuoPart::Human));
  CHECK(s.events[0].pitch == 48 && s.events[1].pitch == 72);  // by start, then pitch
  CHECK(s.events[2].pitch == 50 && s.events[2].beat == 2.0);
}

static void test_midi_named_tracks_win_over_pitch() {
  Bytes robot = {0x00, 0xFF, 0x03, 0x07, ' ', 'R', 'o', 'B', 'o', 't', '\t',
                 0x00, 0x90, 40, 70, 0x60, 0x80, 40, 0};
  Bytes pianist = {0x00, 0xFF, 0x03, 0x07, 'P', 'I', 'A', 'N', 'I', 'S', 'T',
                   0x00, 0x90, 90, 70, 0x60, 0x80, 90, 0};
  Bytes other = {0x00, 0xFF, 0x03, 0x04, 'L', 'e', 'a', 'd',
                 0x00, 0x90, 100, 70, 0x60, 0x80, 100, 0};
  MidiScore s;
  CHECK(import(smf({robot, pianist, other}), s) && s.events.size() == 3);
  for (const ScoreEvent& e : s.events)
    CHECK(e.part == (e.pitch == 40 ? DuoPart::Bot : DuoPart::Human));
  CHECK(std::string(part_name(DuoPart::Bot)) == "robot");
}

static void test_midi_one_track_is_split_by_skyline() {
  // A C major chord, then G4 alone, in 3/4 at 60 bpm.
  Bytes track = {0x00, 0xFF, 0x58, 0x04, 3, 2, 24, 8, 0x00, 0xFF, 0x51, 0x03, 0x0F, 0x42, 0x40,
                 0x00, 0x90, 60, 70, 0x00, 64, 70, 0x00, 67, 70,
                 0x83, 0x60, 60, 0, 0x00, 64, 0, 0x00, 67, 0,
                 0x00, 67, 70, 0x83, 0x60, 67, 0};
  MidiScore s;
  CHECK(import(smf({track}), s) && s.events.size() == 4);
  CHECK(s.beats_per_bar == 3 && s.beat_unit == 4 && s.tempo_bpm == 60.0);
  CHECK(s.events[0].part == DuoPart::Human && s.events[1].part == DuoPart::Human);
  CHECK(s.events[2].pitch == 67 && s.events[2].part == DuoPart::Bot);
  CHECK(s.events[3].pitch == 67 && s.events[3].part == DuoPart::Bot && s.events[3].beat == 2.0);
}

static void test_midi_warns_of_what_a_score_cannot_hold() {
  Bytes track = {0x00, 0xFF, 0x51, 0x03, 0x00, 0x30, 0xD4,  // 12500 us: 4800 bpm
                 0x00, 0x90, 60, 70, 0x60, 0x80, 60, 0,
                 0x00, 0xFF, 0x51, 0x03, 0x07, 0xA1, 0x20,  // a later tempo
                 0x00, 0x90, 62, 70};                       // never released
  MidiScore s;
  CHECK(import(smf({track}), s) && s.tempo_bpm == 300.0);
  CHECK(s.warnings == std::vector<std::string>({
                          "1 later tempo change(s) ignored: one tempo per score",
                          "1 note(s) never released were left out",
                          "tempo 4800 bpm is outside what a score allows; using 300",
                      }));
}

// The planner, on the rig's instruments: bottles-v1 (C5..C6, a diatonic octave) and
// piano-88 under a 176-LED strip.
static const CarriageInstrument& kBottles =
    kCarriageInstruments[instrument_index(kCarriageInstruments, "bottles-v1")];
static const KeyboardInstrument& kPiano88 =
    kKeyboardInstruments[instrument_index(kKeyboardInstruments, "piano-88")];

struct SongLines : SongSink {
  std::vector<Command> commands;
  void line(const char* json) override {
    Command c;
    CHECK(std::strlen(json) <= kMaxMessage && parse(json, c));
    commands.push_back(c);
  }
  std::vector<Command> of(Type type) const {
    std::vector<Command> out;
    for (const Command& c : commands)
      if (c.type == type) out.push_back(c);
    return out;
  }
};

static MidiScore duet_score(double tempo_bpm, int beats_per_bar = 4) {
  MidiScore s;
  s.tempo_bpm = tempo_bpm;
  s.beats_per_bar = beats_per_bar;
  return s;
}

static void bot(MidiScore& s, int32_t bar, double beat, uint8_t pitch, uint8_t vel = 80) {
  s.events.push_back({beat, 0.25, bar, pitch, vel, DuoPart::Bot});
}

static void human(MidiScore& s, int32_t bar, double beat, uint8_t pitch) {
  s.events.push_back({beat, 1.0, bar, pitch, 70, DuoPart::Human});
}

static SongLines plan(const MidiScore& s, const Channels& channels = kRig) {
  SongLines song;
  std::string why;
  CHECK(plan_song(s, kBottles, kPiano88, channels, song, why));
  CHECK(why.empty());
  return song;
}

static std::string plan_refusal(const MidiScore& s, const Channels& channels = kRig) {
  SongLines song;
  std::string why;
  CHECK(!plan_song(s, kBottles, kPiano88, channels, song, why));
  CHECK(song.commands.empty());
  return why;
}

static void test_planner_counts_in_then_plays_in_time_order() {
  MidiScore s = duet_score(120, 3);
  bot(s, 1, 1.0, 72);  // C5, the first bottle: a move from home, then a strike
  SongLines song = plan(s);
  const std::vector<Command>& c = song.commands;
  for (size_t i = 0; i < c.size(); ++i) {
    CHECK(c[i].seq == static_cast<int64_t>(i));
    CHECK(i == 0 || c[i - 1].t_us <= c[i].t_us);
    CHECK(c[i].ch == (c[i].type == Type::LedFrameAt ? 1 : 0));
  }
  CHECK(c[0].type == Type::LedFrameAt && c[0].t_us == 0);  // the count-in starts the song
  // A bar's count-in in 3/4 at 120 bpm: the whole strip, a beat apart, half a beat each.
  std::vector<Command> leds = song.of(Type::LedFrameAt);
  std::vector<Command> count_in;
  for (const Command& l : leds)
    if (l.first == 0 && l.count == 176 && l.rgb[2] == 255) count_in.push_back(l);
  CHECK(count_in.size() == 3);
  for (size_t i = 1; i < count_in.size(); ++i)
    CHECK(count_in[i].t_us - count_in[i - 1].t_us == 500000);
  std::vector<Command> strikes = song.of(Type::StrikeAt);
  CHECK(strikes.size() == 1);
  // Bar 1 beat 1 sounds a bar after the count-in starts; the strike fires 12 ms early.
  CHECK(strikes[0].t_us - count_in[0].t_us == 1500000 - 12000);
  CHECK(strikes[0].pulse_us == 24405);  // velocity 80 of 1..127 over 15..30 ms
  // The carriage leaves home just in time: 15 mm, a triangular move, then 15 ms to settle.
  std::vector<Command> moves = song.of(Type::MoveAt);
  CHECK(moves.size() == 1 && moves[0].target_steps == 1200);
  CHECK(moves[0].v_max_mm_s == 500.0f && moves[0].a_max_mm_s2 == 5000.0f);
  CHECK(strikes[0].t_us - moves[0].t_us == 124545);
}

static void test_planner_folds_notes_onto_bottles() {
  MidiScore s = duet_score(60);
  bot(s, 1, 1.0, 61);  // C#4: no bottle has a C#, so the nearest one, C5
  bot(s, 2, 1.0, 96);  // C7: the same pitch class an octave down, C6
  bot(s, 3, 1.0, 76);  // E5 is a bottle
  std::vector<Command> moves = plan(s).of(Type::MoveAt);
  CHECK(moves.size() == 3);
  CHECK(moves[0].target_steps == 1200 && moves[1].target_steps == 46000);
  CHECK(moves[2].target_steps == 14000);
}

static void test_planner_moves_a_too_fast_note_to_the_next_grid_point() {
  // C5 to D5 takes 0.315 s; half a beat at 120 bpm is 0.25 s, so D5 waits a quarter beat.
  MidiScore s = duet_score(120);
  bot(s, 1, 1.0, 72);
  bot(s, 1, 1.5, 74);
  std::vector<Command> strikes = plan(s).of(Type::StrikeAt);
  CHECK(strikes.size() == 2 && strikes[1].t_us - strikes[0].t_us == 375000);
}

static void test_planner_drops_a_note_it_cannot_reach() {
  // C6 a quarter beat after C5 at 120 bpm: the carriage needs over a second, too far to
  // move it; one drop in five notes is not enough to slow the piece down.
  MidiScore s = duet_score(120);
  for (int beat = 1; beat <= 4; ++beat) bot(s, 1, beat, 72);
  bot(s, 1, 4.25, 84);
  SongLines song = plan(s);
  CHECK(song.of(Type::StrikeAt).size() == 4);
  CHECK(song.of(Type::MoveAt).size() == 1);  // only from home: it never goes to C6
}

static void test_planner_drops_strikes_over_the_duty_limit() {
  // G5 at full force every 0.125 s: the solenoid may be on 20% of any 10 s, which is 66
  // pulses of 30 ms.
  MidiScore s = duet_score(120);
  for (int i = 0; i < 120; ++i) bot(s, 1 + i / 16, 1 + (i % 16) * 0.25, 79, 127);
  std::vector<Command> strikes = plan(s).of(Type::StrikeAt);
  CHECK(strikes.size() < 120);
  for (size_t i = 0; i < strikes.size(); ++i) {
    CHECK(strikes[i].pulse_us == 30000);
    size_t in_window = 0;
    for (size_t j = i; j < strikes.size() && strikes[j].t_us - strikes[i].t_us < 10000000; ++j)
      ++in_window;
    CHECK(in_window <= 66);
  }
}

static void test_planner_slows_down_rather_than_drop_many_notes() {
  // A scale in half beats at 120 bpm: every step comes too soon, and moving them drops
  // too many, so the piece plays at the tempo that fits them all: 95 bpm.
  MidiScore s = duet_score(120);
  const uint8_t scale[] = {72, 74, 76, 77, 79, 81, 83, 84};
  for (int i = 0; i < 8; ++i) bot(s, 1 + i / 8, 1 + (i % 8) * 0.5, scale[i]);
  SongLines song = plan(s);
  std::vector<Command> strikes = song.of(Type::StrikeAt);
  CHECK(strikes.size() == 8);
  for (size_t i = 1; i < strikes.size(); ++i) {
    int64_t gap = strikes[i].t_us - strikes[i - 1].t_us;
    CHECK(gap >= 315789 && gap <= 315790);  // half a beat at 95 bpm
  }
  CHECK(song.of(Type::LedFrameAt)[2].t_us - song.of(Type::LedFrameAt)[0].t_us == 631579);
}

static void test_planner_lights_the_keys_at_both_ends_of_the_keyboard() {
  MidiScore s = duet_score(100);
  human(s, 1, 1.0, 21);   // A0
  human(s, 1, 3.0, 108);  // C8
  std::vector<Command> keys;
  for (const Command& c : plan(s).of(Type::LedFrameAt))
    if (c.count != 176) keys.push_back(c);
  // Each key: a dim cue a beat ahead, off, white while it sounds, off.
  CHECK(keys.size() == 8);
  for (const Command& c : keys) {
    bool low = c.first == 1 && c.count == 2;
    bool high = c.first == 174 && c.count == 2;  // the strip's last two LEDs
    CHECK(low || high);
  }
  CHECK(keys[0].rgb[0] == 40 && keys[1].rgb[0] == 0 && keys[2].rgb[0] == 255);
  CHECK(keys[1].t_us == keys[2].t_us);  // at the same time, the dim cue's end comes first
  CHECK(plan_refusal([] {
          MidiScore off = duet_score(100);
          human(off, 1, 2.0, 109);
          human(off, 1, 1.0, 20);  // the first in time is the one named
          return off;
        }()) == "key 20 is not on the keyboard");
}

static void test_planner_refuses_what_the_rig_cannot_store_or_play() {
  MidiScore s = duet_score(200);
  for (int i = 0; i < 1001; ++i) human(s, 1 + i / 4, 1 + i % 4, 60);
  CHECK(plan_refusal(s) == "4012 commands; a stored song holds at most 4000");
  static constexpr Channel kNoLeds[] = {{ChannelKind::CarriageStriker, 0}};
  MidiScore one = duet_score(100);
  bot(one, 1, 1.0, 72);
  CHECK(plan_refusal(one, Channels{kNoLeds, 1}) == "the rig has no channel for: led_strip");
}

// The planner module, as a board installs it in the device API.
static Bytes two_tracks() {  // the bot's C5 D5 E5, the pianist's C3: a quarter each
  Bytes melody, bass;
  for (uint8_t p : {72, 74, 76}) melody.insert(melody.end(), {0x00, 0x90, p, 80, 0x83, 0x60, 0x80, p, 0});
  bass.insert(bass.end(), {0x00, 0x91, 48, 70, 0x83, 0x60, 0x81, 48, 0});
  return smf({melody, bass});
}

static void test_the_api_plans_a_midi_file_with_the_planner_installed() {
  Rig r;
  MemorySettingsStore settings;
  Api api(r.dev, settings);
  Bytes file = two_tracks();
  CHECK(api.begin_upload("/api/songs/3/midi", "Three notes").body ==
        R"({"error":"this board has no MIDI planner"})");

  MidiPlanner planner(r.dev, kBottles, kPiano88);
  api.install_planner(planner);
  CHECK(api.begin_upload("/api/songs/3/midi", "Three notes").status == 200);
  for (size_t at = 0; at < file.size(); at += 5)  // in pieces, as a web server hands it over
    api.upload_data(reinterpret_cast<const char*>(file.data()) + at,
                    std::min<size_t>(5, file.size() - at));
  Response planned = api.end_upload();
  CHECK(planned.status == 200 && planned.body == R"({"ok":true,"warnings":[]})");
  CHECK(r.store.has(3) && r.store.title(3) == "Three notes");

  CHECK(api.handle("POST", "/api/songs/3/play", "", r.hal.now_us).status == 200);
  r.run_until(12000000);
  CHECK(r.strikes() == 3 && !r.out.has("fault"));  // the bot's three notes

  // Refused, and the stored song stays: not MIDI, a bad title, a key off the keyboard.
  CHECK(api.begin_upload("/api/songs/3/midi", "x").status == 200);
  api.upload_data("not a midi file", 15);
  CHECK(api.end_upload().status == 400);
  CHECK(api.begin_upload("/api/songs/3/midi", "two\nlines").status == 400);
  Bytes low = smf({{0x00, 0x90, 72, 80, 0x83, 0x60, 0x80, 72, 0},
                   {0x00, 0x91, 10, 70, 0x83, 0x60, 0x81, 10, 0}});
  CHECK(api.begin_upload("/api/songs/3/midi", "low").status == 200);
  api.upload_data(reinterpret_cast<const char*>(low.data()), low.size());
  CHECK(api.end_upload().body == R"({"error":"key 10 is not on the keyboard"})");
  Bytes huge(kMaxMidiBytes + 1, 0);
  CHECK(api.begin_upload("/api/songs/3/midi", "huge").status == 200);
  api.upload_data(reinterpret_cast<const char*>(huge.data()), huge.size());
  CHECK(api.end_upload().status == 413);
  CHECK(r.store.title(3) == "Three notes" && !r.dev.writing_song());
}

int main() {
  test_parse();
  test_queue_orders_by_time();
  test_home_move_strike();
  test_strike_before_arrival_is_refused();
  test_safety_rules();
  test_duty_cycle_limit();
  test_duty_cannot_be_bypassed_with_short_pulses();
  test_greeting_hello_then_channels_and_oversize_is_rejected();
  test_time_ping();
  test_commands_must_name_a_channel_of_their_kind();
  test_midi_notes_play_and_are_silenced_when_the_hub_goes_quiet();
  test_midi_notes_off_and_estop_and_boards_without_midi();
  test_upload_then_play_from_memory();
  test_a_song_keeps_its_title();
  test_a_key_is_never_read_from_inside_a_value();
  test_a_bad_song_is_refused_whole();
  test_a_stalled_upload_is_dropped();
  test_the_button_plays_the_next_song_and_stops();
  test_stop_clears_what_the_hub_queued();
  test_no_watchdog_stop_while_playing_from_memory();
  test_playing_from_memory_keeps_the_rig_safe();
  test_the_api_reports_the_device_and_plays_its_songs();
  test_the_api_refuses_unknown_paths_and_wrong_methods();
  test_the_api_stores_a_song_file();
  test_the_api_refuses_a_bad_song_file_whole();
  test_the_api_plans_a_midi_file_with_the_planner_installed();
  test_json_objects_of_strings_and_lists();
  test_settings_are_saved_and_the_password_never_leaves();
  test_bad_settings_are_refused_and_nothing_is_saved();
  test_midi_running_status_and_note_on_releases();
  test_midi_truncated_or_malformed_is_refused();
  test_midi_tracks_by_mean_pitch();
  test_midi_named_tracks_win_over_pitch();
  test_midi_one_track_is_split_by_skyline();
  test_midi_warns_of_what_a_score_cannot_hold();
  test_planner_counts_in_then_plays_in_time_order();
  test_planner_folds_notes_onto_bottles();
  test_planner_moves_a_too_fast_note_to_the_next_grid_point();
  test_planner_drops_a_note_it_cannot_reach();
  test_planner_drops_strikes_over_the_duty_limit();
  test_planner_slows_down_rather_than_drop_many_notes();
  test_planner_lights_the_keys_at_both_ends_of_the_keyboard();
  test_planner_refuses_what_the_rig_cannot_store_or_play();
  if (failures) {
    std::printf("%d check(s) failed\n", failures);
    return 1;
  }
  std::printf("firmware core: all checks passed\n");
  return 0;
}
