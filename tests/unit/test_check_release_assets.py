import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

import scripts.check_release_assets as release_assets
from scripts.check_release_assets import (
    ReleaseAssetCheck,
    _validate_release,
    check_release_payload,
    compare_semver_tags,
    fetch_release_payloads,
    parse_expected_assets,
    verify_bundle_sha256,
    verify_bundle_signature,
)


def _payload(
    *,
    prerelease: bool = False,
    draft: bool = False,
    tag_name: str = "v0.6.0",
) -> dict[str, object]:
    return {
        "tag_name": tag_name,
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


def test_fetch_release_payloads_latest_count(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_payload = [
        {"tag_name": "v0.7.0-alpha.1"},
        {"tag_name": "v0.6.0"},
    ]

    def _fake_run(path: str, retries: int, retry_backoff_s: float) -> object:
        assert "releases?per_page=2" in path
        assert retries == 3
        assert retry_backoff_s == 1.0
        return expected_payload

    monkeypatch.setattr(release_assets, "_run_gh_json", _fake_run)
    payloads = fetch_release_payloads(
        repo="org/repo",
        tag="",
        latest=False,
        latest_count=2,
        gh_retries=3,
        gh_retry_backoff_s=1.0,
    )
    assert payloads == expected_payload


def test_fetch_release_payloads_requires_single_selector() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        fetch_release_payloads(
            repo="org/repo",
            tag="v0.6.0",
            latest=True,
            latest_count=0,
            gh_retries=1,
            gh_retry_backoff_s=0.0,
        )


def test_validate_release_prerelease_parity_mismatch() -> None:
    release = check_release_payload(
        _payload(tag_name="v0.7.0-alpha.1", prerelease=False),
        expected_assets={"bundle.json"},
    )
    result = _validate_release(
        release,
        prerelease_mode="any",
        allow_draft=True,
        verify_bundle_integrity=False,
        verify_signature=False,
        public_key_asset="release-evidence-public.pem",
        require_public_key=False,
        download_timeout_s=1.0,
        enforce_prerelease_flag_parity=True,
        allow_legacy_evidence_gap_before_tag="",
        allow_legacy_public_key_gap_before_tag="",
        github_token=None,
    )
    assert result.passed is False
    assert any("prerelease flag parity mismatch" in err for err in result.errors)


def test_compare_semver_tags_orders_prerelease_before_ga() -> None:
    assert compare_semver_tags("v0.7.0-alpha.2", "v0.7.0") == -1
    assert compare_semver_tags("v0.7.0", "v0.7.0-alpha.2") == 1
    assert compare_semver_tags("v0.7.0-alpha.2", "v0.7.0-alpha.10") == -1


def test_validate_release_legacy_public_key_gap_allows_pass() -> None:
    release = check_release_payload(
        _payload(tag_name="v0.6.0"),
        expected_assets={"bundle.json", "bundle.sha256", "bundle.sig"},
    )
    result = _validate_release(
        release,
        prerelease_mode="any",
        allow_draft=True,
        verify_bundle_integrity=False,
        verify_signature=True,
        public_key_asset="release-evidence-public.pem",
        require_public_key=True,
        download_timeout_s=1.0,
        enforce_prerelease_flag_parity=False,
        allow_legacy_evidence_gap_before_tag="",
        allow_legacy_public_key_gap_before_tag="v0.7.0-alpha.1",
        github_token=None,
    )
    assert result.passed is True
    assert result.legacy_gap_applied is True
    assert result.signature_verified is False


def test_validate_release_public_key_missing_without_legacy_gap_fails() -> None:
    release = check_release_payload(
        _payload(tag_name="v0.6.0"),
        expected_assets={"bundle.json", "bundle.sha256", "bundle.sig"},
    )
    result = _validate_release(
        release,
        prerelease_mode="any",
        allow_draft=True,
        verify_bundle_integrity=False,
        verify_signature=True,
        public_key_asset="release-evidence-public.pem",
        require_public_key=True,
        download_timeout_s=1.0,
        enforce_prerelease_flag_parity=False,
        allow_legacy_evidence_gap_before_tag="",
        allow_legacy_public_key_gap_before_tag="",
        github_token=None,
    )
    assert result.passed is False
    assert any("public key asset is missing" in err for err in result.errors)


def test_validate_release_legacy_evidence_gap_skips_integrity_checks() -> None:
    payload = _payload(tag_name="v0.2.0")
    payload["assets"] = []
    release = check_release_payload(
        payload,
        expected_assets={
            "bundle.json",
            "bundle.sha256",
            "bundle.sig",
            "release-evidence-public.pem",
        },
    )
    result = _validate_release(
        release,
        prerelease_mode="any",
        allow_draft=True,
        verify_bundle_integrity=True,
        verify_signature=True,
        public_key_asset="release-evidence-public.pem",
        require_public_key=True,
        download_timeout_s=1.0,
        enforce_prerelease_flag_parity=False,
        allow_legacy_evidence_gap_before_tag="v0.3.0",
        allow_legacy_public_key_gap_before_tag="v0.7.0-alpha.1",
        github_token=None,
    )
    assert result.passed is True
    assert result.legacy_gap_applied is True
    assert result.integrity_verified is False
    assert result.signature_verified is False


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
