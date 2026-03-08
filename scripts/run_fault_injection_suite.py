#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    # Allow direct script execution in CI (`python scripts/...`).
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.benchmark_runner import load_dataset, run_benchmark

SCENARIOS: tuple[tuple[str, str], ...] = (
    ("provider_429_storm", "provider_429"),
    ("policy_outage_fail_closed", "policy_outage"),
    ("budget_backend_transient_failure", "budget_backend_transient"),
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deterministic fault-injection benchmark suite"
    )
    parser.add_argument("--out-dir", default="artifacts/fault-injection")
    parser.add_argument(
        "--dataset",
        default="benchmarks/data/synthetic_prompts.jsonl",
        help="Dataset JSONL path",
    )
    parser.add_argument("--dataset-version", default="v1")
    parser.add_argument(
        "--json-report",
        default="",
        help="Optional explicit output path (defaults to <out-dir>/fault-summary.json)",
    )
    return parser.parse_args()


def _read_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid summary JSON object: {path}")
    return payload


def _metric(summary: dict[str, Any], key: str) -> float:
    metrics = summary.get("metrics")
    if not isinstance(metrics, dict):
        raise RuntimeError("summary missing metrics object")
    raw_value = metrics.get(key)
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    if isinstance(raw_value, str) and raw_value.strip() != "":
        return float(raw_value)
    raise RuntimeError(f"summary metric missing: {key}")


def _to_int(value: float) -> int:
    return int(round(value))


def main() -> None:
    args = _parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dataset_rows = load_dataset(Path(args.dataset))

    scenario_rows: list[dict[str, Any]] = []
    total_requests = 0
    total_errors = 0
    max_latency_p95 = 0.0

    for scenario, expected_fault in SCENARIOS:
        scenario_out = out_dir / scenario
        run_benchmark(
            out_dir=scenario_out,
            scenario=scenario,
            dataset_version=args.dataset_version,
            dataset_rows=dataset_rows,
        )
        summary = _read_summary(scenario_out / "results_summary.json")

        requests_total = _metric(summary, "requests_total")
        errors_total = _metric(summary, "errors_total")
        latency_p95 = _metric(summary, "latency_ms_p95")
        observed_fault = str(summary.get("metrics", {}).get("fault_type", "unknown"))
        attribution = _metric(summary, "fault_attribution_accuracy")

        scenario_pass = (
            observed_fault == expected_fault
            and requests_total > 0
            and attribution >= 0.9
        )

        scenario_rows.append(
            {
                "scenario": scenario,
                "expected_fault_type": expected_fault,
                "observed_fault_type": observed_fault,
                "requests_total": _to_int(requests_total),
                "errors_total": _to_int(errors_total),
                "error_rate": round(errors_total / requests_total, 6),
                "latency_ms_p95": round(latency_p95, 4),
                "fault_attribution_accuracy": round(attribution, 4),
                "status": "pass" if scenario_pass else "fail",
            }
        )

        total_requests += _to_int(requests_total)
        total_errors += _to_int(errors_total)
        max_latency_p95 = max(max_latency_p95, latency_p95)

    failed_scenarios = [row for row in scenario_rows if row["status"] != "pass"]
    totals = {
        "scenarios_total": len(scenario_rows),
        "passed_scenarios": len(scenario_rows) - len(failed_scenarios),
        "failed_scenarios": len(failed_scenarios),
        "requests_total": total_requests,
        "errors_total": total_errors,
        "error_rate": round((total_errors / total_requests) if total_requests > 0 else 1.0, 6),
        "max_latency_ms_p95": round(max_latency_p95, 4),
    }

    report = {
        "suite": "fault-injection-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": args.dataset,
        "dataset_version": args.dataset_version,
        "totals": totals,
        "scenarios": scenario_rows,
    }

    out_path = (
        Path(args.json_report)
        if args.json_report.strip()
        else out_dir / "fault-summary.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"fault suite summary written: {out_path}")
    print(
        "fault suite:",
        "PASS" if totals["failed_scenarios"] == 0 else "FAIL",
        f"(failed={totals['failed_scenarios']})",
    )

    if totals["failed_scenarios"] > 0:
        raise SystemExit("fault injection suite failed")


if __name__ == "__main__":
    main()
