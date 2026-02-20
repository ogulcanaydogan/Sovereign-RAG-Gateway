#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from time import sleep

DEFAULT_EXPECTED_ASSETS = (
    "bundle.json",
    "bundle.md",
    "bundle.sha256",
    "bundle.sig",
    "events.jsonl",
    "release-evidence-metadata.json",
    "sbom.spdx.json",
)


@dataclass(frozen=True)
class ReleaseAssetCheck:
    tag_name: str
    url: str
    draft: bool
    prerelease: bool
    assets_present: set[str]
    expected_assets: set[str]

    @property
    def missing_assets(self) -> set[str]:
        return self.expected_assets.difference(self.assets_present)


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


def _extract_assets(payload: object) -> set[str]:
    if not isinstance(payload, dict):
        raise ValueError("release payload must be a JSON object")
    raw_assets = payload.get("assets", [])
    if not isinstance(raw_assets, list):
        raise ValueError("release payload assets must be a list")

    assets: set[str] = set()
    for item in raw_assets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if name:
            assets.add(name)
    return assets


def check_release_payload(payload: object, expected_assets: set[str]) -> ReleaseAssetCheck:
    if not isinstance(payload, dict):
        raise ValueError("release payload must be a JSON object")

    tag_name = str(payload.get("tag_name", "")).strip()
    if tag_name == "":
        raise ValueError("release payload missing tag_name")
    url = str(payload.get("html_url", "")).strip()
    draft = bool(payload.get("draft", False))
    prerelease = bool(payload.get("prerelease", False))

    assets = _extract_assets(payload)
    return ReleaseAssetCheck(
        tag_name=tag_name,
        url=url,
        draft=draft,
        prerelease=prerelease,
        assets_present=assets,
        expected_assets=expected_assets,
    )


def fetch_release_payload(
    repo: str,
    tag: str | None,
    latest: bool,
    gh_retries: int,
    gh_retry_backoff_s: float,
) -> object:
    normalized_repo = repo.strip()
    if normalized_repo == "":
        raise ValueError("repo must be non-empty")

    if latest:
        payload = _run_gh_json(
            f"repos/{normalized_repo}/releases?per_page=1",
            retries=gh_retries,
            retry_backoff_s=gh_retry_backoff_s,
        )
        if not isinstance(payload, list) or len(payload) == 0:
            raise RuntimeError("no releases found for repository")
        return payload[0]

    if not tag:
        raise ValueError("tag is required when latest is false")
    normalized_tag = tag.strip()
    if normalized_tag == "":
        raise ValueError("tag must be non-empty")
    return _run_gh_json(
        f"repos/{normalized_repo}/releases/tags/{normalized_tag}",
        retries=gh_retries,
        retry_backoff_s=gh_retry_backoff_s,
    )


def parse_expected_assets(raw: str) -> set[str]:
    values = {item.strip() for item in raw.split(",") if item.strip()}
    if not values:
        raise ValueError("expected assets set cannot be empty")
    return values


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify GitHub release has required evidence assets"
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="owner/repo (defaults to GITHUB_REPOSITORY env var)",
    )
    parser.add_argument("--tag", default="", help="release tag to validate")
    parser.add_argument(
        "--latest",
        action="store_true",
        help="validate latest release instead of an explicit tag",
    )
    parser.add_argument(
        "--expected-assets",
        default=",".join(DEFAULT_EXPECTED_ASSETS),
        help="comma-separated asset names required on the release",
    )
    parser.add_argument(
        "--prerelease-mode",
        choices=("any", "true", "false"),
        default="any",
        help="enforce prerelease state",
    )
    parser.add_argument(
        "--allow-draft",
        action="store_true",
        help="allow draft releases",
    )
    parser.add_argument(
        "--gh-retries",
        type=int,
        default=3,
        help="number of retry attempts for gh api calls",
    )
    parser.add_argument(
        "--gh-retry-backoff-s",
        type=float,
        default=1.0,
        help="seconds to wait between gh api retries",
    )
    args = parser.parse_args()

    expected_assets = parse_expected_assets(args.expected_assets)
    payload = fetch_release_payload(
        repo=args.repo,
        tag=args.tag,
        latest=args.latest,
        gh_retries=max(args.gh_retries, 1),
        gh_retry_backoff_s=args.gh_retry_backoff_s,
    )
    result = check_release_payload(payload=payload, expected_assets=expected_assets)

    if not args.allow_draft and result.draft:
        raise SystemExit(f"release {result.tag_name} is draft")

    if args.prerelease_mode == "true" and not result.prerelease:
        raise SystemExit(f"release {result.tag_name} must be prerelease=true")
    if args.prerelease_mode == "false" and result.prerelease:
        raise SystemExit(f"release {result.tag_name} must be prerelease=false")

    missing_assets = sorted(result.missing_assets)
    if missing_assets:
        raise SystemExit(
            "missing required release assets: " + ", ".join(missing_assets)
        )

    print(f"release asset verification OK for {result.tag_name}")
    print(f"url: {result.url}")
    print(f"assets: {', '.join(sorted(result.assets_present))}")


if __name__ == "__main__":
    main()
