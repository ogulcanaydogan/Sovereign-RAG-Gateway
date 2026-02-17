# Changelog

## v0.1.0-alpha.2 - 2026-02-17
- Added `GET /v1/models` endpoint and OpenAI SDK compatibility coverage for model listing.
- Added policy observe-mode handling so deny/timeout can be audited as `observe` without blocking requests.
- Added optional remote OPA evaluation path with schema-safe fallback behavior.
- Expanded benchmark runner with scenario matrix (`direct_provider`, `observe_mode`, `enforce_redact`) and JSONL dataset input.
- Added integration tests for models endpoint and observe-mode policy flow.

## v0.1.0-alpha.1 - 2026-02-17
- Initialized FastAPI gateway repository with CI, linting, type-checking, and tests.
- Added `/healthz`, `/readyz`, `/v1/chat/completions`, and `/v1/embeddings` endpoints.
- Added auth middleware, request-id propagation, deterministic error envelope, and JSON logging.
- Added policy client with fail-closed behavior and transform pipeline.
- Added PHI/PII regex redaction engine and audit writer with schema validation.
- Added provider stub with chat + embeddings and provider error normalization mapping.
- Added benchmark skeleton runner and report template.
- Added Dockerfile, docker-compose stack (gateway + OPA + Postgres), and compose smoke script.
- Added OpenAI SDK compatibility integration tests for chat and embeddings.
