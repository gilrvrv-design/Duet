# Native build of the firmware core (no ESP32 needed): unit tests and the contract CLI.
CXX ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Werror
CORE := lib/duet_core/src
SRCS := $(CORE)/duet_protocol.cpp $(CORE)/duet_executor.cpp
INC := -I$(CORE) -Itest/native

.PHONY: test clean
test: build/test_core build/duet_core_cli
	./build/test_core

build/test_core: test/native/test_core.cpp $(SRCS) $(wildcard $(CORE)/*.hpp) test/native/sim_hal.hpp
	@mkdir -p build
	$(CXX) $(CXXFLAGS) $(INC) -o $@ test/native/test_core.cpp $(SRCS)

build/duet_core_cli: test/native/duet_core_cli.cpp $(SRCS) $(wildcard $(CORE)/*.hpp) test/native/sim_hal.hpp
	@mkdir -p build
	$(CXX) $(CXXFLAGS) $(INC) -o $@ test/native/duet_core_cli.cpp $(SRCS)

clean:
	rm -rf build
