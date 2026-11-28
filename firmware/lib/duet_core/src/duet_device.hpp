// The device as a whole: the executor, plus songs stored on it and played without the
// Hub ("play from memory"). Every message goes through here; anything that is not about
// songs passes to the executor unchanged.
//
//   {"type":"song","seq":S,"slot":k,"lines":N}  then N timed commands, t_us from 0.
//       Acked once, with seq S, after the last line (ok, or why it was refused).
//   {"type":"play","seq":S,"slot":k}   home, then play slot k
//   {"type":"stop","seq":S}            stop playing
//
// A stored song plays through the executor's queue, half a second ahead, as the Hub's
// conductor sends it, so every safety rule (homing, travel, duty, e-stop) still applies.
#pragma once
#include <cstdint>

#include "duet_executor.hpp"
#include "duet_songs.hpp"

namespace duet {

constexpr int64_t kPlayLeadUs = 500000;      // from homed (or play) to the song's t_us 0
constexpr int64_t kPlayLookaheadUs = 500000;  // stored commands are queued this far ahead
constexpr int64_t kUploadTimeoutUs = 2000000;  // an upload that stalls this long is dropped
constexpr int64_t kMaxSongUs = 3600000000;     // a song line later than an hour is refused

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

  bool playing() const { return state_ != State::Idle; }
  bool estopped() const { return ex_.estopped(); }
  const char* state_name() const;  // "idle", "homing" or "playing"
  int slot() const { return slot_; }  // the song playing or last played; -1 before any
  const SongStore& songs() const { return store_; }
  const Config& config() const { return ex_.config(); }
  const Identity& identity() const { return id_; }

 private:
  enum class State { Idle, Homing, Playing };

  void begin_upload(const Command& c, int64_t now_us);
  void receive_line(const Command& c, const char* json, int64_t now_us);
  void end_upload(const char* status);
  void play(int slot, int64_t now_us);
  void start_song(int64_t now_us);
  void feed(int64_t now_us);
  void ack(int64_t seq, const char* status);
  void fault(const char* code, const char* detail);

  Executor& ex_;
  SongStore& store_;
  Sink& sink_;
  Identity id_;

  bool receiving_ = false;
  int64_t upload_seq_ = 0;
  int32_t upload_left_ = 0;
  int64_t upload_last_us_ = 0;
  bool upload_bad_ = false;

  State state_ = State::Idle;
  int slot_ = -1;
  int64_t base_us_ = 0;  // device time of the song's t_us 0
  bool have_next_ = false;
  Command next_;
};

}  // namespace duet
