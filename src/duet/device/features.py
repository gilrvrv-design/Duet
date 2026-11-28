"""What a board can do beyond the core, as it reports in ``hello``.

The firmware's list is ``firmware/lib/duet_core/src/duet_features.hpp``; the contract
test keeps the two in step. Every board has the core: the executor and its safety rules,
the serial link, and songs (in RAM when the board has no flash storage).
"""

WIFI = "wifi"  # the WebSocket link over Wi-Fi
FLASH = "flash"  # stored songs survive power-off
PLAY_BUTTON = "play_button"  # a button that plays stored songs without the Hub
ESTOP_BUTTON = "estop_button"  # a hardware emergency stop
WEB = "web"  # the web app and the device API over HTTP (docs/device-api.md)
PLANNER = "planner"  # the optional planner module: MIDI files planned on the device

KNOWN = (WIFI, FLASH, PLAY_BUTTON, ESTOP_BUTTON, WEB, PLANNER)
