.PHONY: run test build

run:
	uv run python main.py

test:
	uv run pytest --cov=. --cov-report=term-missing

build:
	uv sync