// The device API: what the web app (and anything else on the network) asks the device,
// over HTTP. The transport is the board's (the ESP32's web server, the native device's
// socket); every answer is decided here, so all boards answer alike.
//
//   GET  /api/info                {"hello":{..},"channels":[{..},..],"state":..,"slot":..,
//                                  "estopped":..,"network":"station"|"setup"}: hello and
//                                  channels as the Hub hears them
//   GET  /api/songs               {"slots":8,"songs":[{"slot":k,"title":".."},..]}
//   POST /api/songs/<k>/play      play stored song k
//   POST /api/stop                stop playing
//   POST /api/estop               emergency stop (latched, as the button)
//   GET  /api/settings            {"wifi_ssid":..,"wifi_password_set":bool,"servers":[..]}
//                                 (the password itself is never sent back)
//   POST /api/settings            {"wifi_ssid":..,"wifi_password":..,"servers":[..]}; leave
//                                 out wifi_password to keep the saved one. A new network
//                                 answers {"ok":true,"restart":true}: the board restarts
//                                 to join it.
//
// Errors are {"error":"..."} with 400 (a bad request body), 404 (no such path), 405
// (wrong method) or 409 (the device cannot do it now: already playing, no song there,
// emergency stop).
#pragma once
#include <cstdint>
#include <string>

#include "duet_device.hpp"
#include "duet_protocol.hpp"
#include "duet_settings.hpp"

namespace duet {

struct Response {
  int status;
  std::string body;  // JSON
  bool restart = false;  // the board restarts once the answer is sent
};

// How the board is on the network: joined to the saved Wi-Fi ("station"), or serving
// its own setup network for a phone to connect to ("setup").
enum class Network { Station, Setup };

class Api {
 public:
  Api(Device& device, SettingsStore& settings) : device_(device), settings_(settings) {}

  void set_network(Network network) { network_ = network; }
  Response handle(const char* method, const char* path, const char* body, int64_t now_us);

 private:
  Response info() const;
  Response songs() const;
  Response settings() const;
  Response save_settings(const char* body);

  Device& device_;
  SettingsStore& settings_;
  Network network_ = Network::Station;
};

}  // namespace duet
