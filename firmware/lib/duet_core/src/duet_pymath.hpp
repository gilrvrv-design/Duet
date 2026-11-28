// Python's float arithmetic where it differs from C's, and the Hub's score timing built
// on it, for code that must give the Hub's results to the last bit (the MIDI reader, the
// planner). Internal to the core.
#pragma once
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

namespace duet {

// Python's round(x, digits): the decimal correctly rounded from x's exact value, ties
// to even, read back as a double. printf's %f and strtod do just that (glibc, newlib).
inline double py_round(double x, int digits) {
  char buf[48];  // ample: positions stay below 2^30 beats, tempos below 2^28 bpm
  std::snprintf(buf, sizeof buf, "%.*f", digits, x);
  return std::strtod(buf, nullptr);
}

// Python's round(x): to the nearest whole number, ties to even (CPython's
// float.__round__ without digits, step for step).
inline int64_t py_round(double x) {
  double whole = std::round(x);
  if (std::fabs(x - whole) == 0.5) whole = 2.0 * std::round(x / 2.0);
  return static_cast<int64_t>(whole);
}

// Python's x // w for positive floats (CPython's _float_div_mod), which can differ from
// floor(x / w) when the quotient rounds to a whole number.
inline double py_floor_div(double x, double w) {
  double div = (x - std::fmod(x, w)) / w;
  double whole = std::floor(div);
  return div - whole > 0.5 ? whole + 1.0 : whole;
}

constexpr double kEpsilon = 1e-9;  // duet.timing.EPSILON

struct BarBeat {
  int32_t bar;  // 1-based
  double beat;  // 1-based
};

// duet.timing.bar_and_beat: the bar and beat of a 0-based beat index (not negative).
inline BarBeat bar_and_beat(double index, int beats_per_bar) {
  double bar = py_floor_div(index + kEpsilon, beats_per_bar);
  double beat = index - bar * beats_per_bar;
  if (std::fabs(beat) < kEpsilon) beat = 0.0;
  return {static_cast<int32_t>(bar) + 1, py_round(beat + 1, 6)};
}

}  // namespace duet
