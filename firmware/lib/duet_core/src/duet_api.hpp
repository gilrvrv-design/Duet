// The device API: what the web app (and anything else on the network) asks the device,
// over HTTP. The transport is the board's (the ESP32's web server, the native device's
// socket); every answer is decided here, so all boards answer alike.
//
//   GET  /api/info                {"hello":{..},"channels":[{..},..],"state":..,"slot":..,
//                                  "estopped":..,"network":"station"|"setup"}: hello and
//                                  channels as the Hub hears them
//   GET  /api/songs               {"slots":8,"songs":[{"slot":k,"title":".."},..]}
//   PUT  /api/songs/<k>           store a song in slot k. The body is a song file: its
//                                 title line {"title":".."}, then one timed command per
//                                 line (t_us from 0), as the device keeps it in flash
//   DELETE /api/songs/<k>         forget the song in slot k
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
// Errors are {"error":"..."} with 400 (a bad request body), 404 (no such path or song),
// 405 (wrong method), 409 (the device cannot do it now: already playing, emergency stop,
// busy) or 507 (no room to store it).
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

  // PUT /api/songs/<k>, streamed for transports that receive the body in pieces (the
  // ESP32 holds a 4000-line song in flash, not in RAM): begin_upload with the path; if
  // it answers 200, upload_data for each piece, then end_upload (or abort_upload if the
  // client goes away). handle() does all of it for a body that arrives whole.
  Response begin_upload(const char* path);
  void upload_data(const char* data, size_t n);
  Response end_upload();
  void abort_upload();

 private:
  void upload_line();
  void upload_failed(int status, const char* why);
  Response info() const;
  Response songs() const;
  Response settings() const;
  Response save_settings(const char* body);

  Device& device_;
  SettingsStore& settings_;
  Network network_ = Network::Station;

  // The song being uploaded through the API.
  int upload_slot_ = -1;  // none
  int upload_lines_ = 0;  // lines read, the title line included
  int first_bad_line_ = 0;
  int failed_status_ = 0;  // the upload was refused before its end ...
  std::string failed_why_;  // ... and why
  std::string line_;
  bool line_too_long_ = false;
};

}  // namespace duet
