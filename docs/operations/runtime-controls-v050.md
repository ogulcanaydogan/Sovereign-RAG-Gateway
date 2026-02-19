# Runtime Controls (v0.5 Foundation)

This runbook captures the production-oriented controls added after `v0.4.0`.

## 1) Distributed Token Budgets (Redis Backend)

Set:

```bash
SRG_BUDGET_ENABLED=true
SRG_BUDGET_BACKEND=redis
SRG_BUDGET_REDIS_URL=redis://redis:6379/0
SRG_BUDGET_REDIS_PREFIX=srg:budget
SRG_BUDGET_REDIS_TTL_SECONDS=7200
```

Behavior:
- Budget usage is tracked in Redis sorted sets keyed by tenant.
- Sliding-window checks are enforced before provider egress.
- Backend errors surface as deterministic `503 budget_backend_unavailable`.

## 2) OTLP Trace Export

Set:

```bash
SRG_TRACING_ENABLED=true
SRG_TRACING_OTLP_ENABLED=true
SRG_TRACING_OTLP_ENDPOINT=http://otel-collector:4318/v1/traces
SRG_TRACING_OTLP_TIMEOUT_S=2.0
SRG_TRACING_OTLP_HEADERS='{"Authorization":"Bearer token"}'
SRG_TRACING_SERVICE_NAME=sovereign-rag-gateway
```

Behavior:
- Trace spans remain available via `GET /v1/traces/{request_id}`.
- On completion of `gateway.request`, trace is exported best-effort to OTLP/HTTP.
- Export failures are logged and do not fail request handling.

## 3) Webhook Delivery Hardening

Set:

```bash
SRG_WEBHOOK_ENABLED=true
SRG_WEBHOOK_BACKOFF_BASE_S=0.2
SRG_WEBHOOK_BACKOFF_MAX_S=2.0
SRG_WEBHOOK_MAX_RETRIES=2
SRG_WEBHOOK_DEAD_LETTER_PATH=artifacts/audit/webhook_dead_letter.jsonl
```

Behavior:
- Retryable delivery failures (`429`, `5xx`, transport errors) are retried with exponential backoff.
- Requests include `X-SRG-Idempotency-Key`.
- Failed events are written to dead-letter JSONL for replay.

Replay example:

```bash
python scripts/replay_webhook_dead_letter.py \
  --dead-letter artifacts/audit/webhook_dead_letter.jsonl \
  --event-types policy_denied,budget_exceeded \
  --max-events 50 \
  --report-out artifacts/audit/webhook_replay_report.json
```

## 4) Fault-Injection Benchmark Scenarios

`scripts/benchmark_runner.py` now supports:
- `policy_outage_fail_closed`
- `provider_429_storm`
- `connector_timeout`

New summary metrics:
- `fault_attribution_accuracy`
- `detection_delay_ms_p95`
- `slo_burn_prediction_error_pct`
- `false_positive_incident_rate`

## 5) Benchmark Trend Regression Gate

Compare current governance benchmark output against a checked-in baseline:

```bash
python scripts/check_benchmark_trend.py \
  --current artifacts/benchmarks/governance/results_summary.json \
  --baseline benchmarks/baselines/governance_enforce_redact_summary.json \
  --max-latency-regression-pct 20 \
  --max-leakage-regression-abs 0.002 \
  --max-abs-cost-drift-regression-pct 3 \
  --max-citation-drop-abs 0.1
```

## 6) Kind Runtime Controls Smoke

Run runtime controls (budget, tracing, webhook dead-letter) against local kind:

```bash
deploy/kind/runtime-controls-smoke.sh
```

The smoke script validates:
- request-level tracing availability (`/v1/traces/{request_id}`)
- deterministic `429 budget_exceeded` path
- webhook dead-letter write on delivery failure
