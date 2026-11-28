// The device as a whole: the executor, plus songs stored on it and played without the
// Hub ("play from memory"). Every message goes through here; anything that is not about
// songs passes to the executor unchanged.
//
//   {"type":"song","seq":S,"slot":k,"lines":N,"title":".."}  then N timed commands, t_us
//       from 0. The title is optional (at most kMaxTitle bytes).
//       Acked once, with seq S, after the last line (ok, or why it was refused).
//   {"type":"play","seq":S,"slot":k}   home, then play slot k
//   {"type":"stop","seq":S}            stop playing
//
// A stored song plays through the executor's queue, half a second ahead, as the Hub's
// conductor sends it, so every safety rule (homing, travel, duty, e-stop) still applies.
#pragma once
#include <cstdint>
#include <string>

#include "duet_executor.hpp"
#include "duet_songs.hpp"

namespace duet {

constexpr int64_t kPlayLeadUs = 500000;      // from homed (or play) to the song's t_us 0
constexpr int64_t kPlayLookaheadUs = 500000;  // stored commands are queued this far ahead
constexpr int64_t kUploadTimeoutUs = 2000000;  // an upload that stalls this long is dropped
constexpr int64_t kMaxSongUs = 3600000000;     // a song line later than an hour is refused

// The title in a song message or a song file's first line ({"title":".."}): optional,
// at most kMaxTitle bytes, one line. False if it is not that.
bool read_song_title(const char* json, std::string& title);
bool valid_song_title(const std::string& title);  // at most kMaxTitle bytes, one line

class Device {
 public:
  Device(Executor& executor, SongStore& store, Sink& sink, const Identity& id)
      : ex_(executor), store_(store), sink_(sink), id_(id) {}

  // What a new Hub hears first: hello (who the device is), then its channels. Sent when
  // a WebSocket connects, and on a serial link when the Hub asks ({"type":"greet"}).
  void greet();
  void on_message(const char* json, int64_t now_us);
  void on_oversize(int64_t now_us);
  void poll(int64_t now_us);  // call every loop iteration, instead of executor.poll
  void button(int64_t now_us);  // the play button: next stored song, or stop

  // Play a stored song: nullptr if it starts, else why not ("already playing", ...).
  const char* request_play(int slot, int64_t now_us);
  void stop();  // stop playing; nothing if idle
  const char* delete_song(int slot);  // nullptr if gone, else why not

  // Storing a song, from the Hub (the song message) or the device API (a song file), one
  // at a time: begin_song, song_line for each command, then end_song or abort_song. A
  // bad line spoils the whole song: end_song refuses it and the old song stays.
  const char* begin_song(int slot, const std::string& title);  // nullptr: go on
  bool song_line(const char* json);                             // false: a bad line
  void song_line_lost();                                        // one was too long to read
  const char* end_song();                                       // nullptr: stored
  void abort_song();
  bool writing_song() const { return writing_; }

  bool playing() const { return state_ != State::Idle; }
  bool at_rest() const { return !playing() && ex_.at_rest(); }  // nothing moving or queued
  bool estopped() const { return ex_.estopped(); }
  const char* state_name() const;  // "idle", "homing" or "playing"
  int slot() const { return slot_; }  // the song playing or last played; -1 before any
  const SongStore& songs() const { return store_; }
  const Config& config() const { return ex_.config(); }
  const Identity& identity() const { return id_; }

 private:
  enum class State { Idle, Homing, Playing };

  void begin_upload(const Command& c, const char* json, int64_t now_us);
  void receive_line(const char* json, int64_t now_us);
  void end_upload(const char* stalled);
  void play(int slot, int64_t now_us);
  void start_song(int64_t now_us);
  void feed(int64_t now_us);
  void ack(int64_t seq, const char* status);
  void fault(const char* code, const char* detail);

  Executor& ex_;
  SongStore& store_;
  Sink& sink_;
  Identity id_;

  bool writing_ = false;  // a song is being stored
  int32_t song_lines_ = 0;
  bool song_bad_ = false;

  bool receiving_ = false;  // ... from the Hub, in song messages
  int64_t upload_seq_ = 0;
  int32_t upload_left_ = 0;
  int64_t upload_last_us_ = 0;

  State state_ = State::Idle;
  int slot_ = -1;
  int64_t base_us_ = 0;  // device time of the song's t_us 0
  bool have_next_ = false;
  Command next_;
};

}  // namespace duet
