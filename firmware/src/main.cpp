// ESP32 entry point: real hardware behind duet::Hal, the WebSocket and serial links, the
// web app and device API (docs/device-api.md), and the main loop. All decisions live in the tested core (lib/duet_core); this file only
// connects it to the hardware.
#include <Adafruit_NeoPixel.h>
#include <Arduino.h>
#include <DNSServer.h>
#include <ESPmDNS.h>
#include <FastAccelStepper.h>
#include <WebServer.h>
#include <WebSocketsServer.h>
#include <WiFi.h>
#include <esp_timer.h>

#include "board.h"  // from boards/<name>/, chosen by the PlatformIO environment
#include "rig.h"
#include "duet_api.hpp"
#include "duet_device.hpp"
#include "duet_executor.hpp"
#include "flash_songs.h"
#include "nvs_settings.h"
#include "serial_link.h"
#include "web_assets.h"  // generated from firmware/web/ (tools/embed_web.py)
#ifdef DUET_WOKWI
#include "wokwi.h"  // simulator build: Wokwi's open Wi-Fi and a virtual home sensor
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
NvsSettingsStore settings;
duet::Api api(device, IDENTITY, settings);
WebServer web(HTTP_PORT);
DNSServer dns;  // on the setup network, every name leads to the setup page
bool setup_network = false;

// Every request: the device API under /api/, else a file of the web app. Requests are
// small and quick (the page asks once a second), so the main loop is not held up.
void serve_web() {
  const String& path = web.uri();
  if (path.startsWith("/api/")) {
    const char* method = web.method() == HTTP_GET ? "GET" : web.method() == HTTP_POST ? "POST" : "";
    duet::Response r = api.handle(method, path.c_str(), web.arg("plain").c_str(), now_us());
    web.sendHeader("Cache-Control", "no-store");
    web.send(r.status, "application/json", r.body.c_str());
    if (r.restart) {  // new Wi-Fi settings: restart to join that network
      delay(500);     // let the answer reach the phone first
      ESP.restart();
    }
    return;
  }
  const duet::WebAsset* asset = duet::find_asset(duet::kWebAssets, path.c_str());
  if (asset == nullptr && setup_network) {  // a phone checking for a login page: show ours
    web.sendHeader("Location", "http://" + WiFi.softAPIP().toString() + "/");
    web.send(302, "text/plain", "");
    return;
  }
  if (asset == nullptr) {
    web.send(404, "text/plain", "not found");
    return;
  }
  web.sendHeader("Content-Encoding", "gzip");
  web.send_P(200, asset->type, reinterpret_cast<const char*>(asset->gzip), asset->size);
}

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

// Join the saved network, or (none saved, or it cannot be joined) open the setup network
// "Duet-setup" for a phone to connect to. With a saved network the board keeps trying it
// meanwhile, and closes the setup network once it has joined (loop()).
void start_network() {
  WiFi.setSleep(false);  // power saving adds tens of ms of latency
#ifdef DUET_WOKWI
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, WIFI_CHANNEL);
  while (WiFi.status() != WL_CONNECTED) delay(100);
#else
  duet::Settings saved = settings.load();
  if (saved.has_wifi()) {
    WiFi.mode(WIFI_STA);
    WiFi.begin(saved.wifi_ssid.c_str(), saved.wifi_password.c_str());
    for (uint32_t start = millis(); millis() - start < JOIN_TIMEOUT_MS;) {
      if (WiFi.status() == WL_CONNECTED) return;
      delay(100);
    }
  }
  WiFi.mode(saved.has_wifi() ? WIFI_AP_STA : WIFI_AP);
  WiFi.softAP(SETUP_SSID);
  if (saved.has_wifi()) WiFi.begin(saved.wifi_ssid.c_str(), saved.wifi_password.c_str());
  dns.start(53, "*", WiFi.softAPIP());
  setup_network = true;
  api.set_network(duet::Network::Setup);
  Serial.printf("duet: no Wi-Fi; join \"%s\" and open http://%s\n", SETUP_SSID,
                WiFi.softAPIP().toString().c_str());
#endif
}

void leave_setup_network_once_joined() {
  if (!setup_network || WiFi.status() != WL_CONNECTED) return;
  dns.stop();
  WiFi.softAPdisconnect(true);
  WiFi.mode(WIFI_STA);
  setup_network = false;
  api.set_network(duet::Network::Station);
  Serial.printf("duet: joined; the app on http://%s.local\n", DEVICE_ID);
}

}  // namespace

void setup() {
  Serial.begin(115200);
  hal.begin();
  pinMode(PIN_ESTOP, ESTOP_NEEDS_EXTERNAL_PULLUP ? INPUT : INPUT_PULLUP);
  pinMode(PIN_PLAY, INPUT_PULLUP);
  if (!songs.begin_fs()) Serial.println("duet: flash storage failed; songs cannot be stored");
  start_network();
  MDNS.begin(DEVICE_ID);
  MDNS.addService("duet", "tcp", WS_PORT);  // the Hub finds the rig as _duet._tcp
  MDNS.addService("http", "tcp", HTTP_PORT);
  server.begin();
  server.onEvent(on_ws_event);
  web.onNotFound(serve_web);
  web.begin();
  if (!setup_network)
    Serial.printf("duet: %s on ws://%s:%u, the app on http://%s.local\n", DEVICE_ID,
                  WiFi.localIP().toString().c_str(), WS_PORT, DEVICE_ID);
}

void loop() {
  server.loop();
  web.handleClient();
  if (setup_network) dns.processNextRequest();
  leave_setup_network_once_joined();
  read_serial(device, now_us());
  read_play_button();
  if (digitalRead(PIN_ESTOP) == LOW && !executor.estopped()) {
    device.on_message("{\"type\":\"estop\",\"seq\":0}", now_us());  // also ends a song
  }
  device.poll(now_us());
}
