// Runs the firmware core against the simulated hardware for a stream of messages, so
// the Hub's tests can check that firmware and Hub agree (spec §9.5 contract tests).
//
// stdin:  one JSON message per line
// stdout: one JSON event per line ({"event":"strike","t_us":..,"position":..} and so on)
//
// Messages are delivered `lookahead_us` before their own time, like the conductor does,
// and a heartbeat arrives every `heartbeat_us`, like the Hub's DeviceGateway sends.
//
// --midi <file>: the duet the core makes of a MIDI file, as one JSON object (or
// {"error": reason}, exit status 1), for tests/test_midi_contract.py.
//
// --song <file> [instrument]: the song the planner makes of a MIDI file for the rig (its
// carriage instrument, rig.h's PROFILE_ID unless named, and its KEYBOARD_ID), one command per
// line (or {"error": reason}, exit status 1), for tests/test_planner_contract.py.
#include <algorithm>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

#include "duet_executor.hpp"
#include "duet_features.hpp"
#include "duet_json.hpp"
#include "duet_midi.hpp"
#include "duet_planner.hpp"
#include "duet_sim_hal.hpp"
#include "duet_instrument_data.hpp"  // generated from the Hub's instrument files
#include "rig.h"

using namespace duet;

// The rig's channels, exactly as every board has them (src/rig.h).
static constexpr const Channels& kRig = BOARD_CHANNELS;

struct Print : Sink {
  void send(const char* json) override {
    if (std::string(json).find("\"fault\"") != std::string::npos ||
        std::string(json).find("\"status\":\"error") != std::string::npos)
      std::printf("{\"event\":\"fault\",\"message\":%s}\n", json);
  }
};

static constexpr int kRigInstrument = instrument_index(kCarriageInstruments, PROFILE_ID);
static_assert(kRigInstrument >= 0, "rig.h's PROFILE_ID names no carriage instrument");
static constexpr int kPiano = instrument_index(kKeyboardInstruments, KEYBOARD_ID);
static_assert(kPiano >= 0, "the rig's keyboard is not among the instruments");

static int refuse(const std::string& why) {
  std::printf("{\"error\":%s}\n", json_string(why).c_str());
  return 1;
}

static bool read_file(const char* path, MidiScore& score, std::string& why) {
  std::ifstream file(path, std::ios::binary);
  std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(file)), {});
  return read_midi(bytes.data(), bytes.size(), score, why);
}

static int print_midi(const char* path) {
  MidiScore score;
  std::string why;
  if (!read_file(path, score, why)) return refuse(why);
  // %.17g: every double reads back exactly.
  std::printf("{\"tempo_bpm\":%.17g,\"time_signature\":[%d,%d],\"warnings\":[", score.tempo_bpm,
              score.beats_per_bar, score.beat_unit);
  for (size_t i = 0; i < score.warnings.size(); ++i)
    std::printf("%s%s", i ? "," : "", json_string(score.warnings[i]).c_str());
  std::printf("],\"events\":[");
  for (size_t i = 0; i < score.events.size(); ++i) {
    const ScoreEvent& e = score.events[i];
    std::printf("%s{\"part\":\"%s\",\"bar\":%d,\"beat\":%.17g,\"dur\":%.17g,\"pitch\":%d,"
                "\"vel\":%d}",
                i ? "," : "", part_name(e.part), static_cast<int>(e.bar), e.beat, e.dur, e.pitch,
                e.vel);
  }
  std::printf("]}\n");
  return 0;
}

struct PrintLines : SongSink {
  void line(const char* json) override { std::printf("%s\n", json); }
};

static int print_song(const char* path, const char* instrument) {
  int robot = instrument_index(kCarriageInstruments, instrument);
  if (robot < 0) return refuse(std::string("no carriage instrument ") + instrument);
  MidiScore score;
  std::string why;
  PrintLines out;
  const KeyboardInstrument& piano = kKeyboardInstruments[kPiano];
  if (!read_file(path, score, why) ||
      !plan_song(score, kCarriageInstruments[robot], piano, kRig, out, why))
    return refuse(why);
  return 0;
}

int main(int argc, char** argv) {
  if (argc > 2 && std::string(argv[1]) == "--midi") return print_midi(argv[2]);
  if (argc > 2 && std::string(argv[1]) == "--song")
    return print_song(argv[2], argc > 3 ? argv[3] : PROFILE_ID);
  if (argc > 1 && std::string(argv[1]) == "--channels") {  // the rig's channels and limits
    char buf[kMaxMessage + 1];
    for (size_t ch = 0; ch < kRig.count; ++ch) {
      write_channel(buf, sizeof buf, static_cast<int>(ch), kRig.items[ch], Config{});
      std::printf("%s\n", buf);
    }
    return 0;
  }
  if (argc > 1 && std::string(argv[1]) == "--features") {  // every feature it knows
    for (const FeatureName& f : kFeatureNames) std::printf("%s\n", f.name);
    return 0;
  }
  int64_t lookahead = argc > 1 ? std::atoll(argv[1]) : 500000;
  int64_t heartbeat = argc > 2 ? std::atoll(argv[2]) : 250000;  // 0 = no heartbeats
  std::vector<std::pair<int64_t, std::string>> inbox;
  std::string line;
  int64_t first = INT64_MAX, last = 0;
  while (std::getline(std::cin, line)) {
    if (line.empty()) continue;
    Command c;
    parse(line.c_str(), c);
    int64_t t = c.timed() ? c.t_us : 0;
    if (c.timed()) {
      first = std::min(first, c.t_us);
      last = std::max(last, c.t_us);
    }
    inbox.emplace_back(t, line);
  }
  if (inbox.empty()) return 0;
  int64_t start = first == INT64_MAX ? 0 : first - lookahead - 1000;
  for (auto& m : inbox) m.first = m.first ? std::max(start, m.first - lookahead) : start;
  std::stable_sort(inbox.begin(), inbox.end(),
                   [](auto& a, auto& b) { return a.first < b.first; });

  SimHal hal;
  Print out;
  Executor ex(hal, out, kRig);
  size_t next = 0;
  for (hal.now_us = start; hal.now_us <= last + 1000000; hal.now_us += 50) {
    while (next < inbox.size() && inbox[next].first <= hal.now_us)
      ex.on_message(inbox[next++].second.c_str(), hal.now_us);
    if (heartbeat > 0 && (hal.now_us - start) % heartbeat == 0)
      ex.on_message("{\"type\":\"heartbeat\",\"seq\":0}", hal.now_us);
    ex.poll(hal.now_us);
  }
  for (auto& e : hal.events) {
    if (e.kind[0] == 's')
      std::printf("{\"event\":\"strike\",\"t_us\":%" PRId64 ",\"position\":%d}\n", e.t_us, e.a);
    else if (e.kind[0] == 'l')
      std::printf("{\"event\":\"led\",\"t_us\":%" PRId64 ",\"first\":%d,\"count\":%d}\n", e.t_us,
                  e.a, e.b);
  }
  const Stats& s = ex.stats();
  std::printf("{\"event\":\"stats\",\"executed\":%u,\"late\":%u,\"faults\":%u}\n", s.executed,
              s.late, s.faults);
  return 0;
}
