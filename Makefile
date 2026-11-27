.PHONY: install check test lint format serve firmware

install:  # exactly the versions in uv.lock; run `uv lock` after changing dependencies
	uv sync -q --frozen --extra dev --extra llm --extra audio --extra api

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
