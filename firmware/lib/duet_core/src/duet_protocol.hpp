// Wire messages (spec §5.10 FR-D3), as flat JSON objects, one per WebSocket frame or
// serial line. Times are microseconds on the device's own clock: the Hub converts.
#pragma once
#include <cstddef>
#include <cstdint>

namespace duet {

// Longest message either side may send, in bytes (the Hub checks this too:
// duet.protocol.MAX_MESSAGE_BYTES).
constexpr size_t kMaxMessage = 255;

struct Config;

enum class Type : uint8_t {
  Invalid,
  Home,
  MoveAt,
  StrikeAt,
  LedFrameAt,
  Estop,
  TimePing,
  Heartbeat,  // proof of life from the Hub; keeps the watchdog quiet, never acked
  Song,       // the next `lines` timed commands are a song to store in `slot`
  Play,       // play the song stored in `slot` from memory
  Stop,       // stop playing from memory
};

struct Command {
  Type type = Type::Invalid;
  int64_t seq = 0;
  int64_t t_us = 0;
  int32_t target_steps = 0;
  float v_max_mm_s = 0;
  float a_max_mm_s2 = 0;
  int32_t pulse_us = 0;
  int32_t first = 0;
  int32_t count = 0;
  uint8_t rgb[3] = {0, 0, 0};
  int64_t t1 = 0;
  int32_t slot = 0;   // song, play
  int32_t lines = 0;  // song

  bool timed() const {
    return type == Type::MoveAt || type == Type::StrikeAt || type == Type::LedFrameAt;
  }
};

// Parse one message. Returns false (and type Invalid) if it is not a known message.
bool parse(const char* json, Command& out);

// Writers return the number of characters written (snprintf semantics).
// hello carries the safety limits the firmware enforces, so the Hub can check them
// against the instrument profile it plans with.
int write_hello(char* buf, size_t n, const char* device_id, const char* profile,
                const Config& cfg);
int write_ack(char* buf, size_t n, int64_t seq, const char* status);
int write_pong(char* buf, size_t n, int64_t seq, int64_t t1, int64_t t2, int64_t t3);
int write_fault(char* buf, size_t n, const char* code, const char* detail);
int write_telemetry(char* buf, size_t n, bool homed, int32_t position, size_t queued);

}  // namespace duet
