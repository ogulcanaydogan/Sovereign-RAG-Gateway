import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

from scripts.check_release_assets import (
    ReleaseAssetCheck,
    check_release_payload,
    parse_expected_assets,
    verify_bundle_sha256,
    verify_bundle_signature,
)


def _payload(*, prerelease: bool = False, draft: bool = False) -> dict[str, object]:
    return {
        "tag_name": "v0.6.0",
        "html_url": "https://example.test/release/v0.6.0",
        "prerelease": prerelease,
        "draft": draft,
        "assets": [
            {
                "name": "bundle.json",
                "browser_download_url": "https://example.test/bundle.json",
            },
            {
                "name": "bundle.md",
                "browser_download_url": "https://example.test/bundle.md",
            },
            {
                "name": "bundle.sha256",
                "browser_download_url": "https://example.test/bundle.sha256",
            },
            {
                "name": "bundle.sig",
                "browser_download_url": "https://example.test/bundle.sig",
            },
            {
                "name": "events.jsonl",
                "browser_download_url": "https://example.test/events.jsonl",
            },
            {
                "name": "release-evidence-metadata.json",
                "browser_download_url": "https://example.test/release-evidence-metadata.json",
            },
            {
                "name": "sbom.spdx.json",
                "browser_download_url": "https://example.test/sbom.spdx.json",
            },
        ],
    }


def test_parse_expected_assets_comma_separated() -> None:
    values = parse_expected_assets(" a, b ,c ")
    assert values == {"a", "b", "c"}


def test_check_release_payload_success() -> None:
    expected = {
        "bundle.json",
        "bundle.md",
        "bundle.sha256",
        "bundle.sig",
        "events.jsonl",
        "release-evidence-metadata.json",
        "sbom.spdx.json",
    }
    result = check_release_payload(_payload(), expected_assets=expected)

    assert isinstance(result, ReleaseAssetCheck)
    assert result.tag_name == "v0.6.0"
    assert result.prerelease is False
    assert result.draft is False
    assert result.missing_assets == set()
    assert (
        result.asset_download_urls["bundle.json"]
        == "https://example.test/bundle.json"
    )


def test_check_release_payload_missing_assets_detected() -> None:
    payload = _payload()
    payload["assets"] = [{"name": "bundle.json"}]

    result = check_release_payload(
        payload,
        expected_assets={"bundle.json", "sbom.spdx.json"},
    )
    assert result.missing_assets == {"sbom.spdx.json"}


def test_check_release_payload_rejects_invalid_shape() -> None:
    with pytest.raises(ValueError, match="tag_name"):
        check_release_payload({"assets": []}, expected_assets={"bundle.json"})


def test_verify_bundle_sha256_ok(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text('{"ok":true}', encoding="utf-8")
    expected = sha256(bundle_path.read_bytes()).hexdigest()
    digest_path = tmp_path / "bundle.sha256"
    digest_path.write_text(expected + "\n", encoding="utf-8")

    valid, expected_hash, actual_hash, legacy_mode = verify_bundle_sha256(
        bundle_path, digest_path
    )
    assert valid is True
    assert legacy_mode is False
    assert expected_hash == actual_hash


def test_verify_bundle_sha256_mismatch(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text('{"ok":false}', encoding="utf-8")
    digest_path = tmp_path / "bundle.sha256"
    digest_path.write_text("0" * 64 + "\n", encoding="utf-8")

    valid, expected_hash, actual_hash, legacy_mode = verify_bundle_sha256(
        bundle_path, digest_path
    )
    assert valid is False
    assert legacy_mode is False
    assert expected_hash != actual_hash


def test_verify_bundle_sha256_legacy_newline_compat(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    payload = '{"ok":"legacy"}\n'
    bundle_path.write_text(payload, encoding="utf-8")
    expected = sha256(payload.rstrip("\n").encode("utf-8")).hexdigest()
    digest_path = tmp_path / "bundle.sha256"
    digest_path.write_text(expected + "\n", encoding="utf-8")

    valid, expected_hash, actual_hash, legacy_mode = verify_bundle_sha256(
        bundle_path, digest_path
    )
    assert valid is True
    assert legacy_mode is True
    assert expected_hash == actual_hash


def test_verify_bundle_signature_ok(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text('{"message":"signed"}\n', encoding="utf-8")
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    signature = tmp_path / "bundle.sig"

    subprocess.run(
        ["openssl", "genrsa", "-out", str(private_key), "2048"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["openssl", "rsa", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(private_key),
            "-out",
            str(signature),
            str(bundle_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert verify_bundle_signature(bundle_path, signature, public_key) is True


def test_verify_bundle_signature_tampered_bundle_fails(tmp_path: Path) -> None:
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text('{"message":"signed"}\n', encoding="utf-8")
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    signature = tmp_path / "bundle.sig"

    subprocess.run(
        ["openssl", "genrsa", "-out", str(private_key), "2048"],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["openssl", "rsa", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(private_key),
            "-out",
            str(signature),
            str(bundle_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    bundle_path.write_text('{"message":"tampered"}\n', encoding="utf-8")
    assert verify_bundle_signature(bundle_path, signature, public_key) is False
