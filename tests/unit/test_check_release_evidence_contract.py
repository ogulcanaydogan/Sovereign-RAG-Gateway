from __future__ import annotations

import json
from pathlib import Path

import scripts.check_release_evidence_contract as contract


def _release_payload(
    *,
    tag: str = "v0.7.0",
    assets: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "tag_name": tag,
        "html_url": f"https://example.test/{tag}",
        "prerelease": "-" in tag,
        "draft": False,
        "assets": assets
        if assets is not None
        else [
            {"name": "bundle.json", "browser_download_url": "https://example.test/bundle.json"},
            {
                "name": "bundle.sha256",
                "browser_download_url": "https://example.test/bundle.sha256",
            },
            {"name": "bundle.sig", "browser_download_url": "https://example.test/bundle.sig"},
            {
                "name": "release-evidence-public.pem",
                "browser_download_url": "https://example.test/release-evidence-public.pem",
            },
            {
                "name": "release-evidence-metadata.json",
                "browser_download_url": "https://example.test/release-evidence-metadata.json",
            },
        ],
    }


def test_validate_metadata_consistency_passes() -> None:
    metadata = {
        "bundle_path": "artifacts/release-evidence/bundle.json",
        "bundle_sha256_path": "artifacts/release-evidence/bundle.sha256",
        "bundle_signature_path": "artifacts/release-evidence/bundle.sig",
        "public_key_path": "artifacts/release-evidence/release-evidence-public.pem",
        "public_key_asset": "release-evidence-public.pem",
    }

    errors = contract._validate_metadata_consistency(metadata)
    assert errors == []


def test_validate_metadata_consistency_fails_on_wrong_names() -> None:
    metadata = {
        "bundle_path": "bundle.txt",
        "bundle_sha256_path": "digest.sha1",
        "bundle_signature_path": "sig.txt",
        "public_key_path": "public.pem",
        "public_key_asset": "public.pem",
    }

    errors = contract._validate_metadata_consistency(metadata)
    assert len(errors) == 5


def test_validate_release_evidence_contract_passes(monkeypatch, tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    digest = tmp_path / "bundle.sha256"
    signature = tmp_path / "bundle.sig"
    public_key = tmp_path / "release-evidence-public.pem"
    metadata_path = tmp_path / "release-evidence-metadata.json"

    bundle.write_text('{"ok":true}\n', encoding="utf-8")
    digest.write_text("a" * 64 + "\n", encoding="utf-8")
    signature.write_bytes(b"sig")
    public_key.write_text("pem", encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                "bundle_path": "release-evidence/bundle.json",
                "bundle_sha256_path": "release-evidence/bundle.sha256",
                "bundle_signature_path": "release-evidence/bundle.sig",
                "public_key_path": "release-evidence/release-evidence-public.pem",
                "public_key_asset": "release-evidence-public.pem",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        contract,
        "download_assets",
        lambda **_: {
            "bundle.json": bundle,
            "bundle.sha256": digest,
            "bundle.sig": signature,
            "release-evidence-public.pem": public_key,
            "release-evidence-metadata.json": metadata_path,
        },
    )
    monkeypatch.setattr(contract, "verify_bundle_sha256", lambda **_: (True, "x", "x", False))
    monkeypatch.setattr(contract, "verify_bundle_signature", lambda **_: True)

    result = contract.validate_release_evidence_contract(
        payload=_release_payload(),
        allow_legacy_before_tag="v0.3.0",
        github_token=None,
    )
    assert result.status == "pass"
    assert result.digest_verified is True
    assert result.signature_verified is True
    assert result.metadata_valid is True


def test_validate_release_evidence_contract_legacy_gap(monkeypatch) -> None:
    payload = _release_payload(
        tag="v0.2.0",
        assets=[{"name": "bundle.json", "browser_download_url": "https://example.test/bundle.json"}],
    )

    monkeypatch.setattr(
        contract,
        "download_assets",
        lambda **_: (_ for _ in ()).throw(AssertionError("must not download on legacy gap")),
    )

    result = contract.validate_release_evidence_contract(
        payload=payload,
        allow_legacy_before_tag="v0.3.0",
        github_token=None,
    )
    assert result.status == "pass"
    assert result.legacy_gap_applied is True


def test_validate_release_evidence_contract_fails_on_digest(monkeypatch, tmp_path: Path) -> None:
    metadata_path = tmp_path / "release-evidence-metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "bundle_path": "release-evidence/bundle.json",
                "bundle_sha256_path": "release-evidence/bundle.sha256",
                "bundle_signature_path": "release-evidence/bundle.sig",
                "public_key_path": "release-evidence/release-evidence-public.pem",
                "public_key_asset": "release-evidence-public.pem",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        contract,
        "download_assets",
        lambda **_: {
            "bundle.json": tmp_path / "bundle.json",
            "bundle.sha256": tmp_path / "bundle.sha256",
            "bundle.sig": tmp_path / "bundle.sig",
            "release-evidence-public.pem": tmp_path / "release-evidence-public.pem",
            "release-evidence-metadata.json": metadata_path,
        },
    )
    monkeypatch.setattr(contract, "verify_bundle_sha256", lambda **_: (False, "e", "a", False))
    monkeypatch.setattr(contract, "verify_bundle_signature", lambda **_: True)

    result = contract.validate_release_evidence_contract(
        payload=_release_payload(),
        allow_legacy_before_tag="v0.3.0",
        github_token=None,
    )

    assert result.status == "fail"
    assert any("SHA-256 mismatch" in item for item in result.errors)
