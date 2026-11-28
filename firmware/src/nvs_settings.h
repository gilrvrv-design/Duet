// The setup page's settings in the ESP32's NVS (non-volatile storage), so they survive
// power-off and firmware updates. The Wi-Fi password is stored as ESP-IDF stores its own
// Wi-Fi credentials: in NVS, readable by anyone with the board and a USB cable (NVS
// encryption would change that; docs/device-api.md).
#pragma once
#include <Preferences.h>

#include "duet_settings.hpp"

class NvsSettingsStore : public duet::SettingsStore {
 public:
  duet::Settings load() const override {
    Preferences p;
    p.begin(kNamespace, true);
    duet::Settings s{p.getString("ssid", "").c_str(), p.getString("password", "").c_str(), {}};
    String servers = p.getString("servers", "");  // one per line
    p.end();
    for (int start = 0; start < static_cast<int>(servers.length());) {
      int end = servers.indexOf('\n', start);
      if (end < 0) end = servers.length();
      s.servers.emplace_back(servers.substring(start, end).c_str());
      start = end + 1;
    }
    return s;
  }

  bool save(const duet::Settings& s) override {
    String servers;
    for (const std::string& url : s.servers) servers += String(servers.isEmpty() ? "" : "\n") + url.c_str();
    Preferences p;
    p.begin(kNamespace, false);
    bool ok = p.putString("ssid", s.wifi_ssid.c_str()) == s.wifi_ssid.size() &&
              p.putString("password", s.wifi_password.c_str()) == s.wifi_password.size() &&
              p.putString("servers", servers) == servers.length();
    p.end();
    return ok;
  }

 private:
  static constexpr const char* kNamespace = "duet";
};
