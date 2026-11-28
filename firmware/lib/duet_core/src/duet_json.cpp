#include "duet_json.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace duet {
namespace {

struct Reader {
  const char* p;

  void space() {
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') ++p;
  }
  bool take(char c) {
    space();
    if (*p != c) return false;
    ++p;
    return true;
  }
  void utf8(unsigned code, std::string& out) {
    if (code < 0x80) {
      out += static_cast<char>(code);
    } else if (code < 0x800) {
      out += static_cast<char>(0xC0 | code >> 6);
      out += static_cast<char>(0x80 | (code & 0x3F));
    } else {
      out += static_cast<char>(0xE0 | code >> 12);
      out += static_cast<char>(0x80 | (code >> 6 & 0x3F));
      out += static_cast<char>(0x80 | (code & 0x3F));
    }
  }
  bool string(std::string& out) {
    if (!take('"')) return false;
    out.clear();
    for (;;) {
      char c = *p++;
      if (c == '"') return true;
      if (c == '\0' || static_cast<unsigned char>(c) < 0x20) return false;
      if (c != '\\') {
        out += c;
        continue;
      }
      switch (char e = *p++) {
        case '"': case '\\': case '/': out += e; break;
        case 'b': out += '\b'; break;
        case 'f': out += '\f'; break;
        case 'n': out += '\n'; break;
        case 'r': out += '\r'; break;
        case 't': out += '\t'; break;
        case 'u': {
          char hex[5] = {p[0], p[1], p[2], p[3], '\0'};
          char* end = nullptr;
          unsigned long code = std::strtoul(hex, &end, 16);
          if (end != hex + 4) return false;
          if (code >= 0xD800 && code <= 0xDFFF) return false;  // surrogates: not supported
          utf8(static_cast<unsigned>(code), out);
          p += 4;
          break;
        }
        default: return false;
      }
    }
  }
  bool list(std::vector<std::string>& out) {
    if (!take('[')) return false;
    out.clear();
    if (take(']')) return true;
    do {
      out.emplace_back();
      if (!string(out.back())) return false;
    } while (take(','));
    return take(']');
  }
};

}  // namespace

bool read_object(const char* json, JsonObject& out) {
  out = JsonObject{};
  Reader r{json};
  if (!r.take('{')) return false;
  if (!r.take('}')) {
    do {
      std::string key;
      if (!r.string(key) || !r.take(':')) return false;
      r.space();
      bool ok = *r.p == '[' ? r.list(out.lists[key]) : r.string(out.strings[key]);
      if (!ok) return false;
    } while (r.take(','));
    if (!r.take('}')) return false;
  }
  r.space();
  return *r.p == '\0';
}

bool string_field(const char* json, const char* key, std::string& out) {
  std::string pattern = "\"" + std::string(key) + "\"";
  const char* at = std::strstr(json, pattern.c_str());
  if (at == nullptr) return false;
  Reader r{at + pattern.size()};
  return r.take(':') && r.string(out);
}

std::string json_string(const std::string& text) {
  std::string out = "\"";
  for (char c : text) {
    if (c == '"' || c == '\\') {
      out += '\\';
      out += c;
    } else if (static_cast<unsigned char>(c) < 0x20) {
      char esc[8];
      std::snprintf(esc, sizeof esc, "\\u%04x", static_cast<unsigned>(c));
      out += esc;
    } else {
      out += c;
    }
  }
  return out + "\"";
}

}  // namespace duet
