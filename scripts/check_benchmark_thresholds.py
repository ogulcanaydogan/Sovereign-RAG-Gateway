#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def evaluate_thresholds(
    summary: dict[str, object],
    max_leakage_rate: float,
    max_latency_p95_ms: float,
    max_cost_drift_pct: float,
    min_citation_presence_rate: float,
) -> list[str]:
    metrics = summary.get("metrics")
    if not isinstance(metrics, dict):
        return ["results_summary.json missing metrics object"]

    failures: list[str] = []

    def _safe_float(key: str, default: float) -> float:
        raw = metrics.get(key)
        if raw is None or raw == "n/a":
            failures.append(f"{key} is missing or null in metrics (got {raw!r})")
            return default
        try:
            return float(raw)
        except (TypeError, ValueError):
            failures.append(f"{key} is not numeric (got {raw!r})")
            return default

    leakage_rate = _safe_float("leakage_rate", 1.0)
    latency_p95 = _safe_float("latency_ms_p95", 999999.0)
    cost_drift_pct = abs(_safe_float("cost_drift_pct", 999999.0))
    citation_presence = _safe_float("citation_presence_rate", 0.0)

    if leakage_rate > max_leakage_rate:
        failures.append(
            f"leakage_rate {leakage_rate:.6f} exceeds max {max_leakage_rate:.6f}",
        )
    if latency_p95 > max_latency_p95_ms:
        failures.append(
            f"latency_ms_p95 {latency_p95:.2f} exceeds max {max_latency_p95_ms:.2f}",
        )
    if cost_drift_pct > max_cost_drift_pct:
        failures.append(
            f"abs(cost_drift_pct) {cost_drift_pct:.2f} exceeds max {max_cost_drift_pct:.2f}",
        )
    if citation_presence < min_citation_presence_rate:
        failures.append(
            "citation_presence_rate "
            f"{citation_presence:.4f} below min {min_citation_presence_rate:.4f}",
        )
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate benchmark thresholds")
    parser.add_argument(
        "--summary",
        default="artifacts/benchmarks/results_summary.json",
        help="Path to benchmark results_summary.json",
    )
    parser.add_argument("--max-leakage-rate", type=float, default=0.005)
    parser.add_argument("--max-latency-p95-ms", type=float, default=250.0)
    parser.add_argument("--max-cost-drift-pct", type=float, default=5.0)
    parser.add_argument("--min-citation-presence-rate", type=float, default=0.5)
    args = parser.parse_args()

    summary_path = Path(args.summary)
    if not summary_path.exists():
        raise SystemExit(f"summary file does not exist: {summary_path}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    failures = evaluate_thresholds(
        summary=summary,
        max_leakage_rate=args.max_leakage_rate,
        max_latency_p95_ms=args.max_latency_p95_ms,
        max_cost_drift_pct=args.max_cost_drift_pct,
        min_citation_presence_rate=args.min_citation_presence_rate,
    )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        raise SystemExit(1)

    print("Benchmark thresholds passed")


if __name__ == "__main__":
    main()
