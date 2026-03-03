#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
from urllib.request import Request, urlopen

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
    asset_download_urls: dict[str, str]
    expected_assets: set[str]

    @property
    def missing_assets(self) -> set[str]:
        return self.expected_assets.difference(self.assets_present)


@dataclass(frozen=True)
class ReleaseValidationResult:
    tag_name: str
    url: str
    draft: bool
    prerelease: bool
    missing_assets: list[str]
    integrity_verified: bool
    signature_verified: bool
    legacy_digest_mode: bool
    prerelease_parity_expected: bool | None
    prerelease_parity_actual: bool | None
    legacy_gap_applied: bool
    errors: list[str]

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0


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


def _extract_assets(payload: object) -> tuple[set[str], dict[str, str]]:
    if not isinstance(payload, dict):
        raise ValueError("release payload must be a JSON object")
    raw_assets = payload.get("assets", [])
    if not isinstance(raw_assets, list):
        raise ValueError("release payload assets must be a list")

    assets: set[str] = set()
    asset_download_urls: dict[str, str] = {}
    for item in raw_assets:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        download_url = str(item.get("browser_download_url", "")).strip()
        if name:
            assets.add(name)
            if download_url:
                asset_download_urls[name] = download_url
    return assets, asset_download_urls


def check_release_payload(payload: object, expected_assets: set[str]) -> ReleaseAssetCheck:
    if not isinstance(payload, dict):
        raise ValueError("release payload must be a JSON object")

    tag_name = str(payload.get("tag_name", "")).strip()
    if tag_name == "":
        raise ValueError("release payload missing tag_name")
    url = str(payload.get("html_url", "")).strip()
    draft = bool(payload.get("draft", False))
    prerelease = bool(payload.get("prerelease", False))

    assets, asset_download_urls = _extract_assets(payload)
    return ReleaseAssetCheck(
        tag_name=tag_name,
        url=url,
        draft=draft,
        prerelease=prerelease,
        assets_present=assets,
        asset_download_urls=asset_download_urls,
        expected_assets=expected_assets,
    )


def fetch_release_payloads(
    repo: str,
    tag: str,
    latest: bool,
    latest_count: int,
    gh_retries: int,
    gh_retry_backoff_s: float,
) -> list[object]:
    normalized_repo = repo.strip()
    if normalized_repo == "":
        raise ValueError("repo must be non-empty")

    modes = int(bool(tag.strip())) + int(bool(latest)) + int(latest_count > 0)
    if modes != 1:
        raise ValueError("exactly one of --tag, --latest, or --latest-count must be set")

    if latest_count > 0:
        payload = _run_gh_json(
            f"repos/{normalized_repo}/releases?per_page={latest_count}",
            retries=gh_retries,
            retry_backoff_s=gh_retry_backoff_s,
        )
        if not isinstance(payload, list):
            raise RuntimeError("unexpected release list payload from gh api")
        return payload

    if latest:
        payload = _run_gh_json(
            f"repos/{normalized_repo}/releases?per_page=1",
            retries=gh_retries,
            retry_backoff_s=gh_retry_backoff_s,
        )
        if not isinstance(payload, list) or len(payload) == 0:
            raise RuntimeError("no releases found for repository")
        return [payload[0]]

    normalized_tag = tag.strip()
    payload = _run_gh_json(
        f"repos/{normalized_repo}/releases/tags/{normalized_tag}",
        retries=gh_retries,
        retry_backoff_s=gh_retry_backoff_s,
    )
    return [payload]


def parse_expected_assets(raw: str) -> set[str]:
    values = {item.strip() for item in raw.split(",") if item.strip()}
    if not values:
        raise ValueError("expected assets set cannot be empty")
    return values


def _is_prerelease_tag(tag_name: str) -> bool:
    normalized = tag_name.strip().lstrip("v")
    return "-" in normalized


def _parse_semver_tag(tag_name: str) -> tuple[int, int, int, list[str]]:
    normalized = tag_name.strip().lstrip("v")
    if normalized == "":
        raise ValueError("empty tag")
    main_part, sep, prerelease_part = normalized.partition("-")
    main_parts = main_part.split(".")
    if len(main_parts) != 3:
        raise ValueError(f"invalid semver tag: {tag_name}")
    major = int(main_parts[0])
    minor = int(main_parts[1])
    patch = int(main_parts[2])
    prerelease_items = prerelease_part.split(".") if sep else []
    return major, minor, patch, prerelease_items


def _compare_ident(left: str, right: str) -> int:
    left_is_num = left.isdigit()
    right_is_num = right.isdigit()
    if left_is_num and right_is_num:
        left_num = int(left)
        right_num = int(right)
        if left_num < right_num:
            return -1
        if left_num > right_num:
            return 1
        return 0
    if left_is_num and not right_is_num:
        return -1
    if not left_is_num and right_is_num:
        return 1
    if left < right:
        return -1
    if left > right:
        return 1
    return 0


def compare_semver_tags(left_tag: str, right_tag: str) -> int:
    left_major, left_minor, left_patch, left_pre = _parse_semver_tag(left_tag)
    right_major, right_minor, right_patch, right_pre = _parse_semver_tag(right_tag)

    if left_major != right_major:
        return -1 if left_major < right_major else 1
    if left_minor != right_minor:
        return -1 if left_minor < right_minor else 1
    if left_patch != right_patch:
        return -1 if left_patch < right_patch else 1

    if not left_pre and not right_pre:
        return 0
    if not left_pre and right_pre:
        return 1
    if left_pre and not right_pre:
        return -1

    for left_item, right_item in zip(left_pre, right_pre, strict=False):
        cmp = _compare_ident(left_item, right_item)
        if cmp != 0:
            return cmp
    if len(left_pre) < len(right_pre):
        return -1
    if len(left_pre) > len(right_pre):
        return 1
    return 0


def _is_before_tag(tag_name: str, threshold_tag: str) -> bool:
    return compare_semver_tags(tag_name, threshold_tag) < 0


def _download_asset(
    url: str,
    dest: Path,
    github_token: str | None,
    timeout_s: float,
) -> None:
    headers = {
        "Accept": "application/octet-stream",
        "User-Agent": "srg-release-verify",
    }
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=max(timeout_s, 1.0)) as response:
        payload = response.read()
    dest.write_bytes(payload)


def download_assets(
    result: ReleaseAssetCheck,
    asset_names: set[str],
    out_dir: Path,
    github_token: str | None,
    timeout_s: float,
) -> dict[str, Path]:
    missing = sorted(asset_names.difference(result.assets_present))
    if missing:
        raise RuntimeError("missing required downloadable assets: " + ", ".join(missing))

    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded: dict[str, Path] = {}
    for name in sorted(asset_names):
        download_url = result.asset_download_urls.get(name, "").strip()
        if download_url == "":
            raise RuntimeError(f"release asset '{name}' missing download URL")
        destination = out_dir / name
        _download_asset(
            url=download_url,
            dest=destination,
            github_token=github_token,
            timeout_s=timeout_s,
        )
        downloaded[name] = destination
    return downloaded


def _read_sha256(path: Path) -> str:
    parts = path.read_text(encoding="utf-8").strip().split()
    if not parts:
        raise RuntimeError(f"empty SHA-256 file: {path}")
    token = parts[0]
    if len(token) != 64 or any(c not in "0123456789abcdefABCDEF" for c in token):
        raise RuntimeError(f"invalid SHA-256 file format: {path}")
    return token.lower()


def verify_bundle_sha256(bundle_path: Path, digest_path: Path) -> tuple[bool, str, str, bool]:
    expected = _read_sha256(digest_path)
    bundle_bytes = bundle_path.read_bytes()
    actual = sha256(bundle_bytes).hexdigest()
    if expected == actual:
        return True, expected, actual, False

    # Backward compatibility for older releases where digest excluded final newline.
    if bundle_bytes.endswith(b"\n"):
        legacy_actual = sha256(bundle_bytes[:-1]).hexdigest()
        if expected == legacy_actual:
            return True, expected, legacy_actual, True

    return False, expected, actual, False


def verify_bundle_signature(
    bundle_path: Path,
    signature_path: Path,
    public_key_path: Path,
) -> bool:
    result = subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-verify",
            str(public_key_path),
            "-signature",
            str(signature_path),
            str(bundle_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    combined = f"{result.stdout}\n{result.stderr}".lower()
    return "verified ok" in combined


def _validate_release(
    release: ReleaseAssetCheck,
    *,
    prerelease_mode: str,
    allow_draft: bool,
    verify_bundle_integrity: bool,
    verify_signature: bool,
    public_key_asset: str,
    require_public_key: bool,
    download_timeout_s: float,
    enforce_prerelease_flag_parity: bool,
    allow_legacy_evidence_gap_before_tag: str,
    allow_legacy_public_key_gap_before_tag: str,
    github_token: str | None,
) -> ReleaseValidationResult:
    errors: list[str] = []
    integrity_verified = False
    signature_verified = False
    legacy_digest_mode = False
    parity_expected: bool | None = None
    legacy_gap_applied = False
    legacy_evidence_gap_enabled = (
        bool(allow_legacy_evidence_gap_before_tag)
        and _is_before_tag(release.tag_name, allow_legacy_evidence_gap_before_tag)
    )
    legacy_public_key_gap_enabled = (
        bool(allow_legacy_public_key_gap_before_tag)
        and _is_before_tag(release.tag_name, allow_legacy_public_key_gap_before_tag)
    )

    if not allow_draft and release.draft:
        errors.append(f"release {release.tag_name} is draft")

    if prerelease_mode == "true" and not release.prerelease:
        errors.append(f"release {release.tag_name} must be prerelease=true")
    if prerelease_mode == "false" and release.prerelease:
        errors.append(f"release {release.tag_name} must be prerelease=false")

    missing_assets = sorted(release.missing_assets)
    if missing_assets:
        if legacy_evidence_gap_enabled:
            legacy_gap_applied = True
        else:
            errors.append("missing required release assets: " + ", ".join(missing_assets))

    if enforce_prerelease_flag_parity:
        parity_expected = _is_prerelease_tag(release.tag_name)
        if release.prerelease != parity_expected:
            errors.append(
                "prerelease flag parity mismatch: "
                f"tag={release.tag_name} expected={parity_expected} actual={release.prerelease}"
            )

    do_integrity_verification = verify_bundle_integrity
    integrity_base_assets = {"bundle.json", "bundle.sha256"}
    missing_integrity_assets = sorted(integrity_base_assets.difference(release.assets_present))
    if do_integrity_verification and missing_integrity_assets:
        if legacy_evidence_gap_enabled:
            legacy_gap_applied = True
            do_integrity_verification = False
        else:
            errors.append(
                "missing required downloadable assets: " + ", ".join(missing_integrity_assets)
            )

    do_signature_verification = verify_signature
    signature_base_assets = {"bundle.json", "bundle.sig"}
    missing_signature_assets = sorted(signature_base_assets.difference(release.assets_present))
    if do_signature_verification and missing_signature_assets:
        if legacy_evidence_gap_enabled:
            legacy_gap_applied = True
            do_signature_verification = False
        else:
            errors.append(
                "missing required downloadable assets: " + ", ".join(missing_signature_assets)
            )

    if do_signature_verification and public_key_asset not in release.assets_present:
        if require_public_key:
            if legacy_public_key_gap_enabled:
                legacy_gap_applied = True
                do_signature_verification = False
            else:
                errors.append(
                    "signature verification requested but public key asset is missing: "
                    f"{public_key_asset}"
                )
        else:
            do_signature_verification = False

    if do_integrity_verification or do_signature_verification:
        required_downloads = set()
        if do_integrity_verification:
            required_downloads.update(integrity_base_assets)
        if do_signature_verification:
            required_downloads.update(signature_base_assets)
            required_downloads.add(public_key_asset)
        try:
            with TemporaryDirectory(
                prefix=f"srg-release-verify-{release.tag_name}-"
            ) as tmp_dir_name:
                downloaded = download_assets(
                    result=release,
                    asset_names=required_downloads,
                    out_dir=Path(tmp_dir_name),
                    github_token=github_token,
                    timeout_s=download_timeout_s,
                )

                digest_ok, expected_digest, actual_digest, legacy_mode = verify_bundle_sha256(
                    bundle_path=downloaded["bundle.json"],
                    digest_path=downloaded["bundle.sha256"],
                )
                if do_integrity_verification:
                    if not digest_ok:
                        errors.append(
                            "bundle SHA-256 mismatch: "
                            f"expected={expected_digest} actual={actual_digest}"
                        )
                    else:
                        integrity_verified = True
                        legacy_digest_mode = legacy_mode

                if do_signature_verification:
                    signature_ok = verify_bundle_signature(
                        bundle_path=downloaded["bundle.json"],
                        signature_path=downloaded["bundle.sig"],
                        public_key_path=downloaded[public_key_asset],
                    )
                    if not signature_ok:
                        errors.append("bundle signature verification failed")
                    else:
                        signature_verified = True
        except RuntimeError as exc:
            errors.append(str(exc))

    return ReleaseValidationResult(
        tag_name=release.tag_name,
        url=release.url,
        draft=release.draft,
        prerelease=release.prerelease,
        missing_assets=missing_assets,
        integrity_verified=integrity_verified,
        signature_verified=signature_verified,
        legacy_digest_mode=legacy_digest_mode,
        prerelease_parity_expected=parity_expected,
        prerelease_parity_actual=release.prerelease if parity_expected is not None else None,
        legacy_gap_applied=legacy_gap_applied,
        errors=errors,
    )


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
        "--latest-count",
        type=int,
        default=0,
        help="validate the latest N releases",
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
        "--enforce-prerelease-flag-parity",
        action="store_true",
        help="enforce prerelease flag parity with semver tag suffix",
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
    parser.add_argument(
        "--verify-bundle-integrity",
        action="store_true",
        help="download bundle assets and verify bundle.sha256 against bundle.json",
    )
    parser.add_argument(
        "--verify-signature",
        action="store_true",
        help="verify bundle.sig against bundle.json using release public key asset",
    )
    parser.add_argument(
        "--public-key-asset",
        default="release-evidence-public.pem",
        help="release asset name containing PEM public key for signature verification",
    )
    parser.add_argument(
        "--require-public-key",
        action="store_true",
        help="fail if signature verification is requested but public key asset is missing",
    )
    parser.add_argument(
        "--download-timeout-s",
        type=float,
        default=30.0,
        help="HTTP timeout for release asset downloads",
    )
    parser.add_argument(
        "--allow-legacy-evidence-gap-before-tag",
        default="",
        help="allow missing required evidence assets for tags older than this threshold",
    )
    parser.add_argument(
        "--allow-legacy-public-key-gap-before-tag",
        default="",
        help="allow missing public key asset for tags older than this threshold",
    )
    parser.add_argument(
        "--json-report",
        default="",
        help="optional JSON report output path",
    )
    args = parser.parse_args()

    expected_assets = parse_expected_assets(args.expected_assets)
    payloads = fetch_release_payloads(
        repo=args.repo,
        tag=args.tag,
        latest=args.latest,
        latest_count=max(args.latest_count, 0),
        gh_retries=max(args.gh_retries, 1),
        gh_retry_backoff_s=args.gh_retry_backoff_s,
    )

    if not payloads:
        raise SystemExit("no releases found for requested selector")

    validations: list[ReleaseValidationResult] = []
    github_token = os.environ.get("GH_TOKEN", "").strip() or None

    for payload in payloads:
        release = check_release_payload(payload=payload, expected_assets=expected_assets)
        validation = _validate_release(
            release,
            prerelease_mode=args.prerelease_mode,
            allow_draft=args.allow_draft,
            verify_bundle_integrity=args.verify_bundle_integrity,
            verify_signature=args.verify_signature,
            public_key_asset=args.public_key_asset,
            require_public_key=args.require_public_key,
            download_timeout_s=args.download_timeout_s,
            enforce_prerelease_flag_parity=args.enforce_prerelease_flag_parity,
            allow_legacy_evidence_gap_before_tag=args.allow_legacy_evidence_gap_before_tag,
            allow_legacy_public_key_gap_before_tag=args.allow_legacy_public_key_gap_before_tag,
            github_token=github_token,
        )
        validations.append(validation)

    for validation in validations:
        status = "OK" if validation.passed else "FAIL"
        print(f"[{status}] {validation.tag_name} :: {validation.url}")
        if validation.integrity_verified:
            if validation.legacy_digest_mode:
                print("  - bundle SHA-256 verified (legacy newline-compat mode)")
            else:
                print("  - bundle SHA-256 verified")
        if validation.signature_verified:
            print("  - bundle signature verified")
        if validation.legacy_gap_applied:
            print("  - legacy compatibility gap applied")
        if validation.errors:
            for err in validation.errors:
                print(f"  - {err}")

    report_path = args.json_report.strip()
    if report_path:
        report_payload = {
            "repository": args.repo,
            "checked_at": datetime.now(UTC).isoformat(),
            "total_releases": len(validations),
            "failed_releases": sum(1 for item in validations if not item.passed),
            "releases": [
                {
                    "tag_name": item.tag_name,
                    "url": item.url,
                    "draft": item.draft,
                    "prerelease": item.prerelease,
                    "status": "pass" if item.passed else "fail",
                    "missing_assets": item.missing_assets,
                    "integrity_verified": item.integrity_verified,
                    "signature_verified": item.signature_verified,
                    "legacy_digest_mode": item.legacy_digest_mode,
                    "legacy_gap_applied": item.legacy_gap_applied,
                    "prerelease_parity_expected": item.prerelease_parity_expected,
                    "prerelease_parity_actual": item.prerelease_parity_actual,
                    "errors": item.errors,
                }
                for item in validations
            ],
        }
        output_path = Path(report_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")
        print(f"JSON report written: {output_path}")

    failures = [item for item in validations if not item.passed]
    if failures:
        raise SystemExit(
            "release verification failed for "
            f"{len(failures)}/{len(validations)} release(s)"
        )


if __name__ == "__main__":
    main()
