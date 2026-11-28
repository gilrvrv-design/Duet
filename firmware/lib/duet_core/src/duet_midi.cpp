#include "duet_midi.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace duet {
namespace {

constexpr uint32_t kDefaultTempoUs = 500000;  // MIDI's default: 120 bpm in quarter notes
constexpr double kMinTempoBpm = 20.0;         // duet.score: exclusive
constexpr double kMaxTempoBpm = 300.0;        // inclusive
constexpr double kEpsilon = 1e-9;             // duet.timing.EPSILON
constexpr double kMinDur = 1.0 / 64;          // in beats, for a note released at once
// A released note takes at least six bytes: a delta and two data bytes to start it
// (under running status), as many to release it.
constexpr size_t kMinNoteBytes = 6;

// Python's round(x, digits): the decimal correctly rounded from x's exact value, ties
// to even, read back as a double. printf's %f and strtod do just that (glibc, newlib).
double py_round(double x, int digits) {
  char buf[48];  // ample: positions stay below 2^30 beats, tempos below 2^28 bpm
  std::snprintf(buf, sizeof buf, "%.*f", digits, x);
  return std::strtod(buf, nullptr);
}

// Python's x // w for positive floats (CPython's _float_div_mod), which can differ from
// floor(x / w) when the quotient rounds to a whole number.
double py_floor_div(double x, double w) {
  double div = (x - std::fmod(x, w)) / w;
  double whole = std::floor(div);
  return div - whole > 0.5 ? whole + 1.0 : whole;
}

// What str.isspace() is true of in Latin-1, the charset mido decodes track names with.
bool py_space(uint8_t c) {
  return (c >= 0x09 && c <= 0x0D) || (c >= 0x1C && c <= 0x20) || c == 0x85 || c == 0xA0;
}

enum class Name : uint8_t { Other, Bot, Human };  // a track's name, if it is a duo part's

// The track name, stripped and lowercased as Python does. No Latin-1 letter outside
// ASCII lowercases into ASCII, so an ASCII comparison decides.
Name duo_name(const uint8_t* text, size_t size) {
  const uint8_t* end = text + size;
  while (text < end && py_space(*text)) ++text;
  while (end > text && py_space(end[-1])) --end;
  auto is = [&](const char* name) {
    size_t n = std::strlen(name);
    if (static_cast<size_t>(end - text) != n) return false;
    for (size_t i = 0; i < n; ++i)
      if ((text[i] | 0x20) != name[i]) return false;  // name is lowercase letters
    return true;
  };
  if (is(part_name(DuoPart::Bot))) return Name::Bot;
  if (is(part_name(DuoPart::Human))) return Name::Human;
  return Name::Other;
}

struct Note {
  uint32_t start, end;  // ticks
  uint8_t track, pitch, vel;
  DuoPart part;
};

struct Held {  // a note started and not yet released
  int64_t start;
  uint8_t channel, pitch, vel;
};

// What _read_notes finds in a file.
struct Smf {
  int ticks_per_quarter = 0;
  uint32_t tempo_us = kDefaultTempoUs;  // the first in the file
  int beats = 4, unit_exp = 2;          // the first time signature: beats/2^unit_exp
  std::vector<Note> notes;              // in the order they are released, track by track
  std::vector<Name> names;              // by track
  int tempo_changes = 0, signature_changes = 0;
  size_t unreleased = 0;
};

// A cursor over the uploaded bytes: no read goes past the end.
class Bytes {
 public:
  Bytes(const uint8_t* p, size_t n) : p_(p), end_(p + n) {}
  size_t left() const { return static_cast<size_t>(end_ - p_); }
  const uint8_t* take(size_t n) {
    if (n > left()) return nullptr;
    const uint8_t* at = p_;
    p_ += n;
    return at;
  }
  bool byte(uint8_t& b) {
    if (p_ == end_) return false;
    b = *p_++;
    return true;
  }

 private:
  const uint8_t* p_;
  const uint8_t* end_;
};

uint32_t be16(const uint8_t* p) { return uint32_t{p[0]} << 8 | p[1]; }
uint32_t be32(const uint8_t* p) { return be16(p) << 16 | be16(p + 2); }

class Parser {
 public:
  explicit Parser(Smf& smf) : smf_(smf) {}
  const std::string& why() const { return why_; }

  bool file(const uint8_t* data, size_t size) {
    if (size > kMaxMidiBytes)
      return fail("the file is larger than " + std::to_string(kMaxMidiBytes) + " bytes");
    Bytes in(data, size);
    const uint8_t* id = in.take(8);
    if (!id || std::memcmp(id, "MThd", 4) != 0) return fail("not a MIDI file: no MThd header");
    uint32_t length = be32(id + 4);
    const uint8_t* header = length >= 6 ? in.take(length) : nullptr;
    if (!header) return fail("the MIDI header is cut short");
    uint32_t format = be16(header), tracks = be16(header + 2), division = be16(header + 4);
    if (format > 1)
      return fail("MIDI format " + std::to_string(format) + " is not supported: only 0 and 1");
    if (division & 0x8000)
      return fail("SMPTE time division is not supported: only ticks per quarter note");
    if (division == 0) return fail("a time division of 0 ticks per quarter note");
    if (tracks > kMaxMidiTracks)
      return fail("more than " + std::to_string(kMaxMidiTracks) + " tracks");
    smf_.ticks_per_quarter = static_cast<int>(division);
    smf_.names.assign(tracks, Name::Other);
    smf_.notes.reserve(std::min(kMaxMidiNotes, size / kMinNoteBytes));
    for (track_ = 0; track_ < tracks; ++track_) {
      const uint8_t* chunk = in.take(8);
      if (!chunk) return fail("the file ends before track " + std::to_string(track_));
      if (std::memcmp(chunk, "MTrk", 4) != 0) return track_fail("has no MTrk header");
      uint32_t chunk_size = be32(chunk + 4);
      const uint8_t* body = in.take(chunk_size);
      if (!body) return track_fail("runs past the end of the file");
      if (!events(Bytes(body, chunk_size))) return false;
    }
    return true;
  }

 private:
  bool fail(const std::string& reason) {
    why_ = reason;
    return false;
  }
  bool track_fail(const char* reason) {
    return fail("track " + std::to_string(track_) + " " + reason);
  }
  bool cut() { return track_fail("ends in the middle of a message"); }

  // A variable-length quantity: at most four bytes, as the SMF specification allows.
  bool varint(Bytes& in, uint32_t& value) {
    value = 0;
    for (int i = 0; i < 4; ++i) {
      uint8_t b;
      if (!in.byte(b)) return cut();
      value = value << 7 | (b & 0x7F);
      if (b < 0x80) return true;
    }
    return track_fail("has a number longer than four bytes");
  }

  bool events(Bytes in) {
    int64_t now = 0;
    uint8_t running = 0;  // the channel status a lone data byte continues; 0: none
    held_.clear();
    while (in.left()) {
      uint32_t delta;
      uint8_t status;
      if (!varint(in, delta)) return false;
      if (!in.byte(status)) return cut();
      now += delta;
      if (status == 0xFF) {
        if (!meta(in)) return false;  // meta events leave running status as it is
      } else if (status == 0xF0 || status == 0xF7) {
        // Sysex is skipped, and cancels running status as the SMF specification says.
        uint32_t length;
        if (!varint(in, length)) return false;
        if (!in.take(length)) return cut();
        running = 0;
      } else if (status > 0xF0) {
        char text[64];
        std::snprintf(text, sizeof text, "has status byte 0x%02X, which a MIDI file cannot hold",
                      status);
        return track_fail(text);
      } else {
        uint8_t data[2];
        size_t have = 0;
        if (status < 0x80) {
          if (!running) return track_fail("uses running status with no status before it");
          data[have++] = status;
          status = running;
        }
        running = status;
        uint8_t kind = status & 0xF0;
        size_t count = kind == 0xC0 || kind == 0xD0 ? 1 : 2;
        for (; have < count; ++have) {
          if (!in.byte(data[have])) return cut();
          if (data[have] > 0x7F) return track_fail("has a data byte above 127");
        }
        uint8_t channel = status & 0x0F;
        if (kind == 0x90 && data[1] > 0) {
          if (!start(channel, data[0], data[1], now)) return false;
        } else if (kind == 0x80 || kind == 0x90) {
          if (!release(channel, data[0], now)) return false;
        }
      }
    }
    smf_.unreleased += held_.size();
    return true;
  }

  bool meta(Bytes& in) {
    uint8_t type;
    uint32_t length;
    if (!in.byte(type)) return cut();
    if (!varint(in, length)) return false;
    const uint8_t* d = in.take(length);
    if (!d) return cut();
    if (type == 0x03) {
      smf_.names[track_] = duo_name(d, length);  // the last name in a track counts
    } else if (type == 0x51) {
      if (length < 3) return track_fail("has a tempo shorter than 3 bytes");
      uint32_t tempo = uint32_t{d[0]} << 16 | uint32_t{d[1]} << 8 | d[2];
      if (!seen_tempo_) {
        if (tempo == 0) return track_fail("sets a tempo of 0 microseconds per quarter note");
        smf_.tempo_us = tempo;
        seen_tempo_ = true;
      } else if (tempo != smf_.tempo_us) {
        ++smf_.tempo_changes;
      }
    } else if (type == 0x58) {
      if (length < 4) return track_fail("has a time signature shorter than 4 bytes");
      if (!seen_signature_) {
        // What a score allows (duet.score.Meta): 1-16 beats of halves to sixteenths.
        if (d[0] < 1 || d[0] > 16 || d[1] < 1 || d[1] > 4) {
          std::string unit = d[1] < 64 ? std::to_string(uint64_t{1} << d[1])
                                       : "2^" + std::to_string(d[1]);
          return fail("unsupported time signature " + std::to_string(d[0]) + "/" + unit);
        }
        smf_.beats = d[0];
        smf_.unit_exp = d[1];
        seen_signature_ = true;
      } else if (d[0] != smf_.beats || d[1] != smf_.unit_exp) {
        ++smf_.signature_changes;
      }
    }
    return true;
  }

  bool start(uint8_t channel, uint8_t pitch, uint8_t vel, int64_t now) {
    if (++note_ons_ > kMaxMidiNotes)
      return fail("more than " + std::to_string(kMaxMidiNotes) + " notes");
    held_.push_back({now, channel, pitch, vel});
    return true;
  }

  // Releases the earliest held note of this channel and key, as _read_notes's pop(0).
  bool release(uint8_t channel, uint8_t pitch, int64_t now) {
    auto it = std::find_if(held_.begin(), held_.end(), [&](const Held& h) {
      return h.channel == channel && h.pitch == pitch;
    });
    if (it == held_.end()) return true;
    if (now >= kMaxMidiTicks) return track_fail("has notes too late in it: the file is too long");
    smf_.notes.push_back({static_cast<uint32_t>(it->start), static_cast<uint32_t>(now),
                          static_cast<uint8_t>(track_), pitch, it->vel, DuoPart::Human});
    held_.erase(it);
    return true;
  }

  Smf& smf_;
  std::string why_;
  uint32_t track_ = 0;
  std::vector<Held> held_;  // in the track being read
  size_t note_ons_ = 0;
  bool seen_tempo_ = false, seen_signature_ = false;
};

// _assign_parts: the parts by track, or false for a single unnamed track, which the
// skyline splits.
bool assign_by_track(Smf& smf) {
  size_t tracks = smf.names.size();
  std::vector<uint32_t> sum(tracks), count(tracks);
  for (const Note& n : smf.notes) {
    sum[n.track] += n.pitch;
    ++count[n.track];
  }
  bool named = false;
  size_t used = 0, melody = 0;
  double highest = 0;
  for (size_t t = 0; t < tracks; ++t) {
    if (!count[t]) continue;
    named = named || smf.names[t] != Name::Other;
    double mean = static_cast<double>(sum[t]) / count[t];
    if (!used++ || mean > highest) {  // the first highest, as max() picks
      melody = t;
      highest = mean;
    }
  }
  if (!named && used == 1) return false;
  for (Note& n : smf.notes) {
    bool bot = named ? smf.names[n.track] == Name::Bot : n.track == melody;
    n.part = bot ? DuoPart::Bot : DuoPart::Human;
  }
  return true;
}

// _skyline on notes stably sorted by (start, pitch): those sharing a start are adjacent,
// and the top one is the first of the highest pitch in file order, as max() picks.
void skyline(std::vector<Note>& notes) {
  for (size_t first = 0; first < notes.size();) {
    size_t end = first;
    while (end < notes.size() && notes[end].start == notes[first].start) ++end;
    size_t top = end - 1;
    while (top > first && notes[top - 1].pitch == notes[end - 1].pitch) --top;
    for (size_t i = first; i < end; ++i) notes[i].part = DuoPart::Human;
    notes[top].part = DuoPart::Bot;
    first = end;
  }
}

}  // namespace

const char* part_name(DuoPart part) { return part == DuoPart::Bot ? "robot" : "pianist"; }

bool read_midi(const uint8_t* data, size_t size, MidiScore& score, std::string& why) {
  Smf smf;
  Parser parser(smf);
  if (!parser.file(data, size)) {
    why = parser.why();
    return false;
  }
  if (smf.notes.empty()) {
    why = "the file has no notes";
    return false;
  }
  score = MidiScore{};
  if (smf.tempo_changes)
    score.warnings.push_back(std::to_string(smf.tempo_changes) +
                             " later tempo change(s) ignored: one tempo per score");
  if (smf.signature_changes)
    score.warnings.push_back(std::to_string(smf.signature_changes) +
                             " later time signature change(s) ignored");
  if (smf.unreleased)
    score.warnings.push_back(std::to_string(smf.unreleased) +
                             " note(s) never released were left out");

  // The same operations, in the same order, as read_midi, so the doubles are the same.
  const int beats = smf.beats, unit = 1 << smf.unit_exp;
  const double tpb = smf.ticks_per_quarter * 4.0 / unit;
  const double tempo = py_round(60000000.0 / smf.tempo_us * unit / 4, 3);
  auto to_beats = [&](uint32_t ticks) { return py_round(ticks / tpb, 6); };

  bool by_track = assign_by_track(smf);
  std::stable_sort(smf.notes.begin(), smf.notes.end(), [](const Note& a, const Note& b) {
    return a.start != b.start ? a.start < b.start : a.pitch < b.pitch;
  });
  if (!by_track) skyline(smf.notes);

  score.events.reserve(smf.notes.size());
  for (const Note& n : smf.notes) {
    double start = to_beats(n.start);
    double dur = std::max(to_beats(n.end) - start, kMinDur);
    // duet.timing.bar_and_beat
    double bar = py_floor_div(start + kEpsilon, beats);
    double beat = start - bar * beats;
    if (std::fabs(beat) < kEpsilon) beat = 0.0;
    score.events.push_back({py_round(beat + 1, 6), py_round(dur, 6),
                            static_cast<int32_t>(bar) + 1, n.pitch, n.vel, n.part});
  }

  score.beats_per_bar = beats;
  score.beat_unit = unit;
  score.tempo_bpm = std::min(kMaxTempoBpm, std::max(kMinTempoBpm + 0.1, tempo));  // clamp_tempo
  if (score.tempo_bpm != tempo) {
    char text[96];
    std::snprintf(text, sizeof text, "tempo %g bpm is outside what a score allows; using %g",
                  tempo, score.tempo_bpm);
    score.warnings.emplace_back(text);
  }
  return true;
}

}  // namespace duet
