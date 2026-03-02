#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
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

    if args.verify_bundle_integrity or args.verify_signature:
        required_downloads = {"bundle.json", "bundle.sha256"}
        if args.verify_signature:
            required_downloads.add("bundle.sig")
            if args.require_public_key or args.public_key_asset in result.assets_present:
                required_downloads.add(args.public_key_asset)

        with TemporaryDirectory(prefix="srg-release-verify-") as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            downloaded = download_assets(
                result=result,
                asset_names=required_downloads,
                out_dir=tmp_dir,
                github_token=os.environ.get("GH_TOKEN", "").strip() or None,
                timeout_s=args.download_timeout_s,
            )

            digest_ok, expected_digest, actual_digest, legacy_mode = verify_bundle_sha256(
                bundle_path=downloaded["bundle.json"],
                digest_path=downloaded["bundle.sha256"],
            )
            if not digest_ok:
                raise SystemExit(
                    "bundle SHA-256 mismatch: "
                    f"expected={expected_digest} actual={actual_digest}"
                )
            if legacy_mode:
                print(
                    "bundle SHA-256 verification OK (legacy newline-compat mode): "
                    f"{actual_digest}"
                )
            else:
                print(f"bundle SHA-256 verification OK: {actual_digest}")

            if args.verify_signature:
                if args.public_key_asset not in downloaded:
                    if args.require_public_key:
                        raise SystemExit(
                            "signature verification requested but public key asset is missing: "
                            f"{args.public_key_asset}"
                        )
                    print(
                        "signature verification skipped: missing public key asset "
                        f"'{args.public_key_asset}'"
                    )
                else:
                    signature_ok = verify_bundle_signature(
                        bundle_path=downloaded["bundle.json"],
                        signature_path=downloaded["bundle.sig"],
                        public_key_path=downloaded[args.public_key_asset],
                    )
                    if not signature_ok:
                        raise SystemExit("bundle signature verification failed")
                    print("bundle signature verification OK")


if __name__ == "__main__":
    main()
