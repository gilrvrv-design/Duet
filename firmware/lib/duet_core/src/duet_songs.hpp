// Songs stored on the device, to play without the Hub. A song is a title and a list of
// timed commands (move_at, strike_at, led_frame_at, note_at), one JSON line each, with
// t_us counted from the start of the song. The Hub compiles and uploads them;
// duet::Device plays them.
#pragma once
#include <cstddef>
#include <cstring>
#include <string>
#include <vector>

namespace duet {

constexpr int kSongSlots = 8;
constexpr int32_t kMaxSongLines = 4000;  // about ten minutes of a dense piece
constexpr size_t kMaxTitle = 64;         // bytes of UTF-8

class SongStore {
 public:
  virtual ~SongStore() = default;
  virtual bool begin(int slot, const std::string& title) = 0;  // start writing; the old
                                                               // song stays until finish()
  virtual bool append(const char* line) = 0;
  virtual bool finish() = 0;  // the new song replaces the old one
  virtual void abort() = 0;   // forget what was written; the old song stays
  virtual bool has(int slot) const = 0;
  virtual bool remove(int slot) = 0;
  virtual std::string title(int slot) const = 0;  // of a stored song
  virtual bool open(int slot) = 0;                // start reading
  virtual bool next(char* buf, size_t size) = 0;  // the next line; false at the end
};

// Songs in RAM: for tests, QEMU and the native device. Lost at power-off.
class MemorySongStore : public SongStore {
 public:
  bool begin(int slot, const std::string& title) override {
    if (slot < 0 || slot >= kSongSlots) return false;
    writing_ = slot;
    pending_title_ = title;
    pending_.clear();
    return true;
  }
  bool append(const char* line) override {
    if (writing_ < 0) return false;
    pending_.emplace_back(line);
    return true;
  }
  bool finish() override {
    if (writing_ < 0) return false;
    songs_[writing_] = pending_;
    titles_[writing_] = pending_title_;
    pending_.clear();
    writing_ = -1;
    return true;
  }
  void abort() override {
    pending_.clear();
    writing_ = -1;
  }
  bool has(int slot) const override {
    return slot >= 0 && slot < kSongSlots && !songs_[slot].empty();
  }
  std::string title(int slot) const override { return titles_[slot]; }
  bool remove(int slot) override {
    songs_[slot].clear();
    titles_[slot].clear();
    return true;
  }
  bool open(int slot) override {
    if (!has(slot)) return false;
    reading_ = slot;
    line_ = 0;
    return true;
  }
  bool next(char* buf, size_t size) override {
    if (reading_ < 0 || line_ >= songs_[reading_].size()) return false;
    const std::string& s = songs_[reading_][line_++];
    std::strncpy(buf, s.c_str(), size - 1);
    buf[size - 1] = '\0';
    return true;
  }

 private:
  std::vector<std::string> songs_[kSongSlots];
  std::string titles_[kSongSlots];
  std::vector<std::string> pending_;
  std::string pending_title_;
  int writing_ = -1;
  int reading_ = -1;
  size_t line_ = 0;
};

}  // namespace duet
