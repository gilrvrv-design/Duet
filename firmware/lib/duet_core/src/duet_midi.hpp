// A Standard MIDI File made into a duet on the device, with no server: the same score
// the Hub's duet.midi_io.read_midi makes for the default duo (tests/test_midi_contract.py
// holds the two to the same result). Tracks named after the duo's parts are used as
// they are; otherwise the track with the highest mean pitch is the bot's and the rest
// the human's; a single track is split by giving the bot the top note of each onset.
#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace duet {

// The file arrives whole from a browser upload and is held in RAM with its notes and
// events (about 12 + 24 bytes a note): together about 100 KB at most, well within an
// ESP32-classic's free heap.
constexpr size_t kMaxMidiBytes = 32 * 1024;
constexpr size_t kMaxMidiTracks = 64;
constexpr size_t kMaxMidiNotes = 2000;
// Notes end before this tick, so a bar always fits an int32 (even at one tick per
// quarter in 16ths it is hours of music).
constexpr int64_t kMaxMidiTicks = int64_t{1} << 28;

// The default duo's parts (duet.score.DUO).
enum class DuoPart : uint8_t { Bot, Human };
const char* part_name(DuoPart part);  // "robot", "pianist"

struct ScoreEvent {
  double beat;    // 1-based, in beats of the time signature
  double dur;     // in beats
  int32_t bar;    // 1-based
  uint8_t pitch;  // MIDI number
  uint8_t vel;
  DuoPart part;
};

struct MidiScore {
  double tempo_bpm = 0;  // beats of the time signature per minute
  int beats_per_bar = 4;
  int beat_unit = 4;
  std::vector<ScoreEvent> events;     // by start, then pitch
  std::vector<std::string> warnings;  // what the import ignored or changed
};

// Reads the `size` bytes at `data`. False, with the reason in `why`, if they are not a
// MIDI file this can read (format 0 or 1, ticks per quarter note, within the limits).
bool read_midi(const uint8_t* data, size_t size, MidiScore& score, std::string& why);

}  // namespace duet
