#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from time import sleep
from typing import Any


def is_prerelease_tag(tag_name: str) -> bool:
    normalized = tag_name.strip().lstrip("v")
    return "-" in normalized


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


def resolve_tag_commit_sha_from_payloads(
    ref_payload: object,
    annotated_tag_payload: object | None,
) -> str:
    if not isinstance(ref_payload, dict):
        raise RuntimeError("invalid git ref payload")

    ref_object = ref_payload.get("object")
    if not isinstance(ref_object, dict):
        raise RuntimeError("git ref payload missing object")

    object_type = str(ref_object.get("type", "")).strip()
    object_sha = str(ref_object.get("sha", "")).strip()
    if object_sha == "":
        raise RuntimeError("git ref payload missing sha")

    if object_type == "commit":
        return object_sha

    if object_type != "tag":
        raise RuntimeError(f"unsupported git ref object type: {object_type}")

    if not isinstance(annotated_tag_payload, dict):
        raise RuntimeError("annotated tag payload is required for tag refs")

    tag_object = annotated_tag_payload.get("object")
    if not isinstance(tag_object, dict):
        raise RuntimeError("annotated tag payload missing object")

    tag_object_type = str(tag_object.get("type", "")).strip()
    tag_object_sha = str(tag_object.get("sha", "")).strip()
    if tag_object_type != "commit" or tag_object_sha == "":
        raise RuntimeError("annotated tag does not point to a commit")
    return tag_object_sha


def resolve_tag_commit_sha(
    repo: str,
    tag: str,
    retries: int,
    retry_backoff_s: float,
) -> str:
    ref_payload = _run_gh_json(
        f"repos/{repo}/git/ref/tags/{tag}",
        retries=retries,
        retry_backoff_s=retry_backoff_s,
    )

    if not isinstance(ref_payload, dict):
        raise RuntimeError("invalid git ref payload")
    ref_object = ref_payload.get("object")
    if not isinstance(ref_object, dict):
        raise RuntimeError("git ref payload missing object")

    if str(ref_object.get("type", "")).strip() == "tag":
        tag_sha = str(ref_object.get("sha", "")).strip()
        annotated_payload = _run_gh_json(
            f"repos/{repo}/git/tags/{tag_sha}",
            retries=retries,
            retry_backoff_s=retry_backoff_s,
        )
    else:
        annotated_payload = None

    return resolve_tag_commit_sha_from_payloads(ref_payload, annotated_payload)


def find_successful_required_run(
    runs_payload: object,
    required_workflow: str,
) -> dict[str, Any] | None:
    if not isinstance(runs_payload, dict):
        raise RuntimeError("invalid workflow runs payload")

    raw_runs = runs_payload.get("workflow_runs")
    if not isinstance(raw_runs, list):
        raise RuntimeError("workflow runs payload missing workflow_runs")

    required_normalized = required_workflow.strip().lower()
    for item in raw_runs:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip().lower()
        path = str(item.get("path", "")).strip().lower()
        conclusion = str(item.get("conclusion", "")).strip().lower()

        matches_name = name == required_normalized
        matches_path = path.endswith(f"/{required_normalized}.yml")
        if (matches_name or matches_path) and conclusion == "success":
            return item

    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enforce GA release gate: same-commit release-verify success"
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="owner/repo (defaults to GITHUB_REPOSITORY env var)",
    )
    parser.add_argument("--tag", required=True, help="release tag (e.g. v0.7.0)")
    parser.add_argument(
        "--required-workflow",
        default="release-verify",
        help="required workflow name for GA release gating",
    )
    parser.add_argument("--gh-retries", type=int, default=3)
    parser.add_argument("--gh-retry-backoff-s", type=float, default=1.0)
    args = parser.parse_args()

    repo = args.repo.strip()
    tag = args.tag.strip()
    required_workflow = args.required_workflow.strip()

    if repo == "":
        raise SystemExit("repo must be non-empty")
    if tag == "":
        raise SystemExit("tag must be non-empty")

    if is_prerelease_tag(tag):
        print(f"GA gate bypassed for prerelease tag: {tag}")
        return

    commit_sha = resolve_tag_commit_sha(
        repo=repo,
        tag=tag,
        retries=max(args.gh_retries, 1),
        retry_backoff_s=args.gh_retry_backoff_s,
    )

    runs_payload = _run_gh_json(
        f"repos/{repo}/actions/runs?head_sha={commit_sha}&status=completed&per_page=100",
        retries=max(args.gh_retries, 1),
        retry_backoff_s=args.gh_retry_backoff_s,
    )

    run = find_successful_required_run(runs_payload, required_workflow=required_workflow)
    if run is None:
        raise SystemExit(
            "GA release gate failed: "
            f"no successful '{required_workflow}' run found for commit {commit_sha}"
        )

    run_id = str(run.get("id", "n/a"))
    run_url = str(run.get("html_url", "n/a"))
    print(
        "GA release gate passed: "
        f"workflow={required_workflow} commit={commit_sha} run_id={run_id} url={run_url}"
    )


if __name__ == "__main__":
    main()
