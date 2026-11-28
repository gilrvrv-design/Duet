// What a person sets on the device from its setup page: the Wi-Fi network to join, and
// the servers the web app uses when they can be reached (docs/design/esp-first.md).
// Kept by the board: in NVS on the ESP32, in RAM on the native device.
#pragma once
#include <string>
#include <vector>

namespace duet {

constexpr size_t kMaxServers = 4;
constexpr size_t kMaxServerUrl = 128;

struct Settings {
  std::string wifi_ssid;      // empty: none yet, so the board opens its setup network
  std::string wifi_password;  // empty for an open network
  std::vector<std::string> servers;  // http:// or https:// base URLs

  bool has_wifi() const { return !wifi_ssid.empty(); }
};

// Why the settings cannot be used, or nullptr if they can.
const char* settings_problem(const Settings& s);

class SettingsStore {
 public:
  virtual ~SettingsStore() = default;
  virtual Settings load() const = 0;  // nothing saved: empty settings
  virtual bool save(const Settings& s) = 0;
};

class MemorySettingsStore : public SettingsStore {
 public:
  Settings load() const override { return saved_; }
  bool save(const Settings& s) override {
    saved_ = s;
    return true;
  }

 private:
  Settings saved_;
};

}  // namespace duet
