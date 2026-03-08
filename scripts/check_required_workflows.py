#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from time import sleep

DEFAULT_REQUIRED_WORKFLOWS = (
    "ci",
    "deploy-smoke",
    "terraform-validate",
    "evidence-replay-smoke",
    "release-verify",
    "slo-reliability",
)


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


def parse_required_workflows(raw: str) -> list[str]:
    values = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not values:
        raise ValueError("required workflows list cannot be empty")
    return values


def extract_workflow_names(payload: object) -> set[str]:
    if not isinstance(payload, dict):
        raise RuntimeError("invalid workflows payload")

    raw_workflows = payload.get("workflows")
    if not isinstance(raw_workflows, list):
        raise RuntimeError("workflows payload missing workflows list")

    names: set[str] = set()
    for item in raw_workflows:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip().lower()
        if name:
            names.add(name)
    return names


def find_missing_required_workflows(required: list[str], available: set[str]) -> list[str]:
    return sorted([name for name in required if name not in available])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify required GitHub Actions workflows exist in repository"
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="owner/repo (defaults to GITHUB_REPOSITORY env var)",
    )
    parser.add_argument(
        "--required-workflows",
        default=",".join(DEFAULT_REQUIRED_WORKFLOWS),
        help="comma-separated required workflow names",
    )
    parser.add_argument("--gh-retries", type=int, default=3)
    parser.add_argument("--gh-retry-backoff-s", type=float, default=1.0)
    args = parser.parse_args()

    repo = args.repo.strip()
    if repo == "":
        raise SystemExit("repo must be non-empty")

    required = parse_required_workflows(args.required_workflows)
    payload = _run_gh_json(
        f"repos/{repo}/actions/workflows?per_page=100",
        retries=max(args.gh_retries, 1),
        retry_backoff_s=args.gh_retry_backoff_s,
    )
    available = extract_workflow_names(payload)
    missing = find_missing_required_workflows(required, available)

    print("required workflows:", ", ".join(required))
    print("available workflows:", ", ".join(sorted(available)))
    if missing:
        raise SystemExit("missing required workflows: " + ", ".join(missing))

    print("required workflow check passed")


if __name__ == "__main__":
    main()
