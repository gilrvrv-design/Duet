# Device API

The device answers HTTP requests from the web app it serves, and from anything else
on the network. Every board answers alike: the answers are decided in the firmware
core (`firmware/lib/duet_core/src/duet_api.cpp`). Only the transport differs, which is
the ESP32's web server or the native device's socket (`firmware/host/http_server.hpp`).

Every path outside `/api/` is the web app (`firmware/web/`: plain HTML, CSS and
JavaScript, with no build step). `firmware/tools/embed_web.py` compiles it into the
firmware gzipped, so a board serves it from program flash. It shows what the board
can do and what it cannot, and plays and stops the stored songs.
`tests/test_web_app.py` drives it in Chromium against the native device.

The Hub's real-time link is the device protocol (docs/device-protocol.md). The API is
for people: it shows what the device is, and it plays the songs stored on it.

| Request | Answer |
|---|---|
| `GET /api/info` | `{"hello":{..},"channels":[..],"state":"idle"\|"homing"\|"playing","slot":k,"estopped":bool}`. `hello` and `channels` are the messages the Hub hears on connecting. `slot` is the song playing or last played (-1 before any). |
| `GET /api/songs` | `{"slots":8,"songs":[{"slot":k},..]}`: the slots that hold a song |
| `POST /api/songs/<k>/play` | Home, then play stored song *k* |
| `POST /api/stop` | Stop playing |
| `POST /api/estop` | Emergency stop, latched as with the hardware button |

Success is `200 {"ok":true}`. Errors are `{"error":"..."}` with one of these statuses:
- 404: no such path;
- 405: the wrong method;
- 409: the device cannot do it now (`already playing`, `no song in that slot`,
  `emergency stop`).

On the ESP32 the app is at `http://duet-rig-1.local` (port 80, announced over mDNS).
Boards that serve it report the `web` feature; QEMU's serial-only board does not.

The native device prints `http <port>` as its second line, and `--http-port N` chooses
the port. The tests in `tests/test_device_api.py` run against it.
