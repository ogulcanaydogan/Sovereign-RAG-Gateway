.PHONY: dev test lint typecheck schema helm-lint helm-template kind-up kind-down demo-up

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

helm-lint:
	helm lint charts/sovereign-rag-gateway

helm-template:
	helm template srg charts/sovereign-rag-gateway >/tmp/srg-helm-template.yaml

kind-up:
	./deploy/kind/kind-up.sh

kind-down:
	./deploy/kind/kind-down.sh

demo-up:
	./deploy/kind/smoke.sh
