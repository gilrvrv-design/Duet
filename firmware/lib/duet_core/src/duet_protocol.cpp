#include "duet_protocol.hpp"

#include "duet_config.hpp"
#include "duet_json.hpp"
#include "duet_features.hpp"

#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace duet {
namespace {

bool get_int(const char* json, const char* key, int64_t& out) {
  const char* p = find_key(json, key);
  if (!p) return false;
  char* end = nullptr;
  long long v = std::strtoll(p, &end, 10);
  if (end == p) return false;
  out = v;
  return true;
}

bool get_float(const char* json, const char* key, float& out) {
  const char* p = find_key(json, key);
  if (!p) return false;
  char* end = nullptr;
  float v = std::strtof(p, &end);
  if (end == p) return false;
  out = v;
  return true;
}

bool type_is(const char* json, const char* name) {
  const char* p = find_key(json, "type");
  if (!p || *p != '"') return false;
  size_t len = std::strlen(name);
  return std::strncmp(p + 1, name, len) == 0 && p[1 + len] == '"';
}

// A whole number within [lo, hi].
bool get_in(const char* json, const char* key, int64_t lo, int64_t hi, int64_t& out) {
  return get_int(json, key, out) && out >= lo && out <= hi;
}

bool get_i32(const char* json, const char* key, int32_t& out) {
  int64_t v = 0;
  if (!get_in(json, key, INT32_MIN, INT32_MAX, v)) return false;
  out = static_cast<int32_t>(v);
  return true;
}

bool get_u8(const char* json, const char* key, int64_t hi, uint8_t& out) {
  int64_t v = 0;
  if (!get_in(json, key, 0, hi, v)) return false;
  out = static_cast<uint8_t>(v);
  return true;
}

// A timed command: its channel and its time.
bool timed(const char* json, Command& c) {
  return get_i32(json, "ch", c.ch) && get_int(json, "t_us", c.t_us);
}

bool rgb(const char* json, uint8_t (&out)[3]) {
  const char* p = find_key(json, "rgb");
  if (!p || *p != '[') return false;
  ++p;
  for (uint8_t& c : out) {
    char* end = nullptr;
    long v = std::strtol(p, &end, 10);
    if (end == p || v < 0 || v > 255) return false;
    c = static_cast<uint8_t>(v);
    p = end;
    while (*p == ',' || *p == ' ') ++p;
  }
  return true;
}

bool no_fields(const char*, Command&) { return true; }

bool song(const char* j, Command& c) {
  return get_i32(j, "slot", c.slot) && get_i32(j, "lines", c.lines);
}

bool play(const char* j, Command& c) { return get_i32(j, "slot", c.slot); }

bool time_ping(const char* j, Command& c) { return get_int(j, "t1", c.t1); }

bool move_at(const char* j, Command& c) {
  return timed(j, c) && get_i32(j, "target_steps", c.target_steps) &&
         get_float(j, "v_max_mm_s", c.v_max_mm_s) && get_float(j, "a_max_mm_s2", c.a_max_mm_s2);
}

bool strike_at(const char* j, Command& c) {
  return timed(j, c) && get_i32(j, "pulse_us", c.pulse_us);
}

bool note_at(const char* j, Command& c) {
  return timed(j, c) && get_u8(j, "midi", 15, c.midi) && get_u8(j, "pitch", 127, c.pitch) &&
         get_u8(j, "vel", 127, c.vel);
}

bool led_frame_at(const char* j, Command& c) {
  return timed(j, c) && get_i32(j, "first", c.first) && get_i32(j, "count", c.count) &&
         rgb(j, c.rgb);
}

struct Kind {
  const char* name;
  Type type;
  bool (*fields)(const char* json, Command& out);
};

constexpr Kind KINDS[] = {
    {"home", Type::Home, no_fields},
    {"heartbeat", Type::Heartbeat, no_fields},
    {"estop", Type::Estop, no_fields},
    {"stop", Type::Stop, no_fields},
    {"greet", Type::Greet, no_fields},
    {"song", Type::Song, song},
    {"play", Type::Play, play},
    {"time_ping", Type::TimePing, time_ping},
    {"move_at", Type::MoveAt, move_at},
    {"strike_at", Type::StrikeAt, strike_at},
    {"note_at", Type::NoteAt, note_at},
    {"led_frame_at", Type::LedFrameAt, led_frame_at},
};

}  // namespace

bool parse(const char* json, Command& out) {
  out = Command{};
  get_int(json, "seq", out.seq);
  for (const Kind& kind : KINDS) {
    if (!type_is(json, kind.name)) continue;
    out.type = kind.type;
    return kind.fields(json, out);
  }
  return false;
}

int write_hello(char* buf, size_t n, const Identity& id) {
  char features[kFeaturesJsonMax] = "";  // every name fits: see duet_features.hpp
  size_t used = 0;
  for (const FeatureName& f : kFeatureNames) {
    if (!(id.features & f.feature)) continue;
    used += std::snprintf(features + used, sizeof features - used, "%s\"%s\"",
                          used ? "," : "", f.name);
  }
  return std::snprintf(buf, n,
                       "{\"type\":\"hello\",\"seq\":0,\"protocol\":%d,\"device_id\":\"%s\","
                       "\"board\":\"%s\",\"profile\":\"%s\",\"features\":[%s],\"channels\":%u}",
                       kProtocol, id.device_id, id.board, id.profile, features,
                       static_cast<unsigned>(id.channels.count));
}

int write_channel(char* buf, size_t n, int ch, const Channel& channel, const Config& cfg) {
  if (channel.kind == ChannelKind::CarriageStriker) {
    return std::snprintf(buf, n,
                         "{\"type\":\"channel\",\"seq\":0,\"ch\":%d,\"kind\":\"%s\","
                         "\"steps_per_mm\":%.3f,\"travel_steps\":%d,\"duty_limit\":%.3f,"
                         "\"duty_window_us\":%lld,\"max_pulse_us\":%d}",
                         ch, kind_name(channel.kind), static_cast<double>(cfg.steps_per_mm),
                         static_cast<int>(cfg.travel_steps), static_cast<double>(cfg.duty_limit),
                         static_cast<long long>(cfg.duty_window_us),
                         static_cast<int>(cfg.max_pulse_us));
  }
  return std::snprintf(buf, n,
                       "{\"type\":\"channel\",\"seq\":0,\"ch\":%d,\"kind\":\"%s\","
                       "\"count\":%d}",
                       ch, kind_name(channel.kind), static_cast<int>(channel.count));
}

int write_ack(char* buf, size_t n, int64_t seq, const char* status) {
  return std::snprintf(buf, n, "{\"type\":\"ack\",\"seq\":%" PRId64 ",\"status\":\"%s\"}", seq,
                       status);
}

int write_pong(char* buf, size_t n, int64_t seq, int64_t t1, int64_t t2, int64_t t3) {
  return std::snprintf(buf, n,
                       "{\"type\":\"time_pong\",\"seq\":%" PRId64 ",\"t1\":%" PRId64
                       ",\"t2\":%" PRId64 ",\"t3\":%" PRId64 "}",
                       seq, t1, t2, t3);
}

int write_fault(char* buf, size_t n, const char* code, const char* detail) {
  return std::snprintf(buf, n,
                       "{\"type\":\"fault\",\"seq\":0,\"code\":\"%s\",\"detail\":\"%s\"}", code,
                       detail);
}

int write_telemetry(char* buf, size_t n, bool homed, int32_t position, size_t queued) {
  return std::snprintf(buf, n,
                       "{\"type\":\"telemetry\",\"seq\":0,\"homed\":%s,\"position\":%d,"
                       "\"queued\":%u}",
                       homed ? "true" : "false", static_cast<int>(position),
                       static_cast<unsigned>(queued));
}

}  // namespace duet
