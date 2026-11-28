// A small HTTP/1.1 server for the native device: one request per connection, answered
// and closed, on the same select() loop as the serial link. Enough for the web app and
// its tests; the ESP32 uses its own web server over the same duet::Api.
#pragma once
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cstdio>
#include <cstring>
#include <functional>
#include <map>
#include <string>

struct HttpReply {
  int status;
  std::string type;  // Content-Type
  std::string body;
  bool gzip = false;  // the body is gzip-compressed
};

class HttpServer {
 public:
  using Handler = std::function<HttpReply(const std::string& method, const std::string& path)>;

  explicit HttpServer(Handler handler) : handler_(std::move(handler)) {}

  int listen_on(int port) {  // returns the port (port 0 picks a free one)
    fd_ = socket(AF_INET, SOCK_STREAM, 0);
    int yes = 1;
    setsockopt(fd_, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof yes);
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    addr.sin_port = htons(static_cast<uint16_t>(port));
    if (bind(fd_, reinterpret_cast<sockaddr*>(&addr), sizeof addr) || listen(fd_, 8)) {
      std::perror("duet_device http");
      std::exit(1);
    }
    socklen_t len = sizeof addr;
    getsockname(fd_, reinterpret_cast<sockaddr*>(&addr), &len);
    return ntohs(addr.sin_port);
  }

  int watch(fd_set& fds) const {  // the highest fd added
    FD_SET(fd_, &fds);
    int top = fd_;
    for (auto& [fd, _] : pending_) {
      FD_SET(fd, &fds);
      top = std::max(top, fd);
    }
    return top;
  }

  void serve(const fd_set& fds) {
    if (FD_ISSET(fd_, &fds)) pending_[accept(fd_, nullptr, nullptr)];
    for (auto it = pending_.begin(); it != pending_.end();) {
      if (FD_ISSET(it->first, &fds) && read_from(it->first, it->second)) {
        close(it->first);
        it = pending_.erase(it);
      } else {
        ++it;
      }
    }
  }

 private:
  static constexpr size_t kMaxRequest = 8192;

  // Reads what has arrived; true when the connection is done with (answered or dropped).
  bool read_from(int fd, std::string& request) {
    char buf[1024];
    ssize_t n = recv(fd, buf, sizeof buf, 0);
    if (n <= 0) return true;
    request.append(buf, static_cast<size_t>(n));
    if (request.find("\r\n\r\n") == std::string::npos)
      return request.size() > kMaxRequest && (answer(fd, {431, "text/plain", "too large"}), true);
    char method[16], target[1024];
    if (std::sscanf(request.c_str(), "%15s %1023s", method, target) != 2) {
      answer(fd, {400, "text/plain", "bad request"});
      return true;
    }
    std::string path = target;
    path = path.substr(0, path.find('?'));
    answer(fd, handler_(method, path));
    return true;
  }

  static void answer(int fd, const HttpReply& reply) {
    std::string head = "HTTP/1.1 " + std::to_string(reply.status) + " " + reason(reply.status) +
                       "\r\nContent-Type: " + reply.type +
                       "\r\nContent-Length: " + std::to_string(reply.body.size()) +
                       (reply.gzip ? "\r\nContent-Encoding: gzip" : "") +
                       "\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n";
    std::string out = head + reply.body;
    for (size_t sent = 0; sent < out.size();) {
      ssize_t n = send(fd, out.data() + sent, out.size() - sent, 0);
      if (n <= 0) return;
      sent += static_cast<size_t>(n);
    }
  }

  static const char* reason(int status) {
    switch (status) {
      case 200: return "OK";
      case 400: return "Bad Request";
      case 404: return "Not Found";
      case 405: return "Method Not Allowed";
      case 409: return "Conflict";
      case 431: return "Request Header Fields Too Large";
      default: return "Error";
    }
  }

  Handler handler_;
  int fd_ = -1;
  std::map<int, std::string> pending_;
};
