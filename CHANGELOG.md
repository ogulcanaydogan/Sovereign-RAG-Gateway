# Changelog

## Unreleased

## v1.0.0 - 2026-03-07

### GA Hardening Completion
- Promoted hardening-only line to GA without introducing breaking HTTP/API changes.
- Finalized runtime governance baseline for GA:
  - policy-first fail-closed controls
  - tenant-aware budget enforcement
  - PHI/PII redaction with audit accounting
  - webhook durability and replay path
  - request traceability and signed evidence bundles
- Finalized release-integrity baseline for GA:
  - latest strict release verification
  - latest-10 historical integrity sweep
  - release evidence contract drift checks
  - GA same-commit `release-verify` enforcement for `vX.Y.Z` tags

### Operations and Evidence
- Kept weekly evidence report generation and verification snapshot outputs as GA operating baseline.
- Kept rollback drill workflow and operator runbook as GA readiness controls.

### Version Alignment
- Updated project/app/chart/Terraform defaults to `1.0.0` / `v1.0.0`.
- Added GA release dossier at `docs/releases/v1.0.0.md`.

## v0.9.0-rc1 - 2026-03-07

### RC Stabilization Cut
- Promoted beta baseline to release candidate for GA hardening with no API contract expansion.
- Confirmed stabilization-window prerequisites in the last 7 days:
  - `deploy-smoke >= 3` successful runs
  - `release-verify >= 2` successful runs
  - `ci >= 1` successful runs
  - `terraform-validate >= 1` successful runs
- Confirmed benchmark trend gate pass using `scripts/check_benchmark_trend.py`.

### Release and Evidence Integrity
- Kept strict release verification path for both latest and latest-10 historical sweep.
- Kept release evidence contract drift checks as a required scheduled guardrail.
- Kept rollback drill workflow and weekly evidence snapshot generation as RC operational baseline.

### Version Alignment
- Updated project/app/chart/Terraform defaults to `0.9.0-rc1` / `v0.9.0-rc1`.
- Added RC dossier at `docs/releases/v0.9.0-rc1.md`.

## v0.8.0-beta.1 - 2026-03-07

### Beta Cut (Hardening-Only Track)
- Promoted the v0.8 operational hardening line from alpha to beta without adding new HTTP surface area.
- Kept runtime-governance behavior stable across policy fail-closed mode, budget controls, webhook durability, tracing, and release-integrity checks.
- Locked beta release posture around existing required workflows:
  - `ci`
  - `deploy-smoke`
  - `terraform-validate`
  - `ga-readiness`
  - `release-verify`
  - `evidence-replay-smoke`

### Release Integrity and Evidence Gates
- Retained strict release verification in CI:
  - latest release integrity/signature/public-key verification
  - historical sweep over latest 10 releases
  - release-evidence contract drift checks
- Retained weekly evidence snapshot generation and rollback drill automation as beta baseline controls.

### Version Alignment
- Updated project/app/chart/Terraform defaults to `0.8.0-beta.1` / `v0.8.0-beta.1`.
- Added prerelease dossier at `docs/releases/v0.8.0-beta.1.md`.

## v0.8.0-alpha.1 - 2026-03-06

### Operations Closeout (v0.8.0-alpha.1 backlog 5/5)
- Added automated stabilization-window evidence checker with JSON output and CI artifact upload.
- Added GA gate integration-like unit scenarios covering prerelease bypass and GA same-commit failure/success behavior.
- Added release-evidence contract drift checker for scheduled verification (asset presence + digest/signature + metadata consistency).
- Added weekly release verification snapshot generation (`PNG + JSON`) and wired outputs into weekly evidence pipeline.
- Added one-command rollback drill (`v0.7.0 -> v0.6.0`) script, dedicated workflow, and operator runbook.

### Workflow and Evidence Pipeline
- Extended `ga-readiness` workflow to publish stabilization-window artifacts.
- Extended `release-verify` workflow to run release-evidence contract sweep and upload report artifact.
- Extended `weekly-evidence-report` workflow to generate and commit release verification snapshot assets.
- Added dedicated `rollback-drill` workflow (dispatch + weekly schedule) with diagnostics artifact upload on failure.

### Version Alignment
- Updated project/app/chart/Terraform defaults to `0.8.0-alpha.1` / `v0.8.0-alpha.1`.
- Added prerelease dossier at `docs/releases/v0.8.0-alpha.1.md`.

## v0.7.0 - 2026-03-03

### GA Promotion
- Promoted v0.7 hardening line to GA with no HTTP/API contract breakages.
- Confirmed GA release artifact set includes signed evidence bundle and public verification key.

### Release Integrity and Gates
- Retained strict latest + latest10 release verification in `release-verify`.
- Retained prerelease metadata parity enforcement in release verification path.
- Retained same-commit `release-verify` requirement for GA tags in `release` workflow.
- Added GA readiness workflow to continuously validate required workflow inventory and release sweep output.

### Version Alignment
- Updated project/app/chart/Terraform defaults to `0.7.0` / `v0.7.0`.
- Added stable release dossier at `docs/releases/v0.7.0.md`.

## v0.7.0-rc1 - 2026-03-03

### GA Readiness Guardrails
- Added `ga-readiness` workflow to validate release posture on PR/push/manual runs.
- Added `scripts/check_required_workflows.py` to enforce required workflow inventory:
  - `ci`
  - `deploy-smoke`
  - `terraform-validate`
  - `evidence-replay-smoke`
  - `release-verify`
- Added unit coverage for required workflow checks (`tests/unit/test_check_required_workflows.py`).

### Release Integrity
- Kept historical strict sweep checks (`latest-count=10`) and prerelease parity enforcement in verification path.
- Kept GA publish gate requirement: same-commit `release-verify` success for `vX.Y.Z` tags.

### Version Alignment
- Updated project/app/chart/Terraform defaults to `0.7.0-rc1` / `v0.7.0-rc1`.
- Added release dossier at `docs/releases/v0.7.0-rc1.md`.

## v0.7.0-alpha.2 - 2026-03-03

### CI Stabilization
- Replaced `helm/kind-action@v1` in deploy smoke workflow with repository-managed kind installation logic using checksum validation and retry backoff.
- Added `deploy/kind/install-kind.sh` to install kind deterministically with checksum verification.

### Release Integrity Hardening
- Extended `scripts/check_release_assets.py` with:
  - `--latest-count` historical verification support
  - `--json-report` summary output
  - `--enforce-prerelease-flag-parity` metadata drift enforcement
- Updated `release-verify` workflow to run strict latest checks plus latest-10 historical sweep and upload sweep artifact.
- Added `scripts/check_ga_release_gate.py` to enforce same-commit `release-verify` success for GA tags.
- Updated `.github/workflows/release.yml` to run GA gate checks before publish and to derive prerelease flag from tag semantics.

### Operations Documentation
- Added offline operator guide for SHA/signature evidence verification:
  - `docs/operations/offline-evidence-signature-verification.md`

### Runtime Foundation Continuity
- Kept `v0.7.0-alpha.1` runtime-controls baseline unchanged (response redaction, token budgets, tracing, webhook durability).
- Kept SharePoint connector support and managed-identity retrieval path unchanged while hardening CI/release integrity.

### Version Alignment
- Updated project/app/chart/Terraform defaults to `0.7.0-alpha.2` / `v0.7.0-alpha.2`.
- Added prerelease dossier at `docs/releases/v0.7.0-alpha.2.md`.

## v0.7.0-alpha.1 - 2026-03-03

### Release Evidence Verification Hardening
- Extended `scripts/check_release_assets.py` with optional cryptographic checks:
  - download/verify `bundle.sha256` against `bundle.json`
  - optional detached signature verification with release public key asset
- Updated `release-verify` workflow to enforce both bundle SHA-256 and detached signature verification on the latest release.
- Updated release evidence generation to publish `release-evidence-public.pem` inside release evidence artifacts for external signature verification.
- Added unit coverage for signature verification success and tampered-bundle failure cases.

### Version Alignment
- Updated project/app/chart/Terraform defaults to `0.7.0-alpha.1` / `v0.7.0-alpha.1`.
- Added prerelease dossier at `docs/releases/v0.7.0-alpha.1.md`.
- Published weekly evidence report with runtime-controls smoke + release + strict release-verify links at `docs/benchmarks/reports/weekly-2026-03-03.md`.

## v0.6.0 - 2026-02-20

### GA Promotion
- Promoted all `v0.6.0-alpha.1` capabilities to GA with no contract-breaking API changes.
- Confirmed `v0.6.0` compatibility for runtime policy enforcement, redaction, provider parity gating, webhook durability, and evidence automation flows.

### Release and Operations
- Added stable release notes at `docs/releases/v0.6.0.md`.
- Updated project, app, chart, and Terraform defaults to `0.6.0` / `v0.6.0`.
- Kept `v0.6.0-alpha.1` notes for prerelease traceability and migration history.
- Added `release-verify` scheduled workflow and `scripts/check_release_assets.py` to validate that latest releases retain required evidence/SBOM assets.

## v0.6.0-alpha.1 - 2026-02-20

### Provider and Runtime Operations Hardening
- Promoted provider parity checks as a CI release gate with persisted matrix artifacts for `http_openai`, `azure_openai`, and `anthropic`.
- Hardened webhook dead-letter durability defaults around `sqlite` backend, retention pruning, and replay compatibility.
- Added webhook replay/retention dashboard coverage with new Grafana panels for delivery attempts, dead-letter rates, and pruning trends.

### Evidence Automation
- Added scheduled weekly evidence report workflow plus manual dispatch support.
- Added auto-maintained weekly reports index generation from benchmark/evidence report artifacts.
- Updated workflow behavior so report generation succeeds even when repository policy blocks GitHub Actions from opening pull requests.

### Enterprise Connector Expansion
- Added SharePoint managed-identity authentication mode (Azure IMDS token acquisition) as an alternative to static bearer tokens.
- Added configuration flags for managed-identity endpoint, resource, API version, optional client ID, and timeout.
- Added unit and integration coverage for managed-identity path and bearer-mode validation behavior.

### Release and Migration Assets
- Added `docs/releases/v0.6.0-alpha.1.md` dossier with explicit migration notes from `v0.5.x`.
- Updated Helm and Terraform default release/image versions to `0.6.0-alpha.1` / `v0.6.0-alpha.1`.

## v0.5.0 - 2026-02-20

### Streaming Budget Enforcement
- Added mid-stream budget enforcement with `check_running()` method on both in-memory and Redis budget trackers.
- Streaming requests now check running token usage every N chunks and terminate gracefully with `finish_reason: "length"` if the tenant ceiling is exceeded.
- Added `budget_mid_stream_terminated` audit field to distinguish mid-stream budget cuts from pre-request denials.
- Redis `check_running()` returns `False` (fail-closed) when the backend is unavailable.

### Resilience and Chaos Testing
- Added comprehensive resilience test suite (`tests/integration/test_resilience.py`) covering 8 failure scenarios:
  - provider error mid-stream (audit still written)
  - budget backend unavailable (fail-closed 503)
  - all providers exhausted in fallback chain
  - OPA timeout in enforce mode (fail-closed 503)
  - sequential budget exhaustion (accounting correctness)
  - webhook endpoint unreachable (non-blocking, request succeeds)
  - audit write failure non-streaming (502)
  - audit write failure streaming (graceful, no crash)
- Added `error-timeout-stream` stub model for streaming timeout simulation.

### Version Sync
- Bumped all version references to 0.5.0 across pyproject.toml, app/main.py, Chart.yaml, Terraform variables, and webhook dispatcher.

## v0.5.0-alpha.1 - 2026-02-19

### Enterprise Retrieval
- Added SharePoint read-only connector via Microsoft Graph (`search` + `fetch`) with:
  - optional drive scoping
  - allowed path prefix controls
  - lexical ranking and top-k retrieval
- Wired connector registration and settings for:
  - `SRG_RAG_SHAREPOINT_*`

### Runtime Operations
- Added webhook dead-letter replay CLI:
  - `scripts/replay_webhook_dead_letter.py`
  - supports event filters, endpoint override, deterministic idempotency key derivation, dry-run mode, and JSON reports

### Benchmarks and CI
- Added benchmark trend regression gate:
  - `scripts/check_benchmark_trend.py`
  - checked-in governance baseline under `benchmarks/baselines/`
- CI now includes:
  - Redis service for runtime-control integration coverage
  - webhook dead-letter replay smoke step
  - governance trend regression check

### Tests
- Added unit tests:
  - `tests/unit/test_sharepoint_connector.py`
  - `tests/unit/test_replay_webhook_dead_letter.py`
  - `tests/benchmarks/test_benchmark_trend.py`
- Added integration tests:
  - `tests/integration/test_runtime_controls_v050.py` (Redis budget backend + live OTLP HTTP export)
  - `tests/integration/test_chat_rag_sharepoint.py`

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
