#!/usr/bin/env python3
"""Generate a weekly benchmark/evidence markdown report."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkflowEvidence:
    name: str
    run_id: str
    run_url: str
    completed_at: str
    result: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate weekly evidence markdown report")
    parser.add_argument(
        "--report-date",
        default=date.today().isoformat(),
        help="Report date in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output markdown path",
    )
    parser.add_argument("--deploy-smoke-run-id", default="")
    parser.add_argument("--deploy-smoke-url", default="")
    parser.add_argument("--deploy-smoke-completed-at", default="")
    parser.add_argument("--deploy-smoke-result", default="success")
    parser.add_argument("--release-run-id", default="")
    parser.add_argument("--release-run-url", default="")
    parser.add_argument("--release-run-completed-at", default="")
    parser.add_argument("--release-run-result", default="success")
    parser.add_argument("--release-tag", default="")
    parser.add_argument("--release-url", default="")
    parser.add_argument(
        "--benchmark-summary",
        default="",
        help="Optional benchmark summary JSON path",
    )
    parser.add_argument(
        "--stabilization-summary",
        default="",
        help="Optional stabilization summary JSON path",
    )
    parser.add_argument(
        "--release-snapshot-json",
        default="",
        help="Optional release verification snapshot JSON path",
    )
    parser.add_argument(
        "--release-snapshot-png",
        default="",
        help="Optional release verification snapshot PNG path",
    )
    parser.add_argument(
        "--slo-summary",
        default="",
        help="Optional reliability/SLO summary JSON path",
    )
    parser.add_argument(
        "--fault-summary",
        default="",
        help="Optional fault injection summary JSON path",
    )
    parser.add_argument(
        "--soak-summary",
        default="",
        help="Optional soak summary JSON path",
    )
    return parser.parse_args()


def _read_benchmark_summary(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_json_object(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _workflow(
    name: str,
    run_id: str,
    run_url: str,
    completed_at: str,
    result: str,
) -> WorkflowEvidence:
    return WorkflowEvidence(
        name=name,
        run_id=run_id or "n/a",
        run_url=run_url or "n/a",
        completed_at=completed_at or "n/a",
        result=result or "unknown",
    )


def render_report(
    *,
    report_date: str,
    generated_at: str,
    deploy_smoke: WorkflowEvidence,
    release: WorkflowEvidence,
    release_tag: str,
    release_url: str,
    benchmark_summary: dict[str, Any] | None,
    stabilization_summary: dict[str, Any] | None = None,
    release_snapshot_json_path: str = "",
    release_snapshot_png_path: str = "",
    slo_summary: dict[str, Any] | None = None,
    fault_summary: dict[str, Any] | None = None,
    soak_summary: dict[str, Any] | None = None,
) -> str:
    lines = [
        f"# Weekly Report - {report_date}",
        "",
        "## Scope",
        (
            "Automated weekly benchmark/evidence snapshot generated from "
            "the latest CI/release metadata."
        ),
        "",
        "## Validation Evidence",
        f"- Workflow: `{deploy_smoke.name}`",
        f"- Run ID: `{deploy_smoke.run_id}`",
        f"- Completed: `{deploy_smoke.completed_at}`",
        f"- URL: {deploy_smoke.run_url}",
        f"- Result: `{deploy_smoke.result}`",
        "",
        "## Release Evidence",
        f"- Workflow: `{release.name}`",
        f"- Run ID: `{release.run_id}`",
        f"- Completed: `{release.completed_at}`",
        f"- URL: {release.run_url}",
        f"- Result: `{release.result}`",
    ]
    if release_tag:
        lines.append(f"- Release tag: `{release_tag}`")
    if release_url:
        lines.append(f"- Release URL: {release_url}")

    lines.extend(["", "## Benchmark Snapshot"])
    if benchmark_summary is None:
        lines.append("- No benchmark summary JSON was available in this run context.")
    else:
        metrics = benchmark_summary.get("metrics", {})
        lines.append(f"- Scenario: `{benchmark_summary.get('scenario', 'unknown')}`")
        lines.append(f"- Requests: `{metrics.get('requests_total', 'n/a')}`")
        lines.append(f"- Leakage rate: `{metrics.get('leakage_rate', 'n/a')}`")
        lines.append(f"- Latency p95 (ms): `{metrics.get('latency_ms_p95', 'n/a')}`")
        lines.append(f"- Cost drift (%): `{metrics.get('cost_drift_pct', 'n/a')}`")
        lines.append(f"- Citation presence: `{metrics.get('citation_presence_rate', 'n/a')}`")

    lines.extend(["", "## Stabilization Window"])
    if stabilization_summary is None:
        lines.append("- No stabilization summary JSON was available in this run context.")
    else:
        lines.append(f"- Overall pass: `{stabilization_summary.get('overall_pass', 'n/a')}`")
        observed = stabilization_summary.get("observed", {})
        if isinstance(observed, dict):
            for workflow_name in sorted(observed):
                item = observed.get(workflow_name)
                if not isinstance(item, dict):
                    continue
                lines.append(
                    f"- `{workflow_name}`: success=`{item.get('success_runs', 'n/a')}` "
                    f"required=`{item.get('required_successes', 'n/a')}` "
                    f"pass=`{item.get('pass', 'n/a')}`"
                )

    lines.extend(["", "## Release Verification Snapshot"])
    if release_snapshot_json_path.strip():
        lines.append(f"- Snapshot JSON: `{release_snapshot_json_path.strip()}`")
    else:
        lines.append("- Snapshot JSON: `n/a`")
    if release_snapshot_png_path.strip():
        lines.append(f"- Snapshot PNG: `{release_snapshot_png_path.strip()}`")
    else:
        lines.append("- Snapshot PNG: `n/a`")

    lines.extend(["", "## Reliability/SLO Summary"])
    if slo_summary is None:
        lines.append("- No reliability/SLO summary JSON was available in this run context.")
    else:
        lines.append(f"- Overall pass: `{slo_summary.get('overall_pass', 'n/a')}`")
        thresholds = slo_summary.get("thresholds", {})
        observed = slo_summary.get("observed", {})
        if isinstance(thresholds, dict) and isinstance(observed, dict):
            lines.append(
                "| Signal | Observed | Threshold |",
            )
            lines.append("|---|---:|---:|")
            lines.append(
                "| error_rate | "
                f"`{observed.get('error_rate', 'n/a')}` | "
                f"`<= {thresholds.get('max_error_rate', 'n/a')}` |"
            )
            lines.append(
                "| p95_regression_vs_baseline_pct | "
                f"`{observed.get('p95_regression_vs_baseline_pct', 'n/a')}` | "
                f"`<= {thresholds.get('max_p95_regression_pct', 'n/a')}` |"
            )
            lines.append(
                "| nominal_shed_rate | "
                f"`{observed.get('nominal_shed_rate', 'n/a')}` | "
                f"`<= {thresholds.get('max_nominal_shed_rate', 'n/a')}` |"
            )
    if fault_summary is not None:
        totals = fault_summary.get("totals", {})
        if isinstance(totals, dict):
            lines.append(
                "- Fault suite: "
                f"failed=`{totals.get('failed_scenarios', 'n/a')}` "
                f"total=`{totals.get('scenarios_total', 'n/a')}` "
                f"error_rate=`{totals.get('error_rate', 'n/a')}`"
            )
    if soak_summary is not None:
        metrics = soak_summary.get("metrics", {})
        if isinstance(metrics, dict):
            lines.append(
                "- Soak: "
                f"p95_ms=`{metrics.get('latency_ms_p95', 'n/a')}` "
                f"error_rate=`{metrics.get('errors_total', 'n/a')}`/"
                f"`{metrics.get('requests_total', 'n/a')}` "
                f"shed_rate=`{metrics.get('shed_rate', 'n/a')}`"
            )

    lines.extend(
        [
            "",
            "## Outcome",
            (
                "This report is generated automatically to provide reproducible "
                "weekly evidence pointers."
            ),
            "",
            "## Metadata",
            f"- Generated at: `{generated_at}`",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    args = _parse_args()
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()

    benchmark_path = Path(args.benchmark_summary) if args.benchmark_summary else None
    benchmark_summary = _read_benchmark_summary(benchmark_path)
    stabilization_path = (
        Path(args.stabilization_summary) if args.stabilization_summary else None
    )
    stabilization_summary = _read_json_object(stabilization_path)
    slo_summary = _read_json_object(Path(args.slo_summary)) if args.slo_summary else None
    fault_summary = _read_json_object(Path(args.fault_summary)) if args.fault_summary else None
    soak_summary = _read_json_object(Path(args.soak_summary)) if args.soak_summary else None

    report = render_report(
        report_date=args.report_date,
        generated_at=now,
        deploy_smoke=_workflow(
            "deploy-smoke",
            args.deploy_smoke_run_id,
            args.deploy_smoke_url,
            args.deploy_smoke_completed_at,
            args.deploy_smoke_result,
        ),
        release=_workflow(
            "release",
            args.release_run_id,
            args.release_run_url,
            args.release_run_completed_at,
            args.release_run_result,
        ),
        release_tag=args.release_tag,
        release_url=args.release_url,
        benchmark_summary=benchmark_summary,
        stabilization_summary=stabilization_summary,
        release_snapshot_json_path=args.release_snapshot_json,
        release_snapshot_png_path=args.release_snapshot_png,
        slo_summary=slo_summary,
        fault_summary=fault_summary,
        soak_summary=soak_summary,
    )
    output_path.write_text(report, encoding="utf-8")
    print(f"generated weekly report: {output_path}")


if __name__ == "__main__":
    main()
