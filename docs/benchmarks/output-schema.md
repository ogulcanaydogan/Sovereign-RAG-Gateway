# Benchmark Output Schemas

## File: `results_summary.json`
```json
{
  "run_id": "2026-02-17T20-00-00Z",
  "project": "sovereign-rag-gateway",
  "scenario": "enforce_redact_rag",
  "dataset_version": "v1",
  "cluster_profile": {
    "kubernetes_version": "1.31",
    "node_type": "kind-default",
    "node_count": 3
  },
  "metrics": {
    "requests_total": 0,
    "errors_total": 0,
    "leakage_rate": 0.0,
    "redaction_false_positive_rate": 0.0,
    "policy_deny_precision": 0.0,
    "policy_deny_recall": 0.0,
    "latency_ms_p50": 0.0,
    "latency_ms_p95": 0.0,
    "latency_ms_p99": 0.0,
    "cost_drift_pct": 0.0,
    "citation_presence_rate": 0.0,
    "groundedness_score": 0.0
  }
}
```

## File: `request_metrics.csv`
Columns:
- `timestamp`
- `request_id`
- `tenant_id`
- `scenario`
- `classification`
- `is_rag`
- `policy_decision`
- `redaction_count`
- `provider`
- `model`
- `status_code`
- `latency_ms`
- `tokens_in`
- `tokens_out`
- `cost_usd`
- `leakage_detected`
- `has_citations`

## File: `policy_eval.csv`
Columns:
- `case_id`
- `expected_decision`
- `actual_decision`
- `deny_reason`
- `is_true_positive`
- `is_false_positive`
- `is_true_negative`
- `is_false_negative`

## File: `provenance.json`
```json
{
  "git_commit": "string",
  "image_digest": "string",
  "opa_policy_bundle_sha256": "string",
  "dataset_seed": 0,
  "runner": "github-actions",
  "started_at": "RFC3339",
  "finished_at": "RFC3339"
}
```
