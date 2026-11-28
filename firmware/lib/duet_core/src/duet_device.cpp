#include "duet_device.hpp"

#include <cstdio>
#include <cstring>
#include <string>

#include "duet_json.hpp"

namespace duet {

void Device::on_message(const char* json, int64_t now_us) {
  Command c;
  bool ok = parse(json, c);
  if (receiving_ && ok && c.timed()) {  // heartbeats and pings still pass during uploads
    receive_line(json, now_us);
    return;
  }
  if (ok) {
    switch (c.type) {
      case Type::Song:
        ex_.keepalive(now_us);
        begin_upload(c, json, now_us);
        return;
      case Type::Play:
        ex_.keepalive(now_us);
        if (const char* why = request_play(c.slot, now_us)) {
          char status[64];
          std::snprintf(status, sizeof status, "error: %s", why);
          ack(c.seq, status);
        } else {
          ack(c.seq, "ok");
        }
        return;
      case Type::Stop:
        ex_.keepalive(now_us);
        stop();
        ack(c.seq, "ok");
        return;
      case Type::Greet:
        greet();
        return;
      case Type::Home:
      case Type::Estop:
        stop();  // the Hub takes over
        break;
      default:
        if (c.timed() && playing()) {
          ex_.keepalive(now_us);
          ack(c.seq, "error: playing from memory");
          return;
        }
        break;
    }
  }
  ex_.on_message(json, now_us);
}

void Device::greet() {
  char buf[kMaxMessage + 1];
  write_hello(buf, sizeof buf, id_);
  sink_.send(buf);
  for (size_t ch = 0; ch < id_.channels.count; ++ch) {
    write_channel(buf, sizeof buf, static_cast<int>(ch), id_.channels.items[ch], ex_.config());
    sink_.send(buf);
  }
}

void Device::on_oversize(int64_t now_us) {
  if (receiving_) {
    song_line_lost();  // the song would have a hole in it
    if (--upload_left_ == 0) end_upload(nullptr);
    return;
  }
  ex_.on_oversize(now_us);
}

// A song's title: optional; short, and no control characters (it is shown as one line).
bool read_song_title(const char* json, std::string& title) {
  title.clear();
  if (std::strstr(json, "\"title\"") && !string_field(json, "title", title)) return false;
  if (title.size() > kMaxTitle) return false;
  for (char ch : title)
    if (static_cast<unsigned char>(ch) < 0x20) return false;
  return true;
}

const char* Device::begin_song(int slot, const std::string& title) {
  if (writing_) return "another song is being stored";
  if (playing()) return "playing from memory";
  if (!store_.begin(slot, title)) return "bad song slot";
  writing_ = true;
  song_lines_ = 0;
  song_bad_ = false;
  return nullptr;
}

bool Device::song_line(const char* json) {
  Command c;
  bool ok = ++song_lines_ <= kMaxSongLines && parse(json, c) && c.timed() && c.t_us >= 0 &&
            c.t_us <= kMaxSongUs && ex_.accepts(c) && store_.append(json);
  song_bad_ = song_bad_ || !ok;
  return ok;
}

void Device::song_line_lost() {
  ++song_lines_;
  song_bad_ = true;
}

const char* Device::end_song() {
  writing_ = false;
  const char* why = song_bad_         ? "bad song line"
                    : song_lines_ == 0 ? "bad song length"
                    : !store_.finish() ? "storage full"
                                       : nullptr;
  if (why) store_.abort();
  return why;
}

void Device::abort_song() {
  if (!writing_) return;
  store_.abort();
  writing_ = false;
}

void Device::begin_upload(const Command& c, const char* json, int64_t now_us) {
  if (receiving_) {
    abort_song();
    ack(upload_seq_, "error: upload replaced");
    receiving_ = false;
  }
  std::string title;
  const char* why = c.lines < 1 || c.lines > kMaxSongLines ? "bad song length"
                    : !read_song_title(json, title)       ? "bad song title"
                                                          : begin_song(c.slot, title);
  if (why) {
    ack(c.seq, (std::string("error: ") + why).c_str());
    return;
  }
  receiving_ = true;
  upload_seq_ = c.seq;
  upload_left_ = c.lines;
  upload_last_us_ = now_us;
}

void Device::receive_line(const char* json, int64_t now_us) {
  ex_.keepalive(now_us);
  upload_last_us_ = now_us;
  song_line(json);
  if (--upload_left_ == 0) end_upload(nullptr);
}

void Device::end_upload(const char* stalled) {
  receiving_ = false;
  if (stalled) {
    abort_song();
    ack(upload_seq_, stalled);
    return;
  }
  const char* why = end_song();
  ack(upload_seq_, why ? (std::string("error: ") + why).c_str() : "ok");
}

const char* Device::delete_song(int slot) {
  if (playing() && slot == slot_) return "playing from memory";
  if (!store_.has(slot)) return "no song in that slot";
  return store_.remove(slot) ? nullptr : "storage failed";
}

const char* Device::request_play(int slot, int64_t now_us) {
  if (playing()) return "already playing";
  if (!store_.has(slot)) return "no song in that slot";
  if (ex_.estopped()) return "emergency stop";
  play(slot, now_us);
  return nullptr;
}

const char* Device::state_name() const {
  return state_ == State::Idle ? "idle" : state_ == State::Homing ? "homing" : "playing";
}

void Device::play(int slot, int64_t now_us) {
  slot_ = slot;
  // Always home: a song is compiled from the home position, and the carriage may be
  // wherever the last song left it.
  state_ = State::Homing;
  ex_.start_homing(now_us);
}

void Device::start_song(int64_t now_us) {
  if (!store_.open(slot_)) {
    state_ = State::Idle;
    return;
  }
  state_ = State::Playing;
  base_us_ = now_us + kPlayLeadUs;
  have_next_ = false;
  feed(now_us);
}

void Device::feed(int64_t now_us) {
  for (;;) {
    if (!have_next_) {
      char line[kMaxMessage + 1];
      if (!store_.next(line, sizeof line)) return;  // the whole song is queued
      if (!parse(line, next_) || !next_.timed()) {
        stop();
        fault("SONG_CORRUPT", "a stored song line cannot be read");
        return;
      }
      next_.t_us += base_us_;
      have_next_ = true;
    }
    if (next_.t_us > now_us + kPlayLookaheadUs) return;
    if (!ex_.submit(next_)) {
      stop();
      fault("PLAY_FAILED", "a stored command was refused");
      return;
    }
    have_next_ = false;
  }
}

void Device::poll(int64_t now_us) {
  if (receiving_ && now_us - upload_last_us_ > kUploadTimeoutUs) {
    upload_left_ = 0;
    end_upload("error: upload stalled");
  }
  if (state_ != State::Idle && ex_.estopped()) state_ = State::Idle;
  if (state_ == State::Homing) {
    ex_.keepalive(now_us);
    if (ex_.homed()) {
      start_song(now_us);
    } else if (!ex_.homing()) {
      state_ = State::Idle;  // homing failed; the executor sent HOMING_TIMEOUT
    }
  } else if (state_ == State::Playing) {
    ex_.keepalive(now_us);
    feed(now_us);
    // feed() leaves no line pending only when the store has none left. The song ends
    // when its last move and strike have finished, not when they leave the queue.
    if (state_ == State::Playing && !have_next_ && ex_.at_rest()) state_ = State::Idle;
  }
  ex_.poll(now_us);
}

void Device::button(int64_t now_us) {
  if (playing()) {
    stop();
    return;
  }
  for (int i = 1; i <= kSongSlots; ++i) {  // the next stored song after the last one
    int slot = (slot_ + i + kSongSlots) % kSongSlots;
    if (store_.has(slot)) {
      request_play(slot, now_us);  // refused only under an emergency stop
      return;
    }
  }
}

void Device::stop() {
  if (state_ == State::Idle) return;
  state_ = State::Idle;
  have_next_ = false;
  ex_.cancel();
}

void Device::ack(int64_t seq, const char* status) {
  char buf[96];
  write_ack(buf, sizeof buf, seq, status);
  sink_.send(buf);
}

void Device::fault(const char* code, const char* detail) {
  char buf[kMaxMessage + 1];
  write_fault(buf, sizeof buf, code, detail);
  sink_.send(buf);
}

}  // namespace duet
