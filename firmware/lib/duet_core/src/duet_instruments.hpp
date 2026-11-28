// The instruments the planner plans for, as the Hub's instrument files describe them
// (src/duet/profiles/*.yaml). tools/embed_instruments.py compiles them in from those
// files (the generated, committed duet_instrument_data.hpp), so no fact is typed twice.
#pragma once
#include <cstddef>
#include <cstdint>

namespace duet {

// One note of a carriage-striker bot: what it sounds, and where the carriage stops.
struct CarriageNote {
  uint8_t midi;   // its name
  double hz;      // as measured
  int32_t steps;  // carriage position
};

// An instrument played by a carriage-striker bot (duet.profile.RobotProfile).
struct CarriageInstrument {
  const char* id;
  const CarriageNote* notes;  // by pitch, low to high
  size_t note_count;
  double tolerance_cents;  // how far a note may sound from its name and still play it
  // Kinematics.
  double steps_per_mm, v_max_mm_s, a_max_mm_s2, settle_ms;
  // v_max_mm_s and a_max_mm_s2 as the Hub writes them in a move_at (Python's repr).
  const char* v_max_json;
  const char* a_max_json;
  // Striker.
  int32_t pulse_min_us, pulse_max_us;
  double recovery_ms, latency_ms, duty_limit, duty_window_s;
};

// A keyboard played by a person who follows an LED strip (duet.profile.KeyboardProfile).
struct KeyboardInstrument {
  const char* id;
  uint8_t low, high;  // its range, MIDI numbers
  double leds_per_m, white_key_mm, first_led_mm;
};

constexpr bool same_id(const char* a, const char* b) {
  while (*a && *a == *b) ++a, ++b;
  return *a == *b;
}

// Where the instrument with this id is among `all`, or -1: usable in a static_assert, so
// a board's PROFILE_ID that names no compiled-in instrument does not build.
template <class Instrument, size_t N>
constexpr int instrument_index(const Instrument (&all)[N], const char* id) {
  for (size_t i = 0; i < N; ++i)
    if (same_id(all[i].id, id)) return static_cast<int>(i);
  return -1;
}

}  // namespace duet
