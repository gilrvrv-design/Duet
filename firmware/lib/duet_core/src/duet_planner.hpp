// The optional planner module: a MIDI-made duet (duet_midi.hpp) planned into a song on
// the device, with no server. The song is exactly the one the Hub makes of the same score
// for the default duo (tests/test_planner_contract.py holds the two to it):
//
//   score = repair_bots(score, in_use(robot, keyboard)).score
//   song = compile_song(score, robot, keyboard, channels)
//
// That is: the bot's part made playable (notes folded onto the instrument, too-fast notes
// shifted to the next grid point or dropped, notes over the striker's duty limit dropped,
// or the whole piece slowed down if that drops fewer), the carriage's moves and strikes
// planned just in time, the person's light cues with a one-bar count-in, all in time
// order from t_us 0, one JSON command per line, as Device::song_line takes them.
#pragma once
#include <string>

#include "duet_channels.hpp"
#include "duet_instruments.hpp"
#include "duet_midi.hpp"

namespace duet {

// Where the song goes, one command at a time, so no one holds the whole text.
class SongSink {
 public:
  virtual void line(const char* json) = 0;  // one command, without a newline

 protected:
  ~SongSink() = default;
};

// Plans `score`: its bot part on the carriage instrument `robot`, its human part on
// `keyboard`, for a board with `channels`, and writes the song's commands to `sink` in
// time order. False, with the reason in `why` and nothing written, where the Hub refuses
// the score too: a song of more than kMaxSongLines commands, a person's note outside the
// keyboard, a channel the commands need that the board lacks, or a repair that leaves the
// bot something it cannot play (a bug, on both sides: the Hub asserts it never happens).
//
// Memory, all of it freed on return: 24 bytes per bot note and 2 per note while
// repairing (one repair at a time, even when it tries a slower tempo), then 16 bytes per
// command, with the bot's notes until its commands are made, and 1 more per light
// command while the cues are put in order. At most about 120 KB (measured natively: 117 KB
// for 1996 bot notes making 4000 commands), on top of the score.
bool plan_song(const MidiScore& score, const CarriageInstrument& robot,
               const KeyboardInstrument& keyboard, const Channels& channels, SongSink& sink,
               std::string& why);

}  // namespace duet
