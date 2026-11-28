// Runs the firmware core against the simulated hardware for a stream of messages, so
// the Hub's tests can check that firmware and Hub agree (spec §9.5 contract tests).
//
// stdin:  one JSON message per line
// stdout: one JSON event per line ({"event":"strike","t_us":..,"position":..} and so on)
//
// Messages are delivered `lookahead_us` before their own time, like the conductor does,
// and a heartbeat arrives every `heartbeat_us`, like the Hub's DeviceGateway sends.
#include <algorithm>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

#include "duet_executor.hpp"
#include "duet_features.hpp"
#include "duet_sim_hal.hpp"

using namespace duet;

// The rig's channels, as boards/*/board.h: 0 the carriage and striker, 1 the LED strip,
// 2 MIDI out.
static constexpr Channel kRigChannels[] = {{ChannelKind::CarriageStriker, 0},
                                           {ChannelKind::LedStrip, 176},
                                           {ChannelKind::MidiOut, 0}};
static constexpr Channels kRig{kRigChannels, 3};

struct Print : Sink {
  void send(const char* json) override {
    if (std::string(json).find("\"fault\"") != std::string::npos ||
        std::string(json).find("\"status\":\"error") != std::string::npos)
      std::printf("{\"event\":\"fault\",\"message\":%s}\n", json);
  }
};

int main(int argc, char** argv) {
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
