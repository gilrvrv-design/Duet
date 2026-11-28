#include "duet_settings.hpp"

namespace duet {

const char* settings_problem(const Settings& s) {
  // 802.11 limits: an SSID is 1-32 bytes; a WPA2 passphrase is 8-63 characters.
  if (s.wifi_ssid.empty() || s.wifi_ssid.size() > 32) return "the network name must be 1-32 bytes";
  if (!s.wifi_password.empty() && (s.wifi_password.size() < 8 || s.wifi_password.size() > 63))
    return "a Wi-Fi password is 8-63 characters, or empty for an open network";
  if (s.servers.size() > kMaxServers) return "at most 4 servers";
  for (const std::string& url : s.servers) {
    bool scheme = url.rfind("http://", 0) == 0 || url.rfind("https://", 0) == 0;
    if (!scheme || url.size() > kMaxServerUrl || url.find_first_of(" \"\\\n") != std::string::npos)
      return "a server is an http:// or https:// address of at most 128 characters";
  }
  return nullptr;
}

}  // namespace duet
