// The firmware as a Linux process: the same core, serial framing and stubbed hardware as
// the QEMU build, on a real-time clock, with the serial link carried over TCP. The Hub
// connects with tcp://127.0.0.1:<port>, exactly as to QEMU or a rig on a serial bridge.
//
//   duet_device [--port N] [--http-port N] [--clock-offset-us N] [--start-steps N]
//
// Port 0 picks a free port. The first stdout line is "listening <port>" (the serial
// link), the second "http <port>" (the device API and web app, as on the ESP32). Lines starting
// with '#' report what the stubbed hardware did (duet_report_hal.hpp). One Hub at a time;
// the device keeps its state (and its stored songs) between connections, like a powered
// rig. A line "press" on stdin presses the play button.
//
// Wi-Fi settings are kept in RAM. With none saved the device reports its setup network,
// as an ESP32 does on first boot; saving a network stands for the restart that joins it.
#include <arpa/inet.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <string>

#include "board.h"  // boards/native
#include "rig.h"
#include "duet_api.hpp"
#include "duet_device.hpp"
#include "duet_executor.hpp"
#include "duet_line_reader.hpp"
#include "duet_report_hal.hpp"
#include "http_server.hpp"
#include "web_assets.h"  // generated from firmware/web/ (tools/embed_web.py)

namespace {

int64_t clock_offset_us = 987654321;  // the device clock is not the Hub's: sync must work
int client = -1;

int64_t now_us() {
  timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return ts.tv_sec * 1000000LL + ts.tv_nsec / 1000 + clock_offset_us;
}

void send_line(const char* line) {
  if (client < 0) return;
  std::string out = std::string(line) + "\n";
  if (send(client, out.data(), out.size(), 0) < 0) {
    close(client);
    client = -1;
  }
}

// What the stubbed hardware did: to the Hub's console, and to stdout, so it can be seen
// when no Hub is connected (playing from memory).
void report(const char* line) {
  std::printf("%s\n", line);
  std::fflush(stdout);
  send_line(line);
}

struct SocketSink : duet::Sink {
  void send(const char* json) override { send_line(json); }
};

int listen_on(int port) {
  int fd = socket(AF_INET, SOCK_STREAM, 0);
  int yes = 1;
  setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof yes);
  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  addr.sin_port = htons(static_cast<uint16_t>(port));
  if (bind(fd, reinterpret_cast<sockaddr*>(&addr), sizeof addr) || listen(fd, 1)) {
    std::perror("duet_device");
    std::exit(1);
  }
  socklen_t len = sizeof addr;
  getsockname(fd, reinterpret_cast<sockaddr*>(&addr), &len);
  std::printf("listening %d\n", ntohs(addr.sin_port));
  std::fflush(stdout);
  return fd;
}

}  // namespace

int main(int argc, char** argv) {
  int port = 0;
  int http_port = 0;
  int32_t start_steps = 4000;
  for (int i = 1; i + 1 < argc; i += 2) {
    std::string flag = argv[i];
    if (flag == "--port") port = std::atoi(argv[i + 1]);
    else if (flag == "--http-port") http_port = std::atoi(argv[i + 1]);
    else if (flag == "--clock-offset-us") clock_offset_us = std::atoll(argv[i + 1]);
    else if (flag == "--start-steps") start_steps = std::atoi(argv[i + 1]);
  }
  std::signal(SIGPIPE, SIG_IGN);

  duet::ReportingHal hal(report);
  SocketSink sink;
  duet::Executor executor(hal, sink, BOARD_CHANNELS);
  duet::MemorySongStore songs;
  duet::Device device(executor, songs, sink,
                     duet::Identity{DEVICE_ID, BOARD, PROFILE_ID, FEATURES, BOARD_CHANNELS});
  duet::MemorySettingsStore settings;
  duet::Api api(device, settings);
  api.set_network(duet::Network::Setup);  // nothing saved yet
  HttpServer http([&](const std::string& method, const std::string& path,
                      const std::string& body) {
    if (path.rfind("/api/", 0) == 0) {
      duet::Response r = api.handle(method.c_str(), path.c_str(), body.c_str(), hal.now_us);
      if (r.restart) api.set_network(duet::Network::Station);  // "restarted and joined"
      return HttpReply{r.status, "application/json", r.body};
    }
    const duet::WebAsset* asset = duet::find_asset(duet::kWebAssets, path.c_str());
    if (asset == nullptr) return HttpReply{404, "text/plain", "not found"};
    return HttpReply{200, asset->type,
                     std::string(reinterpret_cast<const char*>(asset->gzip), asset->size), true};
  });
  duet::LineReader reader;
  std::string console;  // stdin: "press" presses the play button
  bool stdin_open = true;
  hal.now_us = now_us();
  hal.place(start_steps);
  int server = listen_on(port);
  std::printf("http %d\n", http.listen_on(http_port));
  std::fflush(stdout);

  for (;;) {
    fd_set fds;
    FD_ZERO(&fds);
    FD_SET(server, &fds);
    if (stdin_open) FD_SET(STDIN_FILENO, &fds);
    if (client >= 0) FD_SET(client, &fds);
    int top = std::max({server, client, http.watch(fds)});
    timeval wait{0, 100};  // poll the executor at least every 0.1 ms
    select(top + 1, &fds, nullptr, nullptr, &wait);
    hal.now_us = now_us();

    if (FD_ISSET(server, &fds)) {
      int fd = accept(server, nullptr, nullptr);
      if (client >= 0) {
        close(fd);  // one Hub at a time, like the rig
      } else {
        client = fd;
        int yes = 1;
        setsockopt(client, IPPROTO_TCP, TCP_NODELAY, &yes, sizeof yes);  // greets when asked
      }
    }
    if (client >= 0 && FD_ISSET(client, &fds)) {
      char buf[512];
      ssize_t n = recv(client, buf, sizeof buf, 0);
      if (n <= 0) {
        close(client);
        client = -1;
      } else {
        for (ssize_t i = 0; i < n; ++i) reader.feed(buf[i], device, hal.now_us);
      }
    }
    if (stdin_open && FD_ISSET(STDIN_FILENO, &fds)) {
      char c;
      if (read(STDIN_FILENO, &c, 1) != 1) {
        stdin_open = false;  // end of input: no more button presses
      } else {
        if (c != '\n') {
          console += c;
        } else {
          if (console == "press") device.button(hal.now_us);
          console.clear();
        }
      }
    }
    http.serve(fds);
    device.poll(hal.now_us);
  }
}
