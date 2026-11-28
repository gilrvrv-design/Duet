#include "duet_planner.hpp"

#include <algorithm>
#include <array>
#include <cinttypes>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

#include "duet_protocol.hpp"
#include "duet_pymath.hpp"
#include "duet_songs.hpp"

// Each step names the Hub function it ports. The doubles must come out the same to the
// last bit, so every expression keeps Python's operations in Python's order.
namespace duet {
namespace {

constexpr double kMarginS = 0.010;    // duet.feasibility.DEFAULT_MARGIN_S
constexpr double kDutySlack = 1e-12;  // _check_duty
constexpr double kGridBeats = 0.25;   // duet.repair
constexpr double kMaxShiftBeats = 0.5;
constexpr double kMaxDropRatio = 0.2;
constexpr double kMinTempoBpm = 40.0;
constexpr int32_t kHomeSteps = 0;   // duet.plans.HOME_STEPS
constexpr double kLeadBeats = 1.0;  // led_plan's defaults
constexpr int kCountInBars = 1;
constexpr int kMidiNotes = 128;

// duet.plans' colours.
constexpr uint8_t kPreCue[] = {40, 40, 40};
constexpr uint8_t kPlayNow[] = {255, 255, 255};
constexpr uint8_t kCountIn[] = {0, 80, 255};
constexpr uint8_t kOff[] = {0, 0, 0};

// duet.timing: score positions to seconds at one tempo.
struct Meter {
  int beats_per_bar;
  double spb;  // seconds_per_beat

  explicit Meter(double tempo_bpm, int beats) : beats_per_bar(beats), spb(60.0 / tempo_bpm) {}
  double beats(const ScoreEvent& e) const {  // beat_index
    return static_cast<double>(int64_t{e.bar - 1} * beats_per_bar) + (e.beat - 1);
  }
  double seconds(const ScoreEvent& e) const { return beats(e) * spb; }
};

// round(seconds * 1_000_000), as build_messages times its messages.
int64_t us(double seconds) { return py_round(seconds * 1000000.0); }

double midi_to_hz(int midi) { return 440.0 * std::pow(2.0, (midi - 69) / 12.0); }

double cents_between(double hz_a, double hz_b) { return 1200.0 * std::log2(hz_b / hz_a); }

bool is_black_key(int midi) {
  int k = midi % 12;
  return k == 1 || k == 3 || k == 6 || k == 8 || k == 10;
}

// The carriage-striker bot (duet.profile.RobotProfile, duet.kinematics), with what the
// planner asks of it worked out once: each MIDI note's bottle, each fold, each interval.
class Robot {
 public:
  explicit Robot(const CarriageInstrument& inst)
      : inst_(inst), n_(inst.note_count), interval_(n_ * n_) {
    for (int midi = 0; midi < kMidiNotes; ++midi) bottle_[midi] = bottle_index(midi);
    for (int midi = 0; midi < kMidiNotes; ++midi)
      fold_[midi] = bottle_[midi] >= 0 ? static_cast<uint8_t>(midi) : fold_pitch(midi);
    for (size_t i = 0; i < n_; ++i)
      for (size_t j = 0; j < n_; ++j) interval_[i * n_ + j] = strike_interval_s(i, j);
  }

  int bottle(uint8_t midi) const { return bottle_[midi]; }  // -1: none sounds it
  uint8_t fold(uint8_t midi) const { return fold_[midi]; }
  double interval(int from, int to) const { return interval_[from * n_ + to]; }
  int32_t steps(int bottle) const { return inst_.notes[bottle].steps; }
  double latency_s() const { return inst_.latency_ms / 1000; }
  double duty_window_s() const { return inst_.duty_window_s; }
  double duty_limit_s() const { return inst_.duty_limit * inst_.duty_window_s; }

  // Striker.pulse_for_velocity
  int32_t pulse_us(uint8_t vel) const {
    int32_t low = inst_.pulse_min_us, high = inst_.pulse_max_us;
    return static_cast<int32_t>(
        py_round(low + static_cast<double>((high - low) * (vel - 1)) / 126));
  }

  // move_time_s: travel plus settle time between two carriage positions.
  double move_s(int32_t from, int32_t to) const {
    if (from == to) return 0.0;
    double distance = std::fabs((to - from) / inst_.steps_per_mm);  // travel_time_s
    double v = inst_.v_max_mm_s, a = inst_.a_max_mm_s2;
    double travel =
        distance <= std::pow(v, 2) / a ? 2.0 * std::sqrt(distance / a) : distance / v + v / a;
    return travel + inst_.settle_ms / 1000;
  }

 private:
  // bottle_index: the note nearest in measured pitch, if within the tolerance.
  int bottle_index(int midi) const {
    double target = midi_to_hz(midi);
    size_t best = 0;
    for (size_t i = 1; i < n_; ++i)  // the first of the nearest, as min() picks
      if (std::fabs(cents_between(target, inst_.notes[i].hz)) <
          std::fabs(cents_between(target, inst_.notes[best].hz)))
        best = i;
    bool near = std::fabs(cents_between(target, inst_.notes[best].hz)) <= inst_.tolerance_cents;
    return near ? static_cast<int>(best) : -1;
  }

  // _fold_pitch: the same pitch class in the nearest octave if a note has it, else the
  // nearest note; the lower of two as near.
  uint8_t fold_pitch(int midi) const {
    bool same_class = false;
    for (size_t i = 0; i < n_; ++i)
      same_class = same_class || inst_.notes[i].midi % 12 == midi % 12;
    int best = -1;
    for (size_t i = 0; i < n_; ++i) {
      int p = inst_.notes[i].midi;
      if (same_class && p % 12 != midi % 12) continue;
      if (best < 0 || std::abs(p - midi) < std::abs(best - midi) ||
          (std::abs(p - midi) == std::abs(best - midi) && p < best))
        best = p;
    }
    return static_cast<uint8_t>(best);
  }

  // strike_interval_s: the shortest time from a strike on bottle i to one on bottle j.
  double strike_interval_s(size_t i, size_t j) const {
    double pulse = inst_.pulse_max_us / 1000000.0;
    double recovery = inst_.recovery_ms / 1000;
    if (i == j) return std::max(recovery, pulse);
    return std::max(recovery, pulse + move_s(inst_.notes[i].steps, inst_.notes[j].steps));
  }

  const CarriageInstrument& inst_;
  size_t n_;
  std::array<int8_t, kMidiNotes> bottle_;
  std::array<uint8_t, kMidiNotes> fold_;
  std::vector<double> interval_;  // seconds, from * n_ + to
};

struct Span {
  int32_t first, count;
};

// The keyboard and its LED strip (duet.plans.led_span, led_count).
class Keys {
 public:
  explicit Keys(const KeyboardInstrument& kb) : kb_(kb), spans_(kb.high - kb.low + 1) {
    double w = kb.white_key_mm;
    int whites = 0;  // below the key
    for (int midi = kb.low; midi <= kb.high; ++midi) {
      double centre = is_black_key(midi) ? whites * w : (whites + 0.5) * w;
      double half = 7 * w / 12 / 2;
      double pitch_mm = 1000 / kb.leds_per_m;
      int64_t first = py_round((centre - half - kb.first_led_mm) / pitch_mm + 0.5);
      int64_t last = py_round((centre + half - kb.first_led_mm) / pitch_mm - 0.5);
      spans_[midi - kb.low] = {static_cast<int32_t>(std::max<int64_t>(first, 0)),
                               static_cast<int32_t>(std::max<int64_t>(1, last - first + 1))};
      whites += !is_black_key(midi);
    }
    double length = whites * w - kb.first_led_mm;
    total_ = static_cast<int32_t>(py_round(length * kb.leds_per_m / 1000));
  }

  bool contains(uint8_t midi) const { return kb_.low <= midi && midi <= kb_.high; }
  Span span(uint8_t midi) const { return spans_[midi - kb_.low]; }
  int32_t total() const { return total_; }

 private:
  const KeyboardInstrument& kb_;
  std::vector<Span> spans_;
  int32_t total_;
};

using Notes = std::vector<ScoreEvent>;  // a score's events, or its bot part alone
using Order = std::vector<uint16_t>;    // indices into them
static_assert(kMaxMidiNotes <= UINT16_MAX, "a score's events are counted in 16 bits");

// robot_strikes: the bot's notes a bottle sounds, by time, then score order.
Order strikes(const Notes& notes, const Robot& robot, const Meter& m) {
  Order order;
  order.reserve(notes.size());
  for (size_t i = 0; i < notes.size(); ++i)
    if (notes[i].part == DuoPart::Bot && robot.bottle(notes[i].pitch) >= 0)
      order.push_back(static_cast<uint16_t>(i));
  std::sort(order.begin(), order.end(), [&](uint16_t a, uint16_t b) {
    double ta = m.seconds(notes[a]), tb = m.seconds(notes[b]);
    return ta != tb ? ta < tb : a < b;
  });
  return order;
}

// _check_duty: calls found(i) for each strike that would keep the solenoid on longer
// than the duty limit allows over any window, counting the strikes before it as if
// those found were dropped.
template <class Found>
void check_duty(const Notes& notes, const Order& order, const Robot& robot, const Meter& m,
                Found found) {
  double window_s = robot.duty_window_s();
  double limit = robot.duty_limit_s();
  auto pulse = [&](uint16_t i) { return robot.pulse_us(notes[i].vel) / 1000000.0; };
  Order window;  // from `head`: the strikes in the window, oldest first
  window.reserve(order.size());
  size_t head = 0;
  double on_time = 0.0;
  for (uint16_t i : order) {
    double t = m.seconds(notes[i]);
    window.push_back(i);
    on_time += pulse(i);
    while (head < window.size() && m.seconds(notes[window[head]]) <= t - window_s)
      on_time -= pulse(window[head++]);
    if (on_time > limit + kDutySlack) {
      found(i);
      on_time -= pulse(window.back());
      window.pop_back();
    }
  }
}

void erase(Notes& notes, const std::vector<bool>& dropped) {
  size_t kept = 0;
  for (size_t i = 0; i < notes.size(); ++i)
    if (!dropped[i]) notes[kept++] = notes[i];
  notes.resize(kept);
}

// _fix_timing: a note that comes too soon after the one before moves to the next grid
// point if that is a small move, else is dropped. Returns how many were dropped.
size_t fix_timing(Notes& notes, const Robot& robot, const Meter& m) {
  Order order = strikes(notes, robot, m);
  // Among simultaneous notes, the highest (usually the melody) first.
  std::sort(order.begin(), order.end(), [&](uint16_t a, uint16_t b) {
    double ta = m.seconds(notes[a]), tb = m.seconds(notes[b]);
    if (ta != tb) return ta < tb;
    return notes[a].pitch != notes[b].pitch ? notes[a].pitch > notes[b].pitch : a < b;
  });
  std::vector<bool> dropped(notes.size());
  size_t drops = 0;
  int prev_bottle = -1;
  double prev_s = 0;
  for (uint16_t i : order) {
    ScoreEvent& e = notes[i];
    int bottle = robot.bottle(e.pitch);
    double t = m.seconds(e);
    if (prev_bottle < 0) {
      prev_bottle = bottle;
      prev_s = t;
      continue;
    }
    double earliest = prev_s + robot.interval(prev_bottle, bottle) + kMarginS;
    if (t >= earliest - kEpsilon) {
      prev_bottle = bottle;
      prev_s = t;
      continue;
    }
    double start_beats = m.beats(e);
    double new_beats = std::ceil(earliest / m.spb / kGridBeats - kEpsilon) * kGridBeats;
    double shift = new_beats - start_beats;
    if (t > prev_s + kEpsilon && shift <= kMaxShiftBeats + kEpsilon) {
      BarBeat at = bar_and_beat(new_beats, m.beats_per_bar);
      e.dur = std::max(kGridBeats, e.dur - shift);
      e.bar = at.bar;
      e.beat = at.beat;
      prev_bottle = bottle;
      prev_s = new_beats * m.spb;
    } else {
      dropped[i] = true;
      ++drops;
    }
  }
  erase(notes, dropped);
  return drops;
}

// _fix_duty: drops the notes that break the solenoid's duty limit.
size_t fix_duty(Notes& notes, const Robot& robot, const Meter& m) {
  std::vector<bool> dropped(notes.size());
  size_t drops = 0;
  check_duty(notes, strikes(notes, robot, m), robot, m, [&](uint16_t i) {
    dropped[i] = true;
    ++drops;
  });
  erase(notes, dropped);
  return drops;
}

struct Repaired {
  Notes notes;
  size_t drops;
};

// _repair_once: fold, then fix the timing, then the duty.
Repaired repair_once(const MidiScore& score, size_t bot_notes, const Robot& robot, const Meter& m) {
  Repaired r{{}, 0};
  r.notes.reserve(bot_notes);
  for (const ScoreEvent& e : score.events)
    if (e.part == DuoPart::Bot) r.notes.push_back(e);
  for (ScoreEvent& e : r.notes) e.pitch = robot.fold(e.pitch);
  r.drops = fix_timing(r.notes, robot, m);
  r.drops += fix_duty(r.notes, robot, m);
  return r;
}

// _slower_tempo: the tempo at which every gap between the bot's notes (as written) is
// wide enough, rounded down to a whole bpm; 0 if none is needed.
double slower_tempo(const MidiScore& score, const Robot& robot, double tempo_bpm) {
  Meter m(tempo_bpm, score.beats_per_bar);
  const Notes& notes = score.events;
  Order order = strikes(notes, robot, m);
  double factor = 1.0;
  for (size_t k = 1; k < order.size(); ++k) {
    const ScoreEvent &prev = notes[order[k - 1]], &cur = notes[order[k]];
    double gap = m.seconds(cur) - m.seconds(prev);
    if (gap <= kEpsilon) continue;  // simultaneous notes are dropped whatever the tempo
    double needed = robot.interval(robot.bottle(prev.pitch), robot.bottle(cur.pitch)) + kMarginS;
    factor = std::max(factor, needed / gap);
  }
  if (factor == 1.0) return 0;
  return std::max(kMinTempoBpm, std::floor(tempo_bpm / factor));
}

// check_robot: what the bot still cannot play, or nullptr.
const char* violation(const Notes& notes, const Robot& robot, const Meter& m) {
  Order order = strikes(notes, robot, m);
  if (order.size() != notes.size()) return "a note no bottle sounds";
  for (size_t k = 1; k < order.size(); ++k) {
    const ScoreEvent &prev = notes[order[k - 1]], &cur = notes[order[k]];
    double gap = m.seconds(cur) - m.seconds(prev);
    double needed = robot.interval(robot.bottle(prev.pitch), robot.bottle(cur.pitch)) + kMarginS;
    if (gap <= kEpsilon) return "two notes at once";
    if (gap < needed - kEpsilon) return "a note too soon after the one before";  // as repair
  }
  bool over = false;
  check_duty(notes, order, robot, m, [&](uint16_t) { over = true; });
  return over ? "too many notes for the striker's duty limit" : nullptr;
}

// repair_robot (keep_tempo off): the bot's part made playable, and the tempo it plays at.
const char* repair(const MidiScore& score, const Robot& robot, Notes& notes, double& tempo) {
  size_t bot_notes = 0;
  for (const ScoreEvent& e : score.events) bot_notes += e.part == DuoPart::Bot;
  tempo = score.tempo_bpm;
  Repaired result = repair_once(score, bot_notes, robot, Meter(tempo, score.beats_per_bar));
  if (bot_notes && static_cast<double>(result.drops) / bot_notes > kMaxDropRatio) {
    double slower = slower_tempo(score, robot, tempo);
    if (slower > 0 && slower < tempo) {
      // One repair in memory at a time: if the slower one drops no fewer notes, the first
      // is made again (it comes out the same).
      size_t drops = result.drops;
      result = Repaired{};
      Repaired retry = repair_once(score, bot_notes, robot, Meter(slower, score.beats_per_bar));
      if (retry.drops < drops) {
        result = std::move(retry);
        tempo = slower;
      } else {
        retry = Repaired{};
        result = repair_once(score, bot_notes, robot, Meter(tempo, score.beats_per_bar));
      }
    }
  }
  notes = std::move(result.notes);
  return violation(notes, robot, Meter(tempo, score.beats_per_bar));
}

// A timed command, compactly. `value`: a move's target steps, a strike's pulse, or a
// light cue's person's note (index into the score's events) or count-in beat.
enum class Kind : uint8_t { Move, Strike, CountInOn, CountInOff, PreOn, NowOn, KeyOff };

struct Command {
  int64_t t_us;
  int32_t value;
  uint16_t pos;  // where build_messages lists it before sorting by time: the tie-break
  Kind kind;
};
static_assert(kMaxSongLines <= UINT16_MAX, "a song's commands are counted in 16 bits");

class Song {
 public:
  Song(const MidiScore& score, const Robot& robot, const Keys& keys, const Meter& m)
      : score_(score), robot_(robot), keys_(keys), m_(m) {}

  // build_messages' bot part: robot_plan, just in time. `count`: only count them.
  size_t robot_commands(const Notes& notes, bool count) {
    size_t n = 0;
    int32_t position = kHomeSteps;
    for (uint16_t i : strikes(notes, robot_, m_)) {
      const ScoreEvent& e = notes[i];
      int32_t target = robot_.steps(robot_.bottle(e.pitch));
      double move = robot_.move_s(position, target);
      double fire = m_.seconds(e) - robot_.latency_s();
      if (move > 0) {
        if (!count) add({us(fire - move), target, 0, Kind::Move});
        ++n;
      }
      if (!count) add({us(fire), robot_.pulse_us(e.vel), 0, Kind::Strike});
      ++n;
      position = target;
    }
    return n;
  }

  // The person's notes in timed_events order (by start, then pitch), or a note outside
  // the keyboard.
  const ScoreEvent* order_human() {
    for (size_t i = 0; i < score_.events.size(); ++i)
      if (score_.events[i].part == DuoPart::Human) human_.push_back(static_cast<uint16_t>(i));
    std::sort(human_.begin(), human_.end(), [&](uint16_t a, uint16_t b) {
      const ScoreEvent &ea = score_.events[a], &eb = score_.events[b];
      double ta = m_.seconds(ea), tb = m_.seconds(eb);
      if (ta != tb) return ta < tb;
      return ea.pitch != eb.pitch ? ea.pitch < eb.pitch : a < b;
    });
    for (uint16_t i : human_)
      if (!keys_.contains(score_.events[i].pitch)) return &score_.events[i];
    return nullptr;
  }

  // led_plan, as _led_messages lists each cue: on, then off. `count`: only count them.
  size_t led_commands(bool count) {
    size_t n = 0;
    auto cue = [&](int64_t on, int64_t off, int32_t value, Kind kind, Kind off_kind) {
      if (!count) {
        add({on, value, 0, kind});
        add({off, value, 0, off_kind});
      }
      n += 2;
    };
    const int beats = count_in_beats();
    for (int i = 0; i < beats; ++i) {
      double on = (i - beats) * m_.spb;
      cue(us(on), us(on + m_.spb / 2), i, Kind::CountInOn, Kind::CountInOff);
    }
    for (uint16_t h : human_) {
      const ScoreEvent& e = score_.events[h];
      double start = m_.seconds(e), end = start + e.dur * m_.spb;
      double pre_on = pre_on_s(start);
      if (pre_on < start) cue(us(pre_on), us(start), h, Kind::PreOn, Kind::KeyOff);
      cue(us(start), us(end), h, Kind::NowOn, Kind::KeyOff);
    }
    return n;
  }

  void reserve(size_t n) { cmds_.reserve(n); }

  // build_messages' order: led_plan sorts the cues by (on_s, first LED); then every
  // message is sorted by time, stably. Light commands follow the bot's, from `first_led`.
  void sort(size_t first_led) {
    size_t cues = (cmds_.size() - first_led) / 2;
    std::vector<uint16_t> rank(cues);
    for (size_t k = 0; k < cues; ++k) rank[k] = static_cast<uint16_t>(k);
    auto on_s = [&](size_t k) { return cue_on_s(cmds_[first_led + 2 * k]); };
    auto first = [&](size_t k) { return cue_span(cmds_[first_led + 2 * k]).first; };
    std::sort(rank.begin(), rank.end(), [&](uint16_t a, uint16_t b) {
      double oa = on_s(a), ob = on_s(b);
      if (oa != ob) return oa < ob;
      return first(a) != first(b) ? first(a) < first(b) : a < b;
    });
    for (size_t r = 0; r < cues; ++r) {
      cmds_[first_led + 2 * rank[r]].pos = static_cast<uint16_t>(first_led + 2 * r);
      cmds_[first_led + 2 * rank[r] + 1].pos = static_cast<uint16_t>(first_led + 2 * r + 1);
    }
    std::sort(cmds_.begin(), cmds_.end(), [](const Command& a, const Command& b) {
      return a.t_us != b.t_us ? a.t_us < b.t_us : a.pos < b.pos;
    });
  }

  // compile_song: t_us from the first command, seq from 0, each on its kind's channel.
  void write(SongSink& sink, int carriage_ch, int led_ch, const CarriageInstrument& inst) const {
    char line[kMaxMessage + 1];
    const int64_t first = cmds_.front().t_us;
    for (size_t seq = 0; seq < cmds_.size(); ++seq) {
      const Command& c = cmds_[seq];
      int64_t t = c.t_us - first;
      if (c.kind == Kind::Move) {
        std::snprintf(line, sizeof line,
                      "{\"type\":\"move_at\",\"seq\":%lu,\"t_us\":%" PRId64
                      ",\"target_steps\":%" PRId32
                      ",\"v_max_mm_s\":%s,\"a_max_mm_s2\":%s,"
                      "\"ch\":%d}",
                      static_cast<unsigned long>(seq), t, c.value, inst.v_max_json, inst.a_max_json,
                      carriage_ch);
      } else if (c.kind == Kind::Strike) {
        std::snprintf(line, sizeof line,
                      "{\"type\":\"strike_at\",\"seq\":%lu,\"t_us\":%" PRId64
                      ",\"pulse_us\":%" PRId32 ",\"ch\":%d}",
                      static_cast<unsigned long>(seq), t, c.value, carriage_ch);
      } else {
        Span span = cue_span(c);
        const uint8_t* rgb = colour(c.kind);
        std::snprintf(line, sizeof line,
                      "{\"type\":\"led_frame_at\",\"seq\":%lu,\"t_us\":%" PRId64
                      ",\"first\":%" PRId32 ",\"count\":%" PRId32 ",\"rgb\":[%d,%d,%d],\"ch\":%d}",
                      static_cast<unsigned long>(seq), t, span.first, span.count, rgb[0], rgb[1],
                      rgb[2], led_ch);
      }
      sink.line(line);
    }
  }

 private:
  void add(Command c) {
    c.pos = static_cast<uint16_t>(cmds_.size());
    cmds_.push_back(c);
  }

  int count_in_beats() const { return score_.beats_per_bar * kCountInBars; }

  double pre_on_s(double start) const {
    return std::max(start - kLeadBeats * m_.spb, -count_in_beats() * m_.spb);
  }

  double cue_on_s(const Command& on) const {
    if (on.kind == Kind::CountInOn) return (on.value - count_in_beats()) * m_.spb;
    double start = m_.seconds(score_.events[on.value]);
    return on.kind == Kind::PreOn ? pre_on_s(start) : start;
  }

  Span cue_span(const Command& c) const {
    if (c.kind == Kind::CountInOn || c.kind == Kind::CountInOff) return {0, keys_.total()};
    return keys_.span(score_.events[c.value].pitch);
  }

  static const uint8_t* colour(Kind kind) {
    return kind == Kind::CountInOn ? kCountIn
           : kind == Kind::PreOn   ? kPreCue
           : kind == Kind::NowOn   ? kPlayNow
                                   : kOff;
  }

  const MidiScore& score_;
  const Robot& robot_;
  const Keys& keys_;
  const Meter m_;
  Order human_;
  std::vector<Command> cmds_;
};

int channel_of(const Channels& channels, ChannelKind kind) {
  for (size_t i = 0; i < channels.count; ++i)
    if (channels.items[i].kind == kind) return static_cast<int>(i);
  return -1;
}

}  // namespace

bool plan_song(const MidiScore& score, const CarriageInstrument& instrument,
               const KeyboardInstrument& keyboard, const Channels& channels, SongSink& sink,
               std::string& why) {
  const Robot robot(instrument);
  Notes notes;
  double tempo;
  if (const char* left = repair(score, robot, notes, tempo)) {
    why = std::string("repair left violations: ") + left;  // a bug, as the Hub's assertion
    return false;
  }
  const Meter m(tempo, score.beats_per_bar);
  const Keys keys(keyboard);
  Song song(score, robot, keys, m);
  if (const ScoreEvent* off = song.order_human()) {
    why = "key " + std::to_string(off->pitch) + " is not on the keyboard";  // led_span
    return false;
  }
  size_t bot_commands = song.robot_commands(notes, true);
  size_t total = bot_commands + song.led_commands(true);
  if (total > static_cast<size_t>(kMaxSongLines)) {
    why = std::to_string(total) + " commands; a stored song holds at most " +
          std::to_string(kMaxSongLines);
    return false;
  }
  int carriage_ch = channel_of(channels, ChannelKind::CarriageStriker);
  int led_ch = channel_of(channels, ChannelKind::LedStrip);
  std::string missing;  // by name, sorted: carriage_striker before led_strip
  if (bot_commands && carriage_ch < 0) missing = kind_name(ChannelKind::CarriageStriker);
  if (led_ch < 0) {
    if (!missing.empty()) missing += ", ";
    missing += kind_name(ChannelKind::LedStrip);
  }
  if (!missing.empty()) {
    why = "the rig has no channel for: " + missing;
    return false;
  }
  song.reserve(total);
  song.robot_commands(notes, false);
  Notes().swap(notes);  // the bot's notes are planned: free them for the light cues
  song.led_commands(false);
  song.sort(bot_commands);
  song.write(sink, carriage_ch, led_ch, instrument);
  return true;
}

}  // namespace duet
