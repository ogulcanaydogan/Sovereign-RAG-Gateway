# Changelog

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
