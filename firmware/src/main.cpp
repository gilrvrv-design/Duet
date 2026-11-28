// ESP32 entry point: real hardware behind duet::Hal, the WebSocket and serial links, and
// the main loop. All decisions live in the tested core (lib/duet_core); this file only
// connects it to the hardware.
#include <Adafruit_NeoPixel.h>
#include <Arduino.h>
#include <ESPmDNS.h>
#include <FastAccelStepper.h>
#include <WebSocketsServer.h>
#include <WiFi.h>
#include <esp_timer.h>

#include "board.h"  // from boards/<name>/, chosen by the PlatformIO environment
#include "rig.h"
#include "duet_device.hpp"
#include "duet_executor.hpp"
#include "flash_songs.h"
#include "serial_link.h"
#ifdef DUET_WOKWI
#include "wokwi.h"  // simulator build: Wokwi's open Wi-Fi and a virtual home sensor
#else
#include "secrets.h"
#endif

namespace {

int64_t now_us() { return esp_timer_get_time(); }  // 64-bit microseconds since boot

class Esp32Hal : public duet::Hal {
 public:
  void begin() {
    engine_.init();
    stepper_ = engine_.stepperConnectToPin(PIN_STEP);
    stepper_->setDirectionPin(PIN_DIR);
    stepper_->setEnablePin(PIN_ENABLE);
    stepper_->setAutoEnable(true);
    pinMode(PIN_SOLENOID, OUTPUT);
    digitalWrite(PIN_SOLENOID, LOW);
    pinMode(PIN_HOME, INPUT);
    Serial2.begin(31250, SERIAL_8N1, -1, PIN_MIDI_TX);  // MIDI out: transmit only
    strip_.begin();
    strip_.setBrightness(LED_BRIGHTNESS);
    strip_.clear();
    strip_.show();
  }

  void move_to(int32_t steps, float speed, float accel) override {
    stepper_->setSpeedInHz(static_cast<uint32_t>(speed));
    stepper_->setAcceleration(static_cast<int32_t>(accel));
    stepper_->moveTo(steps);
  }
  void stop() override { stepper_->forceStop(); }
  bool is_moving() const override { return stepper_->isRunning(); }
  int32_t position() const override { return stepper_->getCurrentPosition(); }
  void set_position(int32_t steps) override {
#ifdef DUET_WOKWI
    home_offset_ += stepper_->getCurrentPosition() - steps;  // the carriage does not move
#endif
    stepper_->setCurrentPosition(steps);
  }
  bool home_sensor() const override {
    bool level = digitalRead(PIN_HOME) == HIGH;
    bool sensed = HOME_ACTIVE_LOW ? !level : level;
#ifdef DUET_WOKWI
    // Nothing in the simulator trips the sensor, so the carriage's true distance from
    // the home end is tracked here. The home button in the diagram still works too.
    sensed = sensed || stepper_->getCurrentPosition() + home_offset_ <= 0;
#endif
    return sensed;
  }
  void solenoid(bool on) override { digitalWrite(PIN_SOLENOID, on ? HIGH : LOW); }
  void led_fill(int first, int count, uint8_t r, uint8_t g, uint8_t b) override {
    strip_.fill(Adafruit_NeoPixel::Color(r, g, b), first, count);
  }
  void led_show() override { strip_.show(); }
  void led_clear() override {
    strip_.clear();
    strip_.show();
  }
  void midi(uint8_t status, uint8_t data1, uint8_t data2) override {
    const uint8_t bytes[] = {status, data1, data2};
    Serial2.write(bytes, sizeof bytes);
  }

 private:
  FastAccelStepperEngine engine_;
  FastAccelStepper* stepper_ = nullptr;
#ifdef DUET_WOKWI
  int32_t home_offset_ = WOKWI_START_STEPS;  // power-on: the carriage is this far from home
#endif
  Adafruit_NeoPixel strip_{LED_COUNT, PIN_LEDS, NEO_GRB + NEO_KHZ800};
};

WebSocketsServer server(WS_PORT);
int8_t client = -1;  // one Hub at a time

class Link : public duet::Sink {
 public:
  void send(const char* json) override {
    if (client >= 0) server.sendTXT(static_cast<uint8_t>(client), json);
    Serial.println(json);  // serial mirror for bench work and as a fallback link
  }
};

constexpr duet::Identity IDENTITY{DEVICE_ID, BOARD, PROFILE_ID, FEATURES, BOARD_CHANNELS};

Esp32Hal hal;
Link link;
duet::Executor executor(hal, link, BOARD_CHANNELS);
FlashSongStore songs;
duet::Device device(executor, songs, link);  // songs stored in flash, played without the Hub

// The play button: a press (stable low for PLAY_DEBOUNCE_MS) plays the next stored song,
// or stops the one playing.
void read_play_button() {
  static bool pressed = false;
  static uint32_t changed_ms = 0;
  bool low = digitalRead(PIN_PLAY) == LOW;
  uint32_t now = millis();
  if (low == pressed) {
    changed_ms = now;
  } else if (now - changed_ms >= PLAY_DEBOUNCE_MS) {
    pressed = low;
    if (pressed) device.button(now_us());
  }
}

void on_ws_event(uint8_t num, WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED: {
      client = static_cast<int8_t>(num);
      device.greet(IDENTITY);
      break;
    }
    case WStype_DISCONNECTED:
      if (client == static_cast<int8_t>(num)) client = -1;
      break;
    case WStype_TEXT: {
      if (length > duet::kMaxMessage) {  // never act on a cut-off message
        device.on_oversize(now_us());
        break;
      }
      char buf[duet::kMaxMessage + 1];
      memcpy(buf, payload, length);
      buf[length] = '\0';
      device.on_message(buf, now_us());
      break;
    }
    default:
      break;
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  hal.begin();
  pinMode(PIN_ESTOP, ESTOP_NEEDS_EXTERNAL_PULLUP ? INPUT : INPUT_PULLUP);
  pinMode(PIN_PLAY, INPUT_PULLUP);
  if (!songs.begin_fs()) Serial.println("duet: flash storage failed; songs cannot be stored");
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // power saving adds tens of ms of latency
#ifdef DUET_WOKWI
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, WIFI_CHANNEL);
#else
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
#endif
  while (WiFi.status() != WL_CONNECTED) delay(100);
  MDNS.begin(DEVICE_ID);
  MDNS.addService("duet", "tcp", WS_PORT);  // the Hub finds the rig as _duet._tcp
  server.begin();
  server.onEvent(on_ws_event);
  Serial.printf("duet: %s on ws://%s:%u\n", DEVICE_ID, WiFi.localIP().toString().c_str(), WS_PORT);
}

void loop() {
  server.loop();
  read_serial(device, now_us());
  read_play_button();
  if (digitalRead(PIN_ESTOP) == LOW && !executor.estopped()) {
    device.on_message("{\"type\":\"estop\",\"seq\":0}", now_us());  // also ends a song
  }
  device.poll(now_us());
}
