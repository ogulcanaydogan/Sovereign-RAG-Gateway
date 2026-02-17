# Benchmark Spec: Governance Yield vs Performance Overhead

## Purpose
Quantify the tradeoff between governance effectiveness and runtime overhead for policy-first LLM/RAG request handling.

## Hypothesis
Compared with direct provider calls, in-path governance (`policy + redaction + policy-scoped retrieval`) reduces leakage and unauthorized actions with bounded latency/cost impact.

## Comparison Conditions
1. Baseline: direct provider calls (no gateway).
2. Observe mode: gateway decisions logged, not enforced.
3. Enforce mode: policy + redaction.
4. Enforce + RAG mode: policy + redaction + connector-scoped retrieval/citations.

## Datasets and Workloads
### Datasets
- Synthetic healthcare-style corpus containing labeled PHI-like entities.
- Adversarial prompt-injection cases targeting retrieval policy bypass.
- Retrieval authorization set with labeled allow/deny source partitions.

### Load profiles
- 10, 25, 50 RPS steady-state.
- Traffic mix: 70% chat-only, 30% RAG-enabled.
- Burst profile: 3x load for 60s every 10 minutes.

## Primary Metrics
- Leakage rate (output contains unreduced sensitive markers).
- Redaction false-positive rate.
- Policy deny precision/recall/F1 on labeled authorization cases.
- Citation integrity rate (citations reference only allowed sources).
- Latency overhead deltas p50/p95/p99 versus baseline.
- Cost drift versus configured budget cap.

## Success Thresholds (Initial v0.2 Target)
- Leakage rate < 0.5% on synthetic suite.
- Redaction false-positive rate < 8%.
- Policy deny F1 >= 0.90.
- Citation integrity >= 99% on labeled RAG cases.
- p95 latency overhead < 250 ms (chat-only), < 600 ms (RAG).
- Cost drift within +/-5% of configured cap.

## Statistical Reporting Requirements
- Report 95% confidence intervals for leakage rate, policy precision/recall/F1, and citation integrity.
- Report run count and sample size per scenario.
- Publish both aggregate and per-scenario distributions; avoid score-only rollups.

## Reproducibility Protocol
- Pin dependency versions and container image digests.
- Record cluster profile (`k8s version`, node type/count, CPU/memory limits).
- Store dataset seed and benchmark manifest for each run.
- Publish raw outputs and report-generation scripts.

## Required Artifacts Per Run
- `artifacts/raw/request_metrics.csv`
- `artifacts/raw/policy_eval.csv`
- `artifacts/raw/results_summary.json`
- `artifacts/raw/provenance.json`
- `artifacts/report.md`
- `artifacts/manifest.yaml`

## Failure Criteria (When to Reject a Run)
- Missing raw artifacts or provenance manifest.
- Incomplete scenario coverage for declared workload matrix.
- Mismatch between published summary metrics and recomputed raw metrics.
- Unreported benchmark environment drift from prior baseline profile.

## Known Limitations
- Synthetic data does not capture full linguistic ambiguity in production PHI.
- Provider-side variability can dominate tail latency at low sample sizes.
- Regex-centric redaction is weaker on context-dependent entity detection.
