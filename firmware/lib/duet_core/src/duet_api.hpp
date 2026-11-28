// The device API: what the web app (and anything else on the network) asks the device,
// over HTTP. The transport is the board's (the ESP32's web server, the native device's
// socket); every answer is decided here, so all boards answer alike.
//
//   GET  /api/info                {"hello":{..},"channels":[{..},..],"state":..,"slot":..,
//                                  "estopped":..}: hello and channels as the Hub hears them
//   GET  /api/songs               {"slots":8,"songs":[{"slot":k},..]}: the stored songs
//   POST /api/songs/<k>/play      play stored song k
//   POST /api/stop                stop playing
//   POST /api/estop               emergency stop (latched, as the button)
//
// Errors are {"error":"..."} with 404 (no such path), 405 (wrong method) or 409 (the
// device cannot do it now: already playing, no song there, emergency stop).
#pragma once
#include <cstdint>
#include <string>

#include "duet_device.hpp"
#include "duet_protocol.hpp"

namespace duet {

struct Response {
  int status;
  std::string body;  // JSON
};

class Api {
 public:
  Api(Device& device, const Identity& id) : device_(device), id_(id) {}

  Response handle(const char* method, const char* path, int64_t now_us);

 private:
  Response info() const;
  Response songs() const;

  Device& device_;
  Identity id_;
};

}  // namespace duet
