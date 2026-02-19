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
  "stats": {
    "sample_size": 0,
    "runs_count": 0,
    "confidence_level": 0.95
  },
  "metrics": {
    "requests_total": 0,
    "errors_total": 0,
    "leakage_rate": 0.0,
    "leakage_rate_ci95_low": 0.0,
    "leakage_rate_ci95_high": 0.0,
    "redaction_false_positive_rate": 0.0,
    "redaction_false_positive_rate_ci95_low": 0.0,
    "redaction_false_positive_rate_ci95_high": 0.0,
    "policy_deny_precision": 0.0,
    "policy_deny_recall": 0.0,
    "policy_deny_f1": 0.0,
    "policy_deny_f1_ci95_low": 0.0,
    "policy_deny_f1_ci95_high": 0.0,
    "citation_integrity_rate": 0.0,
    "citation_integrity_rate_ci95_low": 0.0,
    "citation_integrity_rate_ci95_high": 0.0,
    "latency_ms_p50": 0.0,
    "latency_ms_p95": 0.0,
    "latency_ms_p99": 0.0,
    "cost_drift_pct": 0.0,
    "fault_type": "none",
    "fault_attribution_accuracy": 0.0,
    "detection_delay_ms_p95": 0.0,
    "slo_burn_prediction_error_pct": 0.0,
    "false_positive_incident_rate": 0.0
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
- `policy_reason`
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
- `citation_integrity_pass`
- `fault_type`
- `detection_delay_ms`
- `attribution_correct`
- `slo_burn_prediction_error_pct`
- `incident_false_positive`

## File: `policy_eval.csv`
Columns:
- `case_id`
- `scenario`
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
  "benchmark_manifest_sha256": "string",
  "runner": "github-actions",
  "started_at": "RFC3339",
  "finished_at": "RFC3339"
}
```

## File: `pgvector_ranking_eval.json`
```json
{
  "run_at": "RFC3339",
  "samples_total": 0,
  "top_k": 3,
  "recall_at_k": 0.0,
  "mrr": 0.0,
  "results": [
    {
      "id": "sample-id",
      "query": "string",
      "expected_file_name": "string",
      "hit": true,
      "matched_rank": 1,
      "top_sources": ["file-a.txt", "file-b.txt"]
    }
  ]
}
```

## File: `pgvector-ranking-latest.md`
- Markdown summary produced by `scripts/eval_pgvector_ranking.py`.
- Must include status (`PASS`/`FAIL`), `Recall@k`, and `MRR`.

## Validation Rules
- Summary metrics must be recomputable from raw CSV files.
- CI fields must use the confidence level declared under `stats.confidence_level`.
- Any missing required artifact invalidates the benchmark run.
