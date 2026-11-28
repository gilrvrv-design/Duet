#include "duet_device.hpp"

#include <cstdio>

namespace duet {

void Device::on_message(const char* json, int64_t now_us) {
  Command c;
  bool ok = parse(json, c);
  if (receiving_ && ok && c.timed()) {  // heartbeats and pings still pass during uploads
    receive_line(c, json, now_us);
    return;
  }
  if (ok) {
    switch (c.type) {
      case Type::Song:
        ex_.keepalive(now_us);
        begin_upload(c, now_us);
        return;
      case Type::Play:
        ex_.keepalive(now_us);
        if (playing()) {
          ack(c.seq, "error: already playing");
        } else if (!store_.has(c.slot)) {
          ack(c.seq, "error: no song in that slot");
        } else if (ex_.estopped()) {
          ack(c.seq, "error: emergency stop");
        } else {
          ack(c.seq, "ok");
          play(c.slot, now_us);
        }
        return;
      case Type::Stop:
        ex_.keepalive(now_us);
        stop();
        ack(c.seq, "ok");
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

void Device::greet(const Identity& id) {
  char buf[kMaxMessage + 1];
  write_hello(buf, sizeof buf, id);
  sink_.send(buf);
  write_limits(buf, sizeof buf, ex_.config());
  sink_.send(buf);
}

void Device::on_oversize(int64_t now_us) {
  if (receiving_) {
    upload_bad_ = true;  // the line is lost: the song would have a hole in it
    if (--upload_left_ == 0) end_upload("error: bad song line");
    return;
  }
  ex_.on_oversize(now_us);
}

void Device::begin_upload(const Command& c, int64_t now_us) {
  if (receiving_) {
    store_.abort();
    ack(upload_seq_, "error: upload replaced");
    receiving_ = false;
  }
  if (playing()) {
    ack(c.seq, "error: playing from memory");
  } else if (c.lines < 1 || c.lines > kMaxSongLines) {
    ack(c.seq, "error: bad song length");
  } else if (!store_.begin(c.slot)) {
    ack(c.seq, "error: bad song slot");
  } else {
    receiving_ = true;
    upload_seq_ = c.seq;
    upload_left_ = c.lines;
    upload_last_us_ = now_us;
    upload_bad_ = false;
  }
}

void Device::receive_line(const Command& c, const char* json, int64_t now_us) {
  ex_.keepalive(now_us);
  upload_last_us_ = now_us;
  if (c.t_us < 0 || c.t_us > kMaxSongUs || !store_.append(json)) upload_bad_ = true;
  if (--upload_left_ == 0) end_upload(upload_bad_ ? "error: bad song line" : nullptr);
}

void Device::end_upload(const char* status) {
  receiving_ = false;
  if (status == nullptr && !store_.finish()) status = "error: storage full";
  if (status != nullptr) store_.abort();
  ack(upload_seq_, status == nullptr ? "ok" : status);
}

bool Device::play(int slot, int64_t now_us) {
  if (!store_.has(slot) || ex_.estopped()) return false;
  slot_ = slot;
  // Always home: a song is compiled from the home position, and the carriage may be
  // wherever the last song left it.
  state_ = State::Homing;
  ex_.start_homing(now_us);
  return true;
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
      play(slot, now_us);
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
