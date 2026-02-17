.PHONY: dev test lint typecheck schema

dev:
	uv sync --extra dev
	uv run uvicorn app.main:app --reload

test:
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run mypy app scripts

schema:
	uv run python scripts/validate_schemas.py
