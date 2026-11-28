#include "duet_midi_planner.hpp"

#include "duet_json.hpp"
#include "duet_midi.hpp"
#include "duet_planner.hpp"

namespace duet {

namespace {

// The planned commands go straight into the song being stored, one at a time.
struct IntoSong : SongSink {
  explicit IntoSong(Device& device) : device(device) {}
  void line(const char* json) override { device.song_line(json); }
  Device& device;
};

}  // namespace

Response MidiPlanner::plan_midi(const std::vector<uint8_t>& midi, const std::string& title,
                                int slot) {
  MidiScore score;
  std::string why;
  if (!read_midi(midi.data(), midi.size(), score, why)) return refused(400, why);
  if (const char* busy = device_.begin_song(slot, title)) return refused(409, busy);
  IntoSong into(device_);
  if (!plan_song(score, robot_, keyboard_, channels_, into, why)) {
    device_.abort_song();
    return refused(422, why);  // the Hub refuses the same score (SONG_INVALID)
  }
  if (const char* failed = device_.end_song())  // "storage full", or a planner bug
    return refused(std::string(failed) == "storage full" ? 507 : 500, failed);
  std::string body = "{\"ok\":true,\"warnings\":[";
  for (size_t i = 0; i < score.warnings.size(); ++i)
    body += (i ? "," : "") + json_string(score.warnings[i]);
  return {200, body + "]}"};
}

}  // namespace duet
