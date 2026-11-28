// The web app, as served by the device: files from firmware/web/, gzipped and compiled
// into the firmware by tools/embed_web.py (the generated web_assets.h holds kWebAssets).
#pragma once
#include <cstddef>
#include <cstring>

namespace duet {

struct WebAsset {
  const char* path;  // "/" for index.html
  const char* type;  // Content-Type
  const unsigned char* gzip;
  size_t size;
};

template <size_t N>
const WebAsset* find_asset(const WebAsset (&assets)[N], const char* path) {
  for (const WebAsset& a : assets)
    if (std::strcmp(a.path, path) == 0) return &a;
  return nullptr;
}

}  // namespace duet
