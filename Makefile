.PHONY: install check test lint format serve firmware

install:
	uv venv -q .venv
	uv pip install -q -e ".[dev,llm,audio,api]"

lint:
	ruff check src tests tools
	ruff format --check src tests tools

format:
	ruff check --fix src tests tools
	ruff format src tests tools

test:
	pytest

check: lint test firmware

firmware:
	$(MAKE) -s -C firmware test

serve:
	DUET_EXAMPLES=examples uvicorn --factory duet.api:create_app --reload
