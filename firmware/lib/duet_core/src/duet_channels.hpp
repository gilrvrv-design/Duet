// What a board can drive, one channel each: a carriage with a striker, an LED strip, ...
// The board lists its channels (board.h); the device describes them on connect; every
// timed command names its channel, and a command for a channel that does not exist or
// is of the wrong kind is refused.
#pragma once
#include <cstddef>
#include <cstdint>

namespace duet {

enum class ChannelKind : uint8_t {
  CarriageStriker,  // move_at, strike_at
  LedStrip,         // led_frame_at
};

struct Channel {
  ChannelKind kind;
  int32_t count;  // LED strip: number of LEDs; otherwise 0
};

struct Channels {
  const Channel* items;
  size_t count;

  bool has(int32_t ch, ChannelKind kind) const {
    return ch >= 0 && static_cast<size_t>(ch) < count && items[ch].kind == kind;
  }
};

constexpr const char* kind_name(ChannelKind kind) {
  return kind == ChannelKind::CarriageStriker ? "carriage_striker" : "led_strip";
}

// The executor drives one carriage: a board may have at most one carriage channel.
template <size_t N>
constexpr bool at_most_one_carriage(const Channel (&channels)[N]) {
  size_t carriages = 0;
  for (const Channel& c : channels) carriages += c.kind == ChannelKind::CarriageStriker;
  return carriages <= 1;
}

}  // namespace duet
