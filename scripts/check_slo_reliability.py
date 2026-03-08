#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate reliability/SLO gate artifacts")
    parser.add_argument(
        "--benchmark-summary",
        default="artifacts/benchmarks/governance/results_summary.json",
        help="Benchmark results_summary.json path",
    )
    parser.add_argument(
        "--fault-summary",
        default="artifacts/fault-injection/fault-summary.json",
        help="Fault injection summary path",
    )
    parser.add_argument(
        "--soak-summary",
        default="artifacts/soak/soak-summary.json",
        help="Soak summary path",
    )
    parser.add_argument(
        "--baseline-summary",
        default="benchmarks/baselines/governance_enforce_redact_summary.json",
        help="Baseline results_summary.json path for p95 regression",
    )
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--max-p95-regression-pct", type=float, default=10.0)
    parser.add_argument("--max-nominal-shed-rate", type=float, default=0.02)
    parser.add_argument("--json-report", default="")
    return parser.parse_args()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"{label} file does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} is not valid JSON: {path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} must be a JSON object: {path}")
    return payload


def _safe_float(value: object, *, field_name: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip() != "":
        try:
            return float(value.strip())
        except ValueError as exc:
            raise SystemExit(f"{field_name} must be numeric (got {value!r})") from exc
    raise SystemExit(f"{field_name} is missing or non-numeric")


def _metric(payload: dict[str, Any], *keys: str, field_name: str) -> float:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            raise SystemExit(f"{field_name} missing path component: {key}")
        current = current.get(key)
    return _safe_float(current, field_name=field_name)


def _error_rate_from_summary(payload: dict[str, Any], *, label: str) -> float:
    requests_total = _metric(
        payload,
        "metrics",
        "requests_total",
        field_name=f"{label}.metrics.requests_total",
    )
    errors_total = _metric(
        payload,
        "metrics",
        "errors_total",
        field_name=f"{label}.metrics.errors_total",
    )
    if requests_total <= 0:
        raise SystemExit(f"{label}.metrics.requests_total must be > 0")
    return max(min(errors_total / requests_total, 1.0), 0.0)


def evaluate_slo_reliability(
    *,
    benchmark_summary: dict[str, Any],
    fault_summary: dict[str, Any],
    soak_summary: dict[str, Any],
    baseline_summary: dict[str, Any],
    max_error_rate: float,
    max_p95_regression_pct: float,
    max_nominal_shed_rate: float,
) -> dict[str, Any]:
    benchmark_error_rate = _error_rate_from_summary(benchmark_summary, label="benchmark")
    soak_error_rate = _error_rate_from_summary(soak_summary, label="soak")

    fault_error_rate = _metric(
        fault_summary,
        "totals",
        "error_rate",
        field_name="fault.totals.error_rate",
    )
    fault_failed_scenarios = _metric(
        fault_summary,
        "totals",
        "failed_scenarios",
        field_name="fault.totals.failed_scenarios",
    )

    baseline_p95 = _metric(
        baseline_summary,
        "metrics",
        "latency_ms_p95",
        field_name="baseline.metrics.latency_ms_p95",
    )
    if baseline_p95 <= 0:
        raise SystemExit("baseline.metrics.latency_ms_p95 must be > 0")

    soak_p95 = _metric(
        soak_summary,
        "metrics",
        "latency_ms_p95",
        field_name="soak.metrics.latency_ms_p95",
    )
    p95_regression_pct = ((soak_p95 - baseline_p95) / baseline_p95) * 100.0

    nominal_shed_rate = _metric(
        soak_summary,
        "metrics",
        "shed_rate",
        field_name="soak.metrics.shed_rate",
    )

    observed_error_rate = max(benchmark_error_rate, soak_error_rate)

    checks = {
        "error_rate": observed_error_rate <= max_error_rate,
        "p95_regression_vs_baseline": p95_regression_pct <= max_p95_regression_pct,
        "nominal_shed_rate": nominal_shed_rate <= max_nominal_shed_rate,
        "fault_suite_scenarios": fault_failed_scenarios == 0.0,
    }
    overall_pass = all(checks.values())

    missing_requirements: list[dict[str, object]] = []
    if not checks["error_rate"]:
        missing_requirements.append(
            {
                "name": "error_rate",
                "observed": round(observed_error_rate, 6),
                "threshold": max_error_rate,
            }
        )
    if not checks["p95_regression_vs_baseline"]:
        missing_requirements.append(
            {
                "name": "p95_regression_vs_baseline",
                "observed": round(p95_regression_pct, 4),
                "threshold": max_p95_regression_pct,
            }
        )
    if not checks["nominal_shed_rate"]:
        missing_requirements.append(
            {
                "name": "nominal_shed_rate",
                "observed": round(nominal_shed_rate, 6),
                "threshold": max_nominal_shed_rate,
            }
        )
    if not checks["fault_suite_scenarios"]:
        missing_requirements.append(
            {
                "name": "fault_suite_scenarios",
                "observed": int(fault_failed_scenarios),
                "threshold": 0,
            }
        )

    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "overall_pass": overall_pass,
        "thresholds": {
            "max_error_rate": max_error_rate,
            "max_p95_regression_pct": max_p95_regression_pct,
            "max_nominal_shed_rate": max_nominal_shed_rate,
        },
        "observed": {
            "error_rate": round(observed_error_rate, 6),
            "benchmark_error_rate": round(benchmark_error_rate, 6),
            "soak_error_rate": round(soak_error_rate, 6),
            "fault_error_rate": round(fault_error_rate, 6),
            "soak_p95_latency_ms": round(soak_p95, 4),
            "baseline_p95_latency_ms": round(baseline_p95, 4),
            "p95_regression_vs_baseline_pct": round(p95_regression_pct, 4),
            "nominal_shed_rate": round(nominal_shed_rate, 6),
            "fault_failed_scenarios": int(fault_failed_scenarios),
        },
        "checks": checks,
        "missing_requirements": missing_requirements,
    }


def main() -> None:
    args = _parse_args()

    benchmark_summary = _load_json(Path(args.benchmark_summary), "benchmark summary")
    fault_summary = _load_json(Path(args.fault_summary), "fault summary")
    soak_summary = _load_json(Path(args.soak_summary), "soak summary")
    baseline_summary = _load_json(Path(args.baseline_summary), "baseline summary")

    result = evaluate_slo_reliability(
        benchmark_summary=benchmark_summary,
        fault_summary=fault_summary,
        soak_summary=soak_summary,
        baseline_summary=baseline_summary,
        max_error_rate=args.max_error_rate,
        max_p95_regression_pct=args.max_p95_regression_pct,
        max_nominal_shed_rate=args.max_nominal_shed_rate,
    )

    if args.json_report.strip():
        report_path = Path(args.json_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"JSON report written: {report_path}")

    print(
        "SLO reliability gate:",
        "PASS" if result["overall_pass"] else "FAIL",
        "| error_rate=",
        result["observed"]["error_rate"],
        "| p95_regression_pct=",
        result["observed"]["p95_regression_vs_baseline_pct"],
        "| shed_rate=",
        result["observed"]["nominal_shed_rate"],
    )

    if not result["overall_pass"]:
        raise SystemExit("slo reliability gate failed")


if __name__ == "__main__":
    main()
