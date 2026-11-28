// The firmware for Espressif's QEMU ESP32 emulator (pio run -e qemu): the real core on
// the real chip's CPU, clock and serial port, with the simulated hardware of the native
// tests instead of motor, solenoid and LED drivers, which QEMU does not emulate.
//
// The Hub talks to it over the serial port, one JSON message per line, exactly as to the
// rig. Lines starting with '#' report what the simulated hardware did (duet_report_hal.hpp).
#include <Arduino.h>
#include <esp_timer.h>

#include "board.h"  // boards/qemu
#include "rig.h"
#include "duet_device.hpp"
#include "duet_executor.hpp"
#include "duet_report_hal.hpp"
#include "serial_link.h"

namespace {

int64_t now_us() { return esp_timer_get_time(); }

constexpr int32_t START_STEPS = 4000;  // power-on: the carriage is this far from home

class SerialSink : public duet::Sink {
 public:
  void send(const char* json) override { Serial.println(json); }
};

duet::ReportingHal hal([](const char* line) { Serial.println(line); });
SerialSink link;
duet::Executor executor(hal, link);
duet::MemorySongStore songs;  // QEMU: songs in RAM; the rig keeps them in flash
duet::Device device(executor, songs, link);

}  // namespace

void setup() {
  Serial.begin(115200);
  hal.now_us = now_us();
  hal.place(START_STEPS);
  // On the serial link the greeting opens the conversation at boot.
  device.greet(duet::Identity{DEVICE_ID, BOARD, PROFILE_ID, FEATURES});
}

void loop() {
  int64_t t = now_us();
  hal.now_us = t;
  read_serial(device, t);
  device.poll(t);
}
