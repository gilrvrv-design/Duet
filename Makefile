.PHONY: install check test lint format serve firmware qemu-test

install:  # exactly the versions in uv.lock; run `uv lock` after changing dependencies
	uv sync -q --frozen --extra dev --extra llm --extra audio --extra api

lint:
	ruff check src tests tools firmware/tools
	ruff format --check src tests tools firmware/tools

format:
	ruff check --fix src tests tools firmware/tools
	ruff format src tests tools firmware/tools

test:
	pytest

check: lint test firmware

firmware:
	$(MAKE) -s -C firmware test

# HOST=0.0.0.0 lets rigs and phones on the network reach the server.
HOST ?= 127.0.0.1
serve:
	DUET_EXAMPLES=examples uvicorn --factory duet.api:create_app --reload --host $(HOST)

# The full loop on the compiled ESP32 image in QEMU too (firmware/QEMU.md).
qemu-test:
	$(MAKE) -s -C firmware qemu-image
	pytest -q tests/test_firmware_loop.py -rs
