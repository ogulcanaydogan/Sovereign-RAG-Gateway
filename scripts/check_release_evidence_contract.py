#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_release_assets import (
    check_release_payload,
    compare_semver_tags,
    download_assets,
    fetch_release_payloads,
    verify_bundle_sha256,
    verify_bundle_signature,
)

REQUIRED_EVIDENCE_ASSETS = {
    "bundle.json",
    "bundle.sha256",
    "bundle.sig",
    "release-evidence-public.pem",
    "release-evidence-metadata.json",
}


@dataclass(frozen=True)
class EvidenceContractResult:
    tag_name: str
    url: str
    status: str
    missing_assets: list[str]
    digest_verified: bool
    signature_verified: bool
    metadata_valid: bool
    legacy_gap_applied: bool
    errors: list[str]


def _is_before_tag(tag_name: str, threshold_tag: str) -> bool:
    if threshold_tag.strip() == "":
        return False
    return compare_semver_tags(tag_name, threshold_tag) < 0


def _load_metadata(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError("release-evidence-metadata.json must be a JSON object")
    return parsed


def _metadata_field_basename(metadata: dict[str, Any], key: str) -> str:
    value = str(metadata.get(key, "")).strip()
    if value == "":
        raise RuntimeError(f"metadata missing required field: {key}")
    return Path(value).name


def _validate_metadata_consistency(metadata: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    bundle_name = _metadata_field_basename(metadata, "bundle_path")
    if bundle_name != "bundle.json":
        errors.append(f"metadata bundle_path must point to bundle.json (got {bundle_name})")

    digest_name = _metadata_field_basename(metadata, "bundle_sha256_path")
    if digest_name != "bundle.sha256":
        errors.append(
            "metadata bundle_sha256_path must point to bundle.sha256 "
            f"(got {digest_name})"
        )

    signature_name = _metadata_field_basename(metadata, "bundle_signature_path")
    if signature_name != "bundle.sig":
        errors.append(
            "metadata bundle_signature_path must point to bundle.sig "
            f"(got {signature_name})"
        )

    public_key_asset = str(metadata.get("public_key_asset", "")).strip()
    if public_key_asset != "release-evidence-public.pem":
        errors.append(
            "metadata public_key_asset must be release-evidence-public.pem "
            f"(got {public_key_asset or 'missing'})"
        )

    public_key_name = _metadata_field_basename(metadata, "public_key_path")
    if public_key_name != "release-evidence-public.pem":
        errors.append(
            "metadata public_key_path must point to release-evidence-public.pem "
            f"(got {public_key_name})"
        )

    return errors


def validate_release_evidence_contract(
    *,
    payload: object,
    allow_legacy_before_tag: str,
    github_token: str | None,
) -> EvidenceContractResult:
    release = check_release_payload(payload, expected_assets=REQUIRED_EVIDENCE_ASSETS)
    errors: list[str] = []
    digest_verified = False
    signature_verified = False
    metadata_valid = False
    legacy_gap_applied = False

    missing_assets = sorted(release.missing_assets)
    if missing_assets:
        if _is_before_tag(release.tag_name, allow_legacy_before_tag):
            legacy_gap_applied = True
        else:
            errors.append("missing required release evidence assets: " + ", ".join(missing_assets))

    if not missing_assets:
        try:
            with TemporaryDirectory(prefix=f"srg-contract-{release.tag_name}-") as tmp_dir_name:
                downloaded = download_assets(
                    result=release,
                    asset_names=REQUIRED_EVIDENCE_ASSETS,
                    out_dir=Path(tmp_dir_name),
                    github_token=github_token,
                    timeout_s=30.0,
                )

                digest_ok, expected_digest, actual_digest, _ = verify_bundle_sha256(
                    bundle_path=downloaded["bundle.json"],
                    digest_path=downloaded["bundle.sha256"],
                )
                if not digest_ok:
                    errors.append(
                        "bundle SHA-256 mismatch: "
                        f"expected={expected_digest} actual={actual_digest}"
                    )
                else:
                    digest_verified = True

                if not verify_bundle_signature(
                    bundle_path=downloaded["bundle.json"],
                    signature_path=downloaded["bundle.sig"],
                    public_key_path=downloaded["release-evidence-public.pem"],
                ):
                    errors.append("bundle signature verification failed")
                else:
                    signature_verified = True

                metadata = _load_metadata(downloaded["release-evidence-metadata.json"])
                metadata_errors = _validate_metadata_consistency(metadata)
                if metadata_errors:
                    errors.extend(metadata_errors)
                else:
                    metadata_valid = True
        except RuntimeError as exc:
            errors.append(str(exc))

    return EvidenceContractResult(
        tag_name=release.tag_name,
        url=release.url,
        status="pass" if not errors else "fail",
        missing_assets=missing_assets,
        digest_verified=digest_verified,
        signature_verified=signature_verified,
        metadata_valid=metadata_valid,
        legacy_gap_applied=legacy_gap_applied,
        errors=errors,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate release evidence contract (assets + metadata + digest/signature parity)"
        )
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="owner/repo (defaults to GITHUB_REPOSITORY env var)",
    )
    parser.add_argument("--tag", default="")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--latest-count", type=int, default=0)
    parser.add_argument("--allow-legacy-before-tag", default="v0.3.0")
    parser.add_argument("--json-report", default="")
    parser.add_argument("--gh-retries", type=int, default=3)
    parser.add_argument("--gh-retry-backoff-s", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    repo = args.repo.strip()
    if repo == "":
        raise SystemExit("repo must be non-empty")

    payloads = fetch_release_payloads(
        repo=repo,
        tag=args.tag,
        latest=bool(args.latest),
        latest_count=max(args.latest_count, 0),
        gh_retries=max(args.gh_retries, 1),
        gh_retry_backoff_s=args.gh_retry_backoff_s,
    )
    if not payloads:
        raise SystemExit("no releases found for requested selector")

    github_token = os.environ.get("GH_TOKEN", "").strip() or None
    results = [
        validate_release_evidence_contract(
            payload=payload,
            allow_legacy_before_tag=args.allow_legacy_before_tag,
            github_token=github_token,
        )
        for payload in payloads
    ]

    for result in results:
        print(f"[{result.status.upper()}] {result.tag_name} :: {result.url}")
        if result.digest_verified:
            print("  - bundle SHA-256 verified")
        if result.signature_verified:
            print("  - bundle signature verified")
        if result.metadata_valid:
            print("  - metadata contract verified")
        if result.legacy_gap_applied:
            print("  - legacy gap applied")
        for error in result.errors:
            print(f"  - {error}")

    report_path_raw = args.json_report.strip()
    if report_path_raw:
        report_payload = {
            "repository": repo,
            "checked_at": datetime.now(UTC).isoformat(),
            "total_releases": len(results),
            "failed_releases": sum(1 for item in results if item.status != "pass"),
            "releases": [
                {
                    "tag_name": item.tag_name,
                    "url": item.url,
                    "status": item.status,
                    "missing_assets": item.missing_assets,
                    "digest_verified": item.digest_verified,
                    "signature_verified": item.signature_verified,
                    "metadata_valid": item.metadata_valid,
                    "legacy_gap_applied": item.legacy_gap_applied,
                    "errors": item.errors,
                }
                for item in results
            ],
        }
        report_path = Path(report_path_raw)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")
        print(f"JSON report written: {report_path}")

    failed = [item for item in results if item.status != "pass"]
    if failed:
        raise SystemExit(
            "release evidence contract check failed for "
            f"{len(failed)}/{len(results)} release(s)"
        )


if __name__ == "__main__":
    main()
