#include "duet_api.hpp"

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "duet_json.hpp"
#include "duet_midi.hpp"  // kMaxMidiBytes only: the planner is linked only if installed

namespace duet {

namespace {

Response error(int status, const char* why) { return refused(status, why); }

const Response kOk{200, "{\"ok\":true}"};

// The slot in "/api/songs/<k><rest>", or -1 if the path is not that.
int song_slot(const char* path, const char* rest) {
  const char* prefix = "/api/songs/";
  size_t n = std::strlen(prefix);
  if (std::strncmp(path, prefix, n) != 0 || !std::isdigit(static_cast<unsigned char>(path[n])))
    return -1;
  char* end = nullptr;
  long slot = std::strtol(path + n, &end, 10);
  if (std::strcmp(end, rest) != 0 || slot < 0 || slot >= kSongSlots) return -1;
  return static_cast<int>(slot);
}

}  // namespace

Response refused(int status, const std::string& why) {
  return {status, "{\"error\":" + json_string(why) + "}"};
}

Response Api::handle(const char* method, const char* path, const char* body, int64_t now_us) {
  bool get = std::strcmp(method, "GET") == 0;
  bool post = std::strcmp(method, "POST") == 0;
  if (std::strcmp(path, "/api/info") == 0) return get ? info() : error(405, "use GET");
  if (std::strcmp(path, "/api/songs") == 0) return get ? songs() : error(405, "use GET");
  if (std::strcmp(path, "/api/settings") == 0) {
    if (get) return settings();
    return post ? save_settings(body) : error(405, "use GET or POST");
  }
  if (std::strcmp(path, "/api/stop") == 0) {
    if (!post) return error(405, "use POST");
    device_.stop();
    return kOk;
  }
  if (std::strcmp(path, "/api/estop") == 0) {
    if (!post) return error(405, "use POST");
    device_.on_message("{\"type\":\"estop\",\"seq\":0}", now_us);
    return kOk;
  }
  int slot = song_slot(path, "/play");
  if (slot >= 0) {
    if (!post) return error(405, "use POST");
    const char* why = device_.request_play(slot, now_us);
    return why ? error(409, why) : kOk;
  }
  slot = song_slot(path, "");
  if (slot >= 0) {
    if (std::strcmp(method, "DELETE") == 0) {
      const char* why = device_.delete_song(slot);
      return !why ? kOk : device_.songs().has(slot) ? error(409, why) : error(404, why);
    }
    if (std::strcmp(method, "PUT") != 0) return error(405, "use PUT or DELETE");
    Response accepted = begin_upload(path);
    if (accepted.status != 200) return accepted;
    upload_data(body, std::strlen(body));
    return end_upload();
  }
  return error(404, "no such path");
}

Response Api::begin_upload(const char* path, const std::string& title) {
  int midi_slot = song_slot(path, "/midi");
  int slot = midi_slot >= 0 ? midi_slot : song_slot(path, "");
  if (slot < 0) return error(404, "no such path");
  if (midi_slot >= 0 && !planner_) return error(404, "this board has no MIDI planner");
  if (midi_slot >= 0 && !valid_song_title(title)) return error(400, "bad song title");
  if (device_.writing_song()) return error(409, "another song is being stored");
  if (!device_.at_rest()) return error(409, "the rig is busy playing");
  upload_slot_ = slot;
  upload_midi_ = midi_slot >= 0;
  midi_title_ = title;
  midi_.clear();
  upload_lines_ = 0;
  first_bad_line_ = 0;
  failed_status_ = 0;
  line_.clear();
  line_too_long_ = false;
  return kOk;
}

void Api::upload_data(const char* data, size_t n) {
  if (upload_midi_) {
    if (midi_.size() + n > kMaxMidiBytes)
      upload_failed(413, ("the file is larger than " + std::to_string(kMaxMidiBytes) +
                          " bytes").c_str());
    else if (!failed_status_)
      midi_.insert(midi_.end(), data, data + n);
    return;
  }
  for (size_t i = 0; i < n; ++i) {
    char c = data[i];
    if (c == '\n') {
      upload_line();
    } else if (c != '\r') {
      if (line_.size() < kMaxMessage) line_ += c;
      else line_too_long_ = true;
    }
  }
}

void Api::upload_line() {
  bool blank = line_.empty() && !line_too_long_;
  bool too_long = line_too_long_;
  std::string line;
  line.swap(line_);
  line_too_long_ = false;
  if (blank || failed_status_) return;
  if (++upload_lines_ == 1) {  // the title line
    std::string title;
    if (too_long || line.find("\"title\"") == std::string::npos ||
        !read_song_title(line.c_str(), title))
      return upload_failed(400, "a song file starts with its title: {\"title\":\"..\"}");
    if (const char* why = device_.begin_song(upload_slot_, title)) upload_failed(409, why);
    return;
  }
  bool ok = too_long ? (device_.song_line_lost(), false) : device_.song_line(line.c_str());
  if (!ok && first_bad_line_ == 0) first_bad_line_ = upload_lines_;
}

void Api::upload_failed(int status, const char* why) {
  failed_status_ = status;
  failed_why_ = why;
}

Response Api::end_upload() {
  if (upload_midi_) {
    int slot = upload_slot_;
    upload_slot_ = -1;
    std::vector<uint8_t> midi;
    midi.swap(midi_);  // freed on return: the planner needs the room
    if (failed_status_) return error(failed_status_, failed_why_.c_str());
    return planner_->plan_midi(midi, midi_title_, slot);
  }
  if (!line_.empty() || line_too_long_) upload_line();  // the last line had no newline
  upload_slot_ = -1;
  if (failed_status_) return error(failed_status_, failed_why_.c_str());
  if (upload_lines_ == 0) return error(400, "the song file is empty");
  const char* why = device_.end_song();
  if (!why) return kOk;
  if (std::strcmp(why, "bad song line") == 0)
    return error(400, ("bad song line " + std::to_string(first_bad_line_)).c_str());
  return std::strcmp(why, "storage full") == 0 ? error(507, why) : error(400, why);
}

void Api::abort_upload() {
  if (upload_slot_ < 0) return;
  if (!upload_midi_ && !failed_status_ && upload_lines_ > 0) device_.abort_song();
  std::vector<uint8_t>().swap(midi_);
  upload_slot_ = -1;
}

Response Api::info() const {
  const Identity& id = device_.identity();
  char buf[kMaxMessage + 1];
  write_hello(buf, sizeof buf, id);
  std::string body = std::string("{\"hello\":") + buf + ",\"channels\":[";
  for (size_t ch = 0; ch < id.channels.count; ++ch) {
    write_channel(buf, sizeof buf, static_cast<int>(ch), id.channels.items[ch],
                  device_.config());
    body += (ch ? "," : "") + std::string(buf);
  }
  std::snprintf(buf, sizeof buf, "],\"state\":\"%s\",\"slot\":%d,\"estopped\":%s,\"network\":\"%s\"",
                device_.state_name(), device_.slot(), device_.estopped() ? "true" : "false",
                network_ == Network::Setup ? "setup" : "station");
  return {200, body + buf + ",\"link\":" + json_string(link_) + "}"};
}

Response Api::settings() const {
  Settings s = settings_.load();
  std::string body = "{\"wifi_ssid\":" + json_string(s.wifi_ssid) +
                     ",\"wifi_password_set\":" + (s.wifi_password.empty() ? "false" : "true") +
                     ",\"servers\":[";
  for (size_t i = 0; i < s.servers.size(); ++i) body += (i ? "," : "") + json_string(s.servers[i]);
  return {200, body + "]}"};
}

Response Api::save_settings(const char* body) {
  JsonObject fields;
  if (!read_object(body, fields) || !fields.strings.count("wifi_ssid") ||
      !fields.lists.count("servers"))
    return error(400, "send wifi_ssid, servers and (to change it) wifi_password");
  Settings old = settings_.load();
  Settings next{fields.strings["wifi_ssid"], old.wifi_password, fields.lists["servers"]};
  if (fields.strings.count("wifi_password")) next.wifi_password = fields.strings["wifi_password"];
  if (const char* problem = settings_problem(next)) return error(400, problem);
  if (!settings_.save(next)) return error(500, "the settings could not be stored");
  bool rejoin = next.wifi_ssid != old.wifi_ssid || next.wifi_password != old.wifi_password;
  if (!rejoin) return kOk;
  return {200, "{\"ok\":true,\"restart\":true}", true};
}

Response Api::songs() const {
  std::string body = "{\"slots\":" + std::to_string(kSongSlots) + ",\"songs\":[";
  bool first = true;
  for (int slot = 0; slot < kSongSlots; ++slot) {
    if (!device_.songs().has(slot)) continue;
    body += (first ? "{\"slot\":" : ",{\"slot\":") + std::to_string(slot) +
            ",\"title\":" + json_string(device_.songs().title(slot)) + "}";
    first = false;
  }
  return {200, body + "]}"};
}

}  // namespace duet
