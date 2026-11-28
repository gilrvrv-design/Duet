// A small JSON reader and writer for the device API's request and answer bodies: an
// object whose values are strings or arrays of strings (the settings). The real-time
// protocol has its own, flatter parser (duet_protocol.cpp).
#pragma once
#include <map>
#include <string>
#include <vector>

namespace duet {

struct JsonObject {
  std::map<std::string, std::string> strings;
  std::map<std::string, std::vector<std::string>> lists;
};

// False unless `json` is exactly one such object (whitespace aside).
bool read_object(const char* json, JsonObject& out);

// `text` as a JSON string: quoted, with quotes, backslashes and control characters escaped.
std::string json_string(const std::string& text);

}  // namespace duet
