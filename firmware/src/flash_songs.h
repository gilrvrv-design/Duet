// Songs in the ESP32's flash (LittleFS), so they survive power-off. One file per slot,
// one JSON line per command. A new song is written to a temporary file and renamed over
// the old one only when complete: a failed upload never damages the stored song.
#pragma once
#include <Arduino.h>
#include <LittleFS.h>

#include "duet_songs.hpp"

class FlashSongStore : public duet::SongStore {
 public:
  bool begin_fs() { return LittleFS.begin(true); }  // formats the partition on first use

  bool begin(int slot) override {
    if (slot < 0 || slot >= duet::kSongSlots) return false;
    abort();
    writing_ = slot;
    out_ = LittleFS.open(kTemp, "w");
    return static_cast<bool>(out_);
  }
  bool append(const char* line) override {
    if (writing_ < 0 || !out_) return false;
    size_t n = strlen(line);
    return out_.write(reinterpret_cast<const uint8_t*>(line), n) == n && out_.write('\n') == 1;
  }
  bool finish() override {
    if (writing_ < 0 || !out_) return false;
    out_.close();
    String path = path_of(writing_);
    LittleFS.remove(path);
    bool ok = LittleFS.rename(kTemp, path);
    writing_ = -1;
    return ok;
  }
  void abort() override {
    if (out_) out_.close();
    LittleFS.remove(kTemp);
    writing_ = -1;
  }
  bool has(int slot) const override {
    if (slot < 0 || slot >= duet::kSongSlots) return false;
    File f = LittleFS.open(path_of(slot), "r");
    return f && f.size() > 0;
  }
  bool open(int slot) override {
    if (in_) in_.close();
    in_ = LittleFS.open(path_of(slot), "r");
    return static_cast<bool>(in_);
  }
  bool next(char* buf, size_t size) override {
    if (!in_ || !in_.available()) return false;
    size_t n = in_.readBytesUntil('\n', buf, size - 1);
    buf[n] = '\0';
    return n > 0;
  }

 private:
  static constexpr const char* kTemp = "/song.tmp";
  static String path_of(int slot) { return String("/song") + slot + ".txt"; }

  int writing_ = -1;
  File out_;
  File in_;
};
