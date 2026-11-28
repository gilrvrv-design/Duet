#include "duet_protocol.hpp"

#include "duet_config.hpp"
#include "duet_json.hpp"
#include "duet_features.hpp"

#include <cinttypes>
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

bool get_ch(const char* json, Command& out) {
  int64_t ch = 0;
  if (!get_int(json, "ch", ch)) return false;
  out.ch = static_cast<int32_t>(ch);
  return true;
}

bool type_is(const char* json, const char* name) {
  const char* p = find_key(json, "type");
  if (!p || *p != '"') return false;
  size_t len = std::strlen(name);
  return std::strncmp(p + 1, name, len) == 0 && p[1 + len] == '"';
}

}  // namespace

bool parse(const char* json, Command& out) {
  out = Command{};
  int64_t i = 0;
  get_int(json, "seq", out.seq);
  if (type_is(json, "home")) {
    out.type = Type::Home;
  } else if (type_is(json, "heartbeat")) {
    out.type = Type::Heartbeat;
  } else if (type_is(json, "estop")) {
    out.type = Type::Estop;
  } else if (type_is(json, "song")) {
    int64_t slot = 0, lines = 0;
    if (!get_int(json, "slot", slot) || !get_int(json, "lines", lines)) return false;
    out.slot = static_cast<int32_t>(slot);
    out.lines = static_cast<int32_t>(lines);
    out.type = Type::Song;
  } else if (type_is(json, "play")) {
    int64_t slot = 0;
    if (!get_int(json, "slot", slot)) return false;
    out.slot = static_cast<int32_t>(slot);
    out.type = Type::Play;
  } else if (type_is(json, "stop")) {
    out.type = Type::Stop;
  } else if (type_is(json, "greet")) {
    out.type = Type::Greet;
  } else if (type_is(json, "time_ping")) {
    if (!get_int(json, "t1", out.t1)) return false;
    out.type = Type::TimePing;
  } else if (type_is(json, "move_at")) {
    if (!get_ch(json, out) || !get_int(json, "t_us", out.t_us) ||
        !get_int(json, "target_steps", i) ||
        !get_float(json, "v_max_mm_s", out.v_max_mm_s) ||
        !get_float(json, "a_max_mm_s2", out.a_max_mm_s2))
      return false;
    out.target_steps = static_cast<int32_t>(i);
    out.type = Type::MoveAt;
  } else if (type_is(json, "strike_at")) {
    if (!get_ch(json, out) || !get_int(json, "t_us", out.t_us) || !get_int(json, "pulse_us", i))
      return false;
    out.pulse_us = static_cast<int32_t>(i);
    out.type = Type::StrikeAt;
  } else if (type_is(json, "note_at")) {
    int64_t midi = 0, pitch = 0, vel = 0;
    if (!get_ch(json, out) || !get_int(json, "t_us", out.t_us) || !get_int(json, "midi", midi) ||
        !get_int(json, "pitch", pitch) || !get_int(json, "vel", vel))
      return false;
    if (midi < 0 || midi > 15 || pitch < 0 || pitch > 127 || vel < 0 || vel > 127) return false;
    out.midi = static_cast<uint8_t>(midi);
    out.pitch = static_cast<uint8_t>(pitch);
    out.vel = static_cast<uint8_t>(vel);
    out.type = Type::NoteAt;
  } else if (type_is(json, "led_frame_at")) {
    int64_t first = 0, count = 0;
    if (!get_ch(json, out) || !get_int(json, "t_us", out.t_us) ||
        !get_int(json, "first", first) || !get_int(json, "count", count))
      return false;
    const char* p = find_key(json, "rgb");
    if (!p || *p != '[') return false;
    char* end = nullptr;
    ++p;
    for (int c = 0; c < 3; ++c) {
      long v = std::strtol(p, &end, 10);
      if (end == p || v < 0 || v > 255) return false;
      out.rgb[c] = static_cast<uint8_t>(v);
      p = end;
      while (*p == ',' || *p == ' ') ++p;
    }
    out.first = static_cast<int32_t>(first);
    out.count = static_cast<int32_t>(count);
    out.type = Type::LedFrameAt;
  } else {
    return false;
  }
  return true;
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
