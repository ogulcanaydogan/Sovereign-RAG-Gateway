# Sovereign Benchmark Report Template

## Run Metadata
- Run ID:
- Scenario:
- Dataset Version:
- Cluster Profile:
- Commit:
- Image Digest:
- Policy Bundle SHA:

## Experimental Conditions
- Control:
- Treatment(s):
- Sample Size:
- Confidence Level:

## Key Results
- Leakage rate (with CI95):
- Redaction false-positive rate (with CI95):
- Policy deny precision/recall/F1 (with CI95 for F1):
- Citation integrity rate (with CI95):
- Latency overhead p50/p95/p99:
- Cost drift:

## Failure and Drift Checks
- Artifact completeness check:
- Summary vs raw recomputation check:
- Environment drift from baseline:

## Raw Artifacts
- `artifacts/raw/request_metrics.csv`
- `artifacts/raw/policy_eval.csv`
- `artifacts/raw/results_summary.json`
- `artifacts/raw/provenance.json`
- `artifacts/manifest.yaml`

## Notes
- Known limitations:
- Failed scenarios and why:
- Reproduction command:
