# Changelog

## v0.4.0 - 2026-02-19

### Runtime Governance Controls
- Added response redaction in chat and streaming paths with separate `input_redaction_count` and `output_redaction_count` tracking.
- Added per-tenant sliding-window budget enforcement in request path with deterministic `429 budget_exceeded` responses.
- Added budget-aware audit fields and deny-path audit emission for over-budget requests.
- Added non-blocking webhook event dispatch hooks for policy deny, budget exceed, provider fallback/error, and redaction hits.
- Added in-memory trace collection wiring across request lifecycle spans:
  - `gateway.request`
  - `policy.evaluate`
  - `redaction.scan`
  - `rag.retrieve`
  - `provider.call`
  - `audit.persist`

### API and Contract Updates
- Added trace diagnostics endpoint: `GET /v1/traces/{request_id}`.
- Extended audit event schema with optional runtime observability/governance fields:
  - `trace_id`
  - `budget`
  - `webhook_events`
  - `input_redaction_count`
  - `output_redaction_count`

### Testing
- Added new unit tests:
  - `test_budget_tracker.py`
  - `test_webhook_dispatcher.py`
  - `test_span_collector.py`
- Added integration runtime controls coverage:
  - budget deny and usage accounting
  - response redaction verification
  - webhook trigger smoke
  - trace endpoint span chain checks

### Infrastructure and CI
- Added Terraform module documentation at `deploy/terraform/README.md`.
- Added `terraform-validate` GitHub Actions workflow (`terraform fmt -check`, `terraform validate`).
- Synced version defaults across app/chart/terraform release variables to `0.4.0`.

## v0.3.0 - 2026-02-18

### Streaming and Provider Adapters
- Added OpenAI-compatible SSE streaming for chat completions with `stream: true` parameter.
- Added Azure OpenAI provider adapter with deployment-scoped endpoints and model normalization (`app/providers/azure_openai.py`).
- Added Anthropic Messages API adapter with OpenAI-shape response normalization (`app/providers/anthropic.py`).
- Added capability-aware provider routing via `eligible_chain()` and `ProviderCapabilities` dataclass.
- Added `route_stream_with_fallback()` for streaming-aware provider selection with first-chunk validation.

### RAG Connectors
- Added S3 connector for JSONL index retrieval with local caching and prefix-based multi-object loading (`app/rag/connectors/s3.py`).
- Added Confluence read-only connector with space filtering, pagination, and BM25 scoring (`app/rag/connectors/confluence.py`).
- Added Jira read-only connector with project key filtering, pagination, and BM25 scoring (`app/rag/connectors/jira.py`).

### Evidence and Compliance
- Added evidence replay bundle generator with SHA-256 chain verification and tamper detection (`scripts/audit_replay_bundle.py`).
- Added signed evidence bundle output with detached RSA signatures (`scripts/generate_release_evidence_artifacts.py`).
- Added evidence bundle JSON Schema contract (`docs/contracts/v1/evidence-bundle.schema.json`).
- Added threat model document with threat matrix, controls, and residual risk (`docs/architecture/threat-model.md`).
- Added compliance control-to-evidence mapping (`docs/operations/compliance-control-mapping.md`).
- Added incident replay runbook with signed evidence procedure (`docs/operations/incident-replay-runbook.md`).

### Operations and Deployment
- Added EKS reference deployment guide with validated resource manifests (`docs/operations/eks-reference-deployment.md`).
- Added Confluence connector setup guide (`docs/operations/confluence-connector.md`).
- Added Jira connector setup guide (`docs/operations/jira-connector.md`).
- Added EKS reference validation CI workflow (`.github/workflows/eks-reference-validate.yml`).
- Added evidence replay smoke CI workflow (`.github/workflows/evidence-replay-smoke.yml`).

### Previous (v0.3.0-rc1)
- Added multi-provider routing with cost-aware fallback via `ProviderRegistry` (`app/providers/registry.py`).
- Added `HTTPOpenAIProvider` for real OpenAI-compatible upstream endpoints (`app/providers/http_openai.py`).
- Added Prometheus metrics module with 6 counters and 1 histogram, exposed at `/metrics` (`app/metrics.py`).
- Added Grafana dashboard ConfigMap with 10 panels across request, policy, cost, and data protection domains.
- Added Prometheus scrape config for gateway `/metrics` endpoint.
- Added External Secrets Operator manifests for AWS Secrets Manager integration (`deploy/secrets/`).
- Added secrets rotation runbook with standard rotation, emergency revocation, and sync monitoring (`docs/operations/secrets-rotation-runbook.md`).
- Added Argo CD AppProject, Application, and ApplicationSet for multi-environment GitOps promotion (`deploy/gitops/`).
- Added environment overlay values for dev, staging, and prod (`deploy/gitops/envs/`).
- Updated Helm chart with Prometheus pod annotations, metrics and fallback settings, bumped appVersion to 0.3.0-rc1.
- Updated audit event schema with `provider_attempts` and `fallback_chain` fields.
- Integrated provider registry and metrics recording into `ChatService` for both chat and embeddings endpoints.

## v0.2.0 - 2026-02-18
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
