// The firmware for Espressif's QEMU ESP32 emulator (pio run -e qemu): the real core on
// the real chip's CPU, clock and serial port, with the simulated hardware of the native
// tests instead of motor, solenoid and LED drivers, which QEMU does not emulate.
//
// The Hub talks to it over the serial port, one JSON message per line, exactly as to the
// rig. Lines starting with '#' report what the simulated hardware did, for tests:
//   # strike t_us=<device us> position=<steps>
//   # led t_us=<device us> first=<led> count=<n> rgb=<r>,<g>,<b>
#include <Arduino.h>
#include <esp_timer.h>

#include "board.h"
#include "duet_executor.hpp"
#include "duet_sim_hal.hpp"
#include "serial_link.h"

namespace {

int64_t now_us() { return esp_timer_get_time(); }

constexpr int32_t START_STEPS = 4000;  // power-on: the carriage is this far from home

class QemuHal : public duet::SimHal {
 public:
  void solenoid(bool on) override {
    if (on) Serial.printf("# strike t_us=%lld position=%ld\n", now_us, (long)position());
  }
  void led_fill(int first, int count, uint8_t r, uint8_t g, uint8_t b) override {
    Serial.printf("# led t_us=%lld first=%d count=%d rgb=%u,%u,%u\n", now_us, first, count, r,
                  g, b);
  }
};

class SerialSink : public duet::Sink {
 public:
  void send(const char* json) override { Serial.println(json); }
};

QemuHal hal;
SerialSink link;
duet::Executor executor(hal, link);

}  // namespace

void setup() {
  Serial.begin(115200);
  hal.now_us = now_us();
  hal.place(START_STEPS);
  char hello[duet::kMaxMessage + 1];
  duet::write_hello(hello, sizeof hello, DEVICE_ID, PROFILE_ID, executor.config());
  Serial.println(hello);  // on the serial link, hello opens the conversation at boot
}

void loop() {
  int64_t t = now_us();
  hal.now_us = t;
  read_serial(executor, t);
  executor.poll(t);
}
