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

// Where the value of "key" starts in a JSON object (keys are matched as keys: a string
// value that reads like a key is skipped), or nullptr if the object has no such key.
const char* find_key(const char* json, const char* key);

// The string value of "key" in a JSON object. False if there is none, or it is not a
// valid string.
bool string_field(const char* json, const char* key, std::string& out);

// `text` as a JSON string: quoted, with quotes, backslashes and control characters escaped.
std::string json_string(const std::string& text);

}  // namespace duet
