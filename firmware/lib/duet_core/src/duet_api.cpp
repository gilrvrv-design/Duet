#include "duet_api.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace duet {

namespace {

Response error(int status, const char* why) {
  return {status, std::string("{\"error\":\"") + why + "\"}"};
}

const Response kOk{200, "{\"ok\":true}"};

// The slot in "/api/songs/<k>/play", or -1 if the path is not that.
int play_slot(const char* path) {
  const char* prefix = "/api/songs/";
  size_t n = std::strlen(prefix);
  if (std::strncmp(path, prefix, n) != 0) return -1;
  char* end = nullptr;
  long slot = std::strtol(path + n, &end, 10);
  if (end == path + n || std::strcmp(end, "/play") != 0 || slot < 0 || slot >= kSongSlots)
    return -1;
  return static_cast<int>(slot);
}

}  // namespace

Response Api::handle(const char* method, const char* path, int64_t now_us) {
  bool get = std::strcmp(method, "GET") == 0;
  bool post = std::strcmp(method, "POST") == 0;
  if (std::strcmp(path, "/api/info") == 0) return get ? info() : error(405, "use GET");
  if (std::strcmp(path, "/api/songs") == 0) return get ? songs() : error(405, "use GET");
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
  int slot = play_slot(path);
  if (slot >= 0) {
    if (!post) return error(405, "use POST");
    const char* why = device_.request_play(slot, now_us);
    return why ? error(409, why) : kOk;
  }
  return error(404, "no such path");
}

Response Api::info() const {
  char buf[kMaxMessage + 1];
  write_hello(buf, sizeof buf, id_);
  std::string body = std::string("{\"hello\":") + buf + ",\"channels\":[";
  for (size_t ch = 0; ch < id_.channels.count; ++ch) {
    write_channel(buf, sizeof buf, static_cast<int>(ch), id_.channels.items[ch],
                  device_.config());
    body += (ch ? "," : "") + std::string(buf);
  }
  std::snprintf(buf, sizeof buf, "],\"state\":\"%s\",\"slot\":%d,\"estopped\":%s}",
                device_.state_name(), device_.slot(), device_.estopped() ? "true" : "false");
  return {200, body + buf};
}

Response Api::songs() const {
  std::string body = "{\"slots\":" + std::to_string(kSongSlots) + ",\"songs\":[";
  bool first = true;
  for (int slot = 0; slot < kSongSlots; ++slot) {
    if (!device_.songs().has(slot)) continue;
    body += (first ? "{\"slot\":" : ",{\"slot\":") + std::to_string(slot) + "}";
    first = false;
  }
  return {200, body + "]}"};
}

}  // namespace duet
