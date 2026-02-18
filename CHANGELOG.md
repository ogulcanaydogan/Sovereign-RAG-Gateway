# Changelog

## Unreleased
- Added Helm chart under `charts/sovereign-rag-gateway` with values schema, readiness/liveness probes, service account, optional RBAC, and default network policy.
- Added kind deployment scripts and smoke runbook under `deploy/kind` and `docs/operations/helm-kind-runbook.md`.
- Added `deploy-smoke` GitHub Actions workflow to validate chart installation and endpoint smoke tests on kind.
- Added release workflow with semver tag validation, changelog-backed release notes, GHCR image publish, cosign signing, SBOM generation, and provenance attestation.
- Added `scripts/extract_release_notes.py` and unit coverage for release-note extraction.

## v0.2.0-rc1 - 2026-02-18
- Added `postgres` pgvector connector with connector registry wiring and policy-aware retrieval gating.
- Extended ingestion tooling to support pgvector-backed indexing (`--connector postgres`).
- Added provider-backed embedding generation for ingestion and retrieval (`SRG_RAG_EMBEDDING_SOURCE=http`).
- Added lexical-hash embedding baseline for deterministic local retrieval without external providers.
- Added citation evaluation harness and CI gate enforcing citation presence threshold (`>=0.95`).
- Added pgvector ranking evaluation harness and CI gate enforcing Recall@3 threshold (`>=0.80`).
- Added migration check script and release notes for `v0.2.0-rc1`.
- Added Postgres integration coverage for connector search/fetch and citation-bearing chat responses.
- Updated benchmark/docs artifacts for week-6 RC readiness.

## v0.1.0-alpha.3 - 2026-02-17
- Added connector-based RAG foundation with `app/rag` registry, connector protocol, and retrieval orchestrator.
- Implemented filesystem connector search/fetch with metadata filtering and citation-ready chunk output.
- Added chat request RAG options and citation extension wiring on `POST /v1/chat/completions`.
- Added policy connector constraints to contract/model and enforced retrieval connector deny paths.
- Added ingestion tooling (`scripts/rag_ingest.py`) and synthetic healthcare corpus generator (`scripts/generate_synthetic_healthcare_corpus.py`).
- Added unit/integration coverage for filesystem retrieval, retrieval policy gating, and citation-bearing chat responses.

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
