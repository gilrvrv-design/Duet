# Native build of the firmware core (no ESP32 needed): unit tests and the contract CLI.
CXX ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Werror
CORE := lib/duet_core/src
SRCS := $(addprefix $(CORE)/,duet_protocol.cpp duet_executor.cpp duet_device.cpp duet_api.cpp duet_json.cpp duet_settings.cpp duet_midi.cpp duet_planner.cpp)
INC := -I$(CORE)

.PHONY: test clean qemu-image device instruments
test: build/test_core build/duet_core_cli build/duet_device
	./build/test_core

build/test_core: test/native/test_core.cpp $(SRCS) $(wildcard $(CORE)/*.hpp)
	@mkdir -p build
	$(CXX) $(CXXFLAGS) $(INC) -o $@ test/native/test_core.cpp $(SRCS)

build/duet_core_cli: test/native/duet_core_cli.cpp src/rig.h $(SRCS) $(wildcard $(CORE)/*.hpp)
	@mkdir -p build
	$(CXX) $(CXXFLAGS) $(INC) -Isrc -o $@ test/native/duet_core_cli.cpp $(SRCS)

# A 4 MB flash image of the QEMU build (env:qemu) for Espressif's ESP32 emulator.
PIO ?= pio
ESPTOOL ?= $(HOME)/.platformio/packages/tool-esptool/esptool
BOOT_APP0 ?= $(HOME)/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin
QEMU_BUILD := .pio/build/qemu

qemu-image:
	$(PIO) run -s -e qemu
	@mkdir -p build
	$(ESPTOOL) --chip esp32 merge-bin --pad-to-size 4MB -o build/qemu-flash.bin \
		0x1000 $(QEMU_BUILD)/bootloader.bin 0x8000 $(QEMU_BUILD)/partitions.bin \
		0xe000 $(BOOT_APP0) 0x10000 $(QEMU_BUILD)/firmware.bin

# The firmware as a Linux process, its serial link over TCP (host/duet_device.cpp).
device: build/duet_device

build/duet_device: host/duet_device.cpp host/http_server.hpp build/gen/web_assets.h boards/native/board.h src/rig.h $(SRCS) $(wildcard $(CORE)/*.hpp)
	@mkdir -p build
	$(CXX) $(CXXFLAGS) $(INC) -Iboards/native -Isrc -Ibuild/gen -o $@ host/duet_device.cpp $(SRCS)

# The web app, compiled into the firmware (tools/embed_web.py).
build/gen/web_assets.h: tools/embed_web.py $(wildcard web/*)
	python3 tools/embed_web.py web $@

# The planner's instruments, from the Hub's instrument files, read by the Hub's own
# loader (tools/embed_instruments.py). The header is committed, so building the firmware
# needs no Python packages; run this after changing an instrument file. make check
# fails while the header is out of date (tests/test_planner_contract.py).
INSTRUMENTS := $(CORE)/duet_instrument_data.hpp
instruments:
	../.venv/bin/python tools/embed_instruments.py ../src/duet/profiles $(INSTRUMENTS)

clean:
	rm -rf build
