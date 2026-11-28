// What a board can do beyond the core, which every board has: the executor and its
// safety rules, the serial link, and songs (in RAM if the board has no flash storage).
// A board lists its features in board.h; the device reports them in hello. The Hub
// keeps the same list (duet.device.features); a contract test keeps them in step.
#pragma once
#include <cstddef>
#include <cstdint>

namespace duet {

enum Feature : uint32_t {
  kWifi = 1u << 0,         // the WebSocket link over Wi-Fi
  kFlash = 1u << 1,        // stored songs survive power-off
  kPlayButton = 1u << 2,   // a button that plays stored songs without the Hub
  kEstopButton = 1u << 3,  // a hardware emergency stop
};

struct FeatureName {
  Feature feature;
  const char* name;
};

constexpr FeatureName kFeatureNames[] = {
    {kWifi, "wifi"},
    {kFlash, "flash"},
    {kPlayButton, "play_button"},
    {kEstopButton, "estop_button"},
};

// Room for every feature at once in hello: `"name",` for each.
constexpr size_t features_json_length() {
  size_t total = 0;
  for (const FeatureName& f : kFeatureNames) {
    size_t len = 0;
    while (f.name[len] != '\0') ++len;
    total += len + 3;
  }
  return total;
}
constexpr size_t kFeaturesJsonMax = 96;
static_assert(features_json_length() < kFeaturesJsonMax, "feature names outgrew hello");

}  // namespace duet
