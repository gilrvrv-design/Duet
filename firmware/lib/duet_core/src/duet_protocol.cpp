#include "duet_protocol.hpp"

#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace duet {
namespace {

// Find the value that follows "key": in a flat JSON object.
const char* find_value(const char* json, const char* key) {
  char pattern[40];
  std::snprintf(pattern, sizeof pattern, "\"%s\"", key);
  const char* p = std::strstr(json, pattern);
  if (!p) return nullptr;
  p += std::strlen(pattern);
  while (*p == ' ' || *p == ':') ++p;
  return p;
}

bool get_int(const char* json, const char* key, int64_t& out) {
  const char* p = find_value(json, key);
  if (!p) return false;
  char* end = nullptr;
  long long v = std::strtoll(p, &end, 10);
  if (end == p) return false;
  out = v;
  return true;
}

bool get_float(const char* json, const char* key, float& out) {
  const char* p = find_value(json, key);
  if (!p) return false;
  char* end = nullptr;
  float v = std::strtof(p, &end);
  if (end == p) return false;
  out = v;
  return true;
}

bool type_is(const char* json, const char* name) {
  const char* p = find_value(json, "type");
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
  } else if (type_is(json, "time_ping")) {
    if (!get_int(json, "t1", out.t1)) return false;
    out.type = Type::TimePing;
  } else if (type_is(json, "move_at")) {
    if (!get_int(json, "t_us", out.t_us) || !get_int(json, "target_steps", i) ||
        !get_float(json, "v_max_mm_s", out.v_max_mm_s) ||
        !get_float(json, "a_max_mm_s2", out.a_max_mm_s2))
      return false;
    out.target_steps = static_cast<int32_t>(i);
    out.type = Type::MoveAt;
  } else if (type_is(json, "strike_at")) {
    if (!get_int(json, "t_us", out.t_us) || !get_int(json, "pulse_us", i)) return false;
    out.pulse_us = static_cast<int32_t>(i);
    out.type = Type::StrikeAt;
  } else if (type_is(json, "led_frame_at")) {
    int64_t first = 0, count = 0;
    if (!get_int(json, "t_us", out.t_us) || !get_int(json, "first", first) ||
        !get_int(json, "count", count))
      return false;
    const char* p = find_value(json, "rgb");
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

int write_hello(char* buf, size_t n, const char* device_id, const char* profile) {
  return std::snprintf(buf, n,
                       "{\"type\":\"hello\",\"seq\":0,\"protocol\":1,\"device_id\":\"%s\","
                       "\"profile\":\"%s\"}",
                       device_id, profile);
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

}  // namespace duet
