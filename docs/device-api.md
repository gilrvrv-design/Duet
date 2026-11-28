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

## The planner module

The planner is an optional module. With it, a MIDI file goes onto the rig with no Hub and
no server: the device reads it (`duet_midi`) and plans it (`duet_planner`). It makes
exactly the song the Hub would make of it, which `tests/test_midi_contract.py` and
`tests/test_planner_contract.py` check on hundreds of files. It plans for the rig's own
instruments (`PROFILE_ID` and `KEYBOARD_ID` in `firmware/src/rig.h`). Their data is
compiled in from the Hub's instrument files, so a rig's own calibration still goes
through the Hub (`duet --robot calibrated.yaml song ...`).

Whoever builds the firmware chooses whether to install it. It adds about 40 KB of
program and, while it plans, up to about 150 KB of RAM:

```bash
cd firmware && pio run -e esp32-classic-planner -t upload
```

(`esp32-s3-planner` likewise.) The board then reports the `planner` feature, and the page
offers MIDI files as well as song files. Every board, with the module or without,
takes song files made by the Hub (`duet song`).

## Servers

The servers saved in the settings add what the rig cannot do alone. The page checks each
one's `/v1/health` when it opens, every 30 seconds, and after the settings change. It
shows each server as up, not reachable, or failing. While one is up, the page shows its
library. "Put on the rig" asks that server for the duet as a song file for this rig
(`POST /v1/duets/{id}/song` with the rig's instrument and channels from `/api/info`),
and stores it with `PUT /api/songs/<k>`. From then on the song plays with no server.
With no server up, the page says so, and the songs on the rig still play.

The browser talks to the servers itself; the rig never waits on one. A server lets
pages from `.local` names and local-network addresses call it (CORS, README.md).
`tests/test_web_servers.py` runs the page with servers up, down and failing.

The Hub's real-time link is the device protocol (docs/device-protocol.md). The API is
for people: it shows what the device is, and it plays the songs stored on it.

| Request | Answer |
|---|---|
| `GET /api/info` | `{"hello":{..},"channels":[..],"state":"idle"\|"homing"\|"playing","slot":k,"estopped":bool,"network":"station"\|"setup","link":".."}`. `hello` and `channels` are the messages the Hub hears on connecting. `slot` is the song playing or last played (-1 before any). `network` is `setup` while the board serves its setup network. `link` is how a Hub reaches the rig: `ws://<its address>:8765` on the ESP32, the serial link's `tcp://` address on the native device. |
| `GET /api/songs` | `{"slots":8,"songs":[{"slot":k,"title":".."},..]}`: the slots that hold a song, and its title |
| `PUT /api/songs/<k>` | Store a song in slot *k*. The body is a song file (below). A bad line refuses the whole song, `400 {"error":"bad song line 12"}`, and the old song stays. Refused (409) while the rig plays, or while the Hub is storing a song. |
| `PUT /api/songs/<k>/midi?title=..` | On a board with the planner module: plan a MIDI file (the body, at most 32 KB) into slot *k*, as the Hub would (below). Answers `{"ok":true,"warnings":[..]}` (what the import ignored), or why not: `400` (not a MIDI file the device reads), `422` (the Hub refuses that score too, say a key off the keyboard). Without the module: `404 {"error":"this board has no MIDI planner"}`. |
| `DELETE /api/songs/<k>` | Forget the song in slot *k* |
| `POST /api/songs/<k>/play` | Home, then play stored song *k* |
| `POST /api/stop` | Stop playing |
| `POST /api/estop` | Emergency stop, latched as with the hardware button |
| `GET /api/settings` | `{"wifi_ssid":..,"wifi_password_set":bool,"servers":[..]}`. The password itself is never sent back. |
| `POST /api/settings` | Body `{"wifi_ssid":..,"wifi_password":..,"servers":[..]}`. Leave out `wifi_password` to keep the saved one. A new network answers `{"ok":true,"restart":true}`, and the board restarts to join it. |

Success is `200 {"ok":true}`. Errors are `{"error":"..."}` with one of these statuses:
- 400: a bad request body (settings: a network name of 1-32 bytes, a password of
  8-63 characters or none, at most 4 `http://` or `https://` servers);
- 404: no such path;
- 405: the wrong method;
- 409: the device cannot do it now (`already playing`, `emergency stop`, `the rig is
  busy playing`, `another song is being stored`);
- 507: no room in flash for the song.

## Song files

A song file is how the device keeps a song in flash, and how its API takes one. The first
line is the title, `{"title":"Rain on the Bottles"}` (at most 64 bytes). Then comes one
timed command per line, exactly as in the device protocol (docs/device-protocol.md),
with `t_us` counted from the song's start. The Hub writes one with
`CompiledSong.song_file()` (`duet.songs`).

```text
{"title":"Rain on the Bottles"}
{"type":"move_at","seq":0,"ch":0,"t_us":0,"target_steps":6400,"v_max_mm_s":500.0,"a_max_mm_s2":5000.0}
{"type":"strike_at","seq":1,"ch":0,"t_us":420000,"pulse_us":20000}
```

The ESP32 streams the body into flash as it arrives (its web server's raw upload), so
a 4000-line song never has to fit in RAM. A song uploaded this way plays exactly like
one from the Hub: every line passes the same checks.

On the ESP32 the app is at `http://duet-rig-1.local` (port 80, announced over mDNS).
Boards that serve it report the `web` feature; QEMU's serial-only board does not.

## Wi-Fi setup

A board with nothing saved, or one that cannot join its saved network within 20 seconds,
opens an open network called `Duet-setup`. On that network, every name leads to the
board (a captive portal), so a phone shows the setup page by itself. The page puts the
Wi-Fi form first while `network` is `setup`. The board keeps trying a saved network
meanwhile, and closes `Duet-setup` once it has joined.

The settings are kept in NVS, the ESP32's non-volatile storage, where ESP-IDF keeps its
own Wi-Fi credentials. Anyone holding the board and a USB cable can read them. NVS
encryption (with flash encryption) would close that gap; it is not enabled.

The native device keeps settings in RAM and starts with none (`network` is `setup`).
Saving a network stands for the restart that joins it.

## Practice

A server can also play a library duet on the rig live, while it listens to the pianist:
- **Play together:** the bot plays in time.
- **Wait for me:** the bot waits for each of the pianist's notes.
- **Follow me:** the bot keeps the pianist's tempo.

The listening needs a MIDI keyboard or a microphone on the **server's** machine. A page
served over plain `http://` cannot use the browser's own microphone or MIDI. The server
lists what it has (`GET /v1/live/inputs`); a server with neither can only play together.

On "Practise" the page asks the server to start (`POST /v1/live`). It sends the duet, the
mode, the input, and how to reach this rig: `link` from `/api/info`. The server connects
to the rig over that link and plays (`duet.live`). The page follows it
(`GET /v1/live/{id}`), and at the end shows how long the bot waited, or how it followed,
and the grade of what was heard. Stop (`POST /v1/live/{id}/stop`) ends it and the rig
goes quiet: the protocol's `stop` clears what the Hub has queued. A server runs one
practice at a time, as a rig takes one Hub at a time.

## The native device

The native device prints `http <port>` as its second line, and `--http-port N` chooses
the port. The tests in `tests/test_device_api.py` run against it.
