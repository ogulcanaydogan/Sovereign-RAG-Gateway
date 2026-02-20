import pytest

from scripts.check_release_assets import (
    ReleaseAssetCheck,
    check_release_payload,
    parse_expected_assets,
)


def _payload(*, prerelease: bool = False, draft: bool = False) -> dict[str, object]:
    return {
        "tag_name": "v0.6.0",
        "html_url": "https://example.test/release/v0.6.0",
        "prerelease": prerelease,
        "draft": draft,
        "assets": [
            {"name": "bundle.json"},
            {"name": "bundle.md"},
            {"name": "bundle.sha256"},
            {"name": "bundle.sig"},
            {"name": "events.jsonl"},
            {"name": "release-evidence-metadata.json"},
            {"name": "sbom.spdx.json"},
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
