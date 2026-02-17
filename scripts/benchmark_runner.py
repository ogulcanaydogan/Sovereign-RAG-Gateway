#!/usr/bin/env python3
import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path


def run_benchmark(out_dir: Path, scenario: str, dataset_version: str) -> None:
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    request_metrics_path = raw_dir / "request_metrics.csv"
    summary_path = out_dir / "results_summary.json"
    report_path = out_dir / "report.md"

    rows = [
        {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "request_id": "req-1",
            "tenant_id": "tenant-a",
            "scenario": scenario,
            "classification": "phi",
            "is_rag": False,
            "policy_decision": "allow",
            "redaction_count": 1,
            "provider": "stub",
            "model": "gpt-4o-mini",
            "status_code": 200,
            "latency_ms": 120,
            "tokens_in": 40,
            "tokens_out": 20,
            "cost_usd": 0.00006,
            "leakage_detected": False,
            "has_citations": False,
        }
    ]

    with request_metrics_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "run_id": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H-%M-%SZ"),
        "project": "sovereign-rag-gateway",
        "scenario": scenario,
        "dataset_version": dataset_version,
        "cluster_profile": {
            "kubernetes_version": "1.31",
            "node_type": "kind-default",
            "node_count": 1,
        },
        "metrics": {
            "requests_total": 1,
            "errors_total": 0,
            "leakage_rate": 0.0,
            "redaction_false_positive_rate": 0.0,
            "policy_deny_precision": 1.0,
            "policy_deny_recall": 1.0,
            "latency_ms_p50": 120.0,
            "latency_ms_p95": 120.0,
            "latency_ms_p99": 120.0,
            "cost_drift_pct": 0.0,
            "citation_presence_rate": 0.0,
            "groundedness_score": 0.0,
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    report_path.write_text(
        "# Benchmark Report\n\n"
        f"- Scenario: `{scenario}`\n"
        f"- Dataset: `{dataset_version}`\n"
        "- Requests: `1`\n"
        "- p95 latency: `120ms`\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run benchmark skeleton")
    parser.add_argument("--out", default="artifacts/benchmarks", help="Output directory")
    parser.add_argument("--scenario", default="enforce_redact", help="Scenario name")
    parser.add_argument("--dataset-version", default="v1", help="Dataset version")
    args = parser.parse_args()

    out_dir = Path(args.out)
    run_benchmark(out_dir=out_dir, scenario=args.scenario, dataset_version=args.dataset_version)
    print(f"Benchmark artifacts written to {out_dir}")


if __name__ == "__main__":
    main()
