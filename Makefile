.PHONY: install check test lint format

install:
	uv venv -q .venv
	uv pip install -q -e ".[dev,llm,audio]"

lint:
	ruff check src tests
	ruff format --check src tests

format:
	ruff check --fix src tests
	ruff format src tests

test:
	pytest

check: lint test
