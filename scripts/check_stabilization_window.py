#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import sleep
from typing import Any

DEFAULT_REQUIRED_COUNTS = (
    "deploy-smoke=3,release-verify=2,ci=1,terraform-validate=1,slo-reliability=1"
)


@dataclass(frozen=True)
class WorkflowWindowStats:
    workflow: str
    required_successes: int
    total_runs: int
    success_runs: int
    failure_runs: int

    @property
    def passed(self) -> bool:
        return self.success_runs >= self.required_successes


def _run_gh_json(path: str, retries: int, retry_backoff_s: float) -> object:
    last_error = ""
    for attempt in range(1, retries + 1):
        result = subprocess.run(
            ["gh", "api", path],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"invalid JSON from gh api '{path}': {exc}") from exc

        last_error = result.stderr.strip() or result.stdout.strip()
        if attempt < retries:
            sleep(max(retry_backoff_s, 0.0))

    raise RuntimeError(f"gh api failed for '{path}': {last_error}")


def parse_required_counts(raw: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for chunk in raw.split(","):
        item = chunk.strip()
        if item == "":
            continue
        if "=" not in item:
            raise ValueError(f"invalid required-counts entry: {item}")
        name, count_raw = item.split("=", 1)
        workflow = name.strip().lower()
        if workflow == "":
            raise ValueError(f"invalid required-counts entry: {item}")
        count = int(count_raw)
        if count < 0:
            raise ValueError(f"required count must be >= 0 for workflow '{workflow}'")
        values[workflow] = count
    if not values:
        raise ValueError("required-counts cannot be empty")
    return values


def _parse_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _resolve_workflow_ids(
    *,
    repo: str,
    retries: int,
    retry_backoff_s: float,
) -> dict[str, int]:
    payload = _run_gh_json(
        f"repos/{repo}/actions/workflows?per_page=100",
        retries=retries,
        retry_backoff_s=retry_backoff_s,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("invalid workflows payload")

    raw_workflows = payload.get("workflows")
    if not isinstance(raw_workflows, list):
        raise RuntimeError("workflows payload missing workflows list")

    mapping: dict[str, int] = {}
    for item in raw_workflows:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip().lower()
        workflow_id = item.get("id")
        if name and isinstance(workflow_id, int):
            mapping[name] = workflow_id
    return mapping


def _filter_window_runs(
    runs_payload: object,
    window_start: datetime,
    window_end: datetime,
) -> tuple[int, int, int]:
    if not isinstance(runs_payload, dict):
        raise RuntimeError("invalid workflow runs payload")

    raw_runs = runs_payload.get("workflow_runs")
    if not isinstance(raw_runs, list):
        raise RuntimeError("workflow runs payload missing workflow_runs")

    total = 0
    successes = 0
    failures = 0

    for item in raw_runs:
        if not isinstance(item, dict):
            continue
        created_at_raw = str(item.get("created_at", "")).strip()
        if created_at_raw == "":
            continue
        created_at = _parse_timestamp(created_at_raw)
        if created_at < window_start or created_at > window_end:
            continue

        total += 1
        conclusion = str(item.get("conclusion", "")).strip().lower()
        if conclusion == "success":
            successes += 1
        else:
            failures += 1

    return total, successes, failures


def collect_window_stats(
    *,
    repo: str,
    required_counts: dict[str, int],
    window_days: int,
    fail_on_missing: bool,
    retries: int,
    retry_backoff_s: float,
) -> tuple[dict[str, WorkflowWindowStats], list[str], dict[str, str]]:
    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(days=max(window_days, 1))

    workflow_ids = _resolve_workflow_ids(
        repo=repo,
        retries=retries,
        retry_backoff_s=retry_backoff_s,
    )

    stats: dict[str, WorkflowWindowStats] = {}
    errors: list[str] = []

    for workflow_name, required_successes in required_counts.items():
        workflow_id = workflow_ids.get(workflow_name)
        if workflow_id is None:
            if fail_on_missing:
                errors.append(f"required workflow not found: {workflow_name}")
            stats[workflow_name] = WorkflowWindowStats(
                workflow=workflow_name,
                required_successes=required_successes,
                total_runs=0,
                success_runs=0,
                failure_runs=0,
            )
            continue

        runs_payload = _run_gh_json(
            (
                f"repos/{repo}/actions/workflows/{workflow_id}/runs"
                "?status=completed&per_page=100"
            ),
            retries=retries,
            retry_backoff_s=retry_backoff_s,
        )
        total, successes, failures = _filter_window_runs(
            runs_payload,
            window_start=window_start,
            window_end=window_end,
        )
        stats[workflow_name] = WorkflowWindowStats(
            workflow=workflow_name,
            required_successes=required_successes,
            total_runs=total,
            success_runs=successes,
            failure_runs=failures,
        )

    window = {
        "start": window_start.isoformat(),
        "end": window_end.isoformat(),
    }
    return stats, errors, window


def _build_report_payload(
    *,
    repository: str,
    window: dict[str, str],
    stats: dict[str, WorkflowWindowStats],
    errors: list[str],
) -> dict[str, Any]:
    missing_requirements: list[dict[str, Any]] = []
    observed: dict[str, dict[str, Any]] = {}

    for workflow_name, item in stats.items():
        observed[workflow_name] = {
            "required_successes": item.required_successes,
            "total_runs": item.total_runs,
            "success_runs": item.success_runs,
            "failure_runs": item.failure_runs,
            "pass": item.passed,
        }
        if not item.passed:
            missing_requirements.append(
                {
                    "workflow": workflow_name,
                    "required_successes": item.required_successes,
                    "observed_successes": item.success_runs,
                }
            )

    overall_pass = len(errors) == 0 and len(missing_requirements) == 0
    return {
        "repository": repository,
        "window": window,
        "requirements": {name: item.required_successes for name, item in stats.items()},
        "observed": observed,
        "overall_pass": overall_pass,
        "missing_requirements": missing_requirements,
        "errors": errors,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check stabilization-window workflow successes for deploy-smoke, "
            "release-verify, ci, terraform-validate"
        )
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="owner/repo (defaults to GITHUB_REPOSITORY env var)",
    )
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument(
        "--required-counts",
        default=DEFAULT_REQUIRED_COUNTS,
        help="comma-separated pairs workflow=count",
    )
    parser.add_argument("--json-report", default="")
    parser.add_argument(
        "--fail-on-missing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="fail when any required workflow is missing",
    )
    parser.add_argument("--gh-retries", type=int, default=3)
    parser.add_argument("--gh-retry-backoff-s", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    repo = args.repo.strip()
    if repo == "":
        raise SystemExit("repo must be non-empty")

    required_counts = parse_required_counts(args.required_counts)
    stats, errors, window = collect_window_stats(
        repo=repo,
        required_counts=required_counts,
        window_days=max(args.window_days, 1),
        fail_on_missing=bool(args.fail_on_missing),
        retries=max(args.gh_retries, 1),
        retry_backoff_s=args.gh_retry_backoff_s,
    )

    payload = _build_report_payload(
        repository=repo,
        window=window,
        stats=stats,
        errors=errors,
    )

    for workflow_name, item in stats.items():
        status = "pass" if item.passed else "fail"
        print(
            f"[{status}] {workflow_name}: success={item.success_runs} "
            f"required={item.required_successes} total={item.total_runs} "
            f"failure={item.failure_runs}"
        )

    if errors:
        for error in errors:
            print(f"[error] {error}")

    report_path_raw = args.json_report.strip()
    if report_path_raw:
        report_path = Path(report_path_raw)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"JSON report written: {report_path}")

    if not bool(payload["overall_pass"]):
        raise SystemExit("stabilization window requirements not satisfied")


if __name__ == "__main__":
    main()
