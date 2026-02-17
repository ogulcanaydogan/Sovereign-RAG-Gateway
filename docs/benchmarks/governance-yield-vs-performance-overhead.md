# Benchmark Spec: Governance Yield vs Performance Overhead

## Purpose
Measure whether in-path governance materially reduces leakage and policy violations while preserving acceptable latency and cost behavior.

## Hypothesis
Compared with direct provider calls, gateway enforcement (`policy + redaction + constrained routing`) reduces sensitive leakage and unauthorized actions with bounded p95 overhead.

## Experimental Conditions
1. Baseline direct provider (no gateway).
2. Gateway observe mode (decision logged, not enforced).
3. Gateway enforce + redaction.
4. Gateway enforce + redaction + RAG (filesystem + pgvector).

## Datasets
- Synthetic healthcare notes/discharge summaries.
- Adversarial prompt injection set with PHI-like payloads.
- Retrieval authorization corpus with allowed/denied source partitions.

## Workload Profiles
- 10 RPS steady, 25 RPS steady, 50 RPS steady.
- Mixed request classes: chat-only (70%), RAG-enabled (30%).
- Burst profile: 3x traffic for 60 seconds every 10 minutes.

## Primary Metrics
- Leakage rate: fraction of outputs containing unreduced PHI markers.
- Redaction false positive rate: benign tokens incorrectly masked.
- Policy deny precision/recall on labeled authorization set.
- Gateway latency overhead p50/p95/p99 relative to baseline.
- Cost projection drift vs configured budget cap.
- Citation presence and groundedness for RAG requests.

## Success Thresholds (v0.2 Target)
- Leakage rate < 0.5% on synthetic suite.
- Redaction false positives < 8%.
- p95 overhead < 250 ms (no RAG) and < 600 ms (with RAG).
- Cost projection stays within +/-5% of cap under tested scenarios.
- Citation presence >= 95% for RAG-enabled responses.

## Scoring
- Governance Yield Score (GYS) = weighted sum of leakage reduction, policy accuracy, and citation integrity.
- Performance Cost Index (PCI) = weighted latency overhead + cost drift + error-rate delta.
- Publish both raw metrics and aggregated scores; never publish score-only summaries.

## Reproducibility Protocol
- Pin dependency versions and container image digests.
- Record cluster profile (node size, CPU/memory limits, K8s version).
- Commit run manifest + seed value for dataset generation.
- Publish raw CSV/JSON plus markdown summary and dashboard screenshots.

## Deliverables Per Run
- `artifacts/raw/*.csv`
- `artifacts/raw/*.json`
- `artifacts/report.md`
- `artifacts/screenshots/*.png`
- `artifacts/manifest.yaml`

## Known Limitations
- Synthetic PHI patterns do not fully match real-world language ambiguity.
- Provider-side variability can dominate tail latency on low sample counts.
- Regex-centric redaction may underperform ML-assisted approaches on context-heavy entities.
