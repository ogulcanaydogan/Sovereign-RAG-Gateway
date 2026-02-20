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
    return parser.parse_args()


def _read_benchmark_summary(path: Path | None) -> dict[str, Any] | None:
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
    )
    output_path.write_text(report, encoding="utf-8")
    print(f"generated weekly report: {output_path}")


if __name__ == "__main__":
    main()
