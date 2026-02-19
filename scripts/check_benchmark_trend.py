#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any


def _metric(metrics: dict[str, object], key: str) -> float:
    value = metrics.get(key)
    if value is None or value == "n/a":
        raise ValueError(f"{key} is missing or null")
    try:
        if isinstance(value, bool):
            raise ValueError(f"{key} is not numeric: {value!r}")
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return float(value)
        raise ValueError(f"{key} is not numeric: {value!r}")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} is not numeric: {value!r}") from exc


def evaluate_trend(
    current_summary: dict[str, object],
    baseline_summary: dict[str, object],
    *,
    max_latency_regression_pct: float,
    max_leakage_regression_abs: float,
    max_abs_cost_drift_regression_pct: float,
    max_citation_drop_abs: float,
) -> list[str]:
    current_metrics = current_summary.get("metrics")
    baseline_metrics = baseline_summary.get("metrics")
    if not isinstance(current_metrics, dict):
        return ["current summary missing metrics object"]
    if not isinstance(baseline_metrics, dict):
        return ["baseline summary missing metrics object"]

    failures: list[str] = []
    try:
        current_latency = _metric(current_metrics, "latency_ms_p95")
        baseline_latency = _metric(baseline_metrics, "latency_ms_p95")
        current_leakage = _metric(current_metrics, "leakage_rate")
        baseline_leakage = _metric(baseline_metrics, "leakage_rate")
        current_abs_cost = abs(_metric(current_metrics, "cost_drift_pct"))
        baseline_abs_cost = abs(_metric(baseline_metrics, "cost_drift_pct"))
        current_citation = _metric(current_metrics, "citation_presence_rate")
        baseline_citation = _metric(baseline_metrics, "citation_presence_rate")
    except ValueError as exc:
        return [str(exc)]

    latency_regression_pct = 0.0
    if baseline_latency > 0:
        latency_regression_pct = ((current_latency - baseline_latency) / baseline_latency) * 100.0

    leakage_regression_abs = current_leakage - baseline_leakage
    abs_cost_regression_pct = current_abs_cost - baseline_abs_cost
    citation_drop_abs = baseline_citation - current_citation

    if latency_regression_pct > max_latency_regression_pct:
        failures.append(
            "latency_ms_p95 regression "
            f"{latency_regression_pct:.2f}% exceeds max {max_latency_regression_pct:.2f}%"
        )
    if leakage_regression_abs > max_leakage_regression_abs:
        failures.append(
            "leakage_rate regression "
            f"{leakage_regression_abs:.6f} exceeds max {max_leakage_regression_abs:.6f}"
        )
    if abs_cost_regression_pct > max_abs_cost_drift_regression_pct:
        failures.append(
            "abs(cost_drift_pct) regression "
            f"{abs_cost_regression_pct:.2f} exceeds max {max_abs_cost_drift_regression_pct:.2f}"
        )
    if citation_drop_abs > max_citation_drop_abs:
        failures.append(
            "citation_presence_rate drop "
            f"{citation_drop_abs:.4f} exceeds max {max_citation_drop_abs:.4f}"
        )

    return failures


def _load_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"summary file does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"summary must be a JSON object: {path}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Check benchmark trend against baseline")
    parser.add_argument(
        "--current",
        default="artifacts/benchmarks/governance/results_summary.json",
        help="Current benchmark summary path",
    )
    parser.add_argument(
        "--baseline",
        default="benchmarks/baselines/governance_enforce_redact_summary.json",
        help="Baseline benchmark summary path",
    )
    parser.add_argument("--max-latency-regression-pct", type=float, default=20.0)
    parser.add_argument("--max-leakage-regression-abs", type=float, default=0.002)
    parser.add_argument("--max-abs-cost-drift-regression-pct", type=float, default=3.0)
    parser.add_argument("--max-citation-drop-abs", type=float, default=0.1)
    args = parser.parse_args()

    current_summary = _load_summary(Path(args.current))
    baseline_summary = _load_summary(Path(args.baseline))

    failures = evaluate_trend(
        current_summary=current_summary,
        baseline_summary=baseline_summary,
        max_latency_regression_pct=args.max_latency_regression_pct,
        max_leakage_regression_abs=args.max_leakage_regression_abs,
        max_abs_cost_drift_regression_pct=args.max_abs_cost_drift_regression_pct,
        max_citation_drop_abs=args.max_citation_drop_abs,
    )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        raise SystemExit(1)

    print("Benchmark trend checks passed")


if __name__ == "__main__":
    main()
