import pytest

from scripts.check_ga_release_gate import (
    find_successful_required_run,
    is_prerelease_tag,
    resolve_tag_commit_sha_from_payloads,
)


def test_is_prerelease_tag() -> None:
    assert is_prerelease_tag("v0.7.0-alpha.2") is True
    assert is_prerelease_tag("v0.7.0") is False


def test_resolve_tag_commit_sha_from_lightweight_tag() -> None:
    ref_payload = {
        "object": {
            "type": "commit",
            "sha": "abc123",
        }
    }

    sha = resolve_tag_commit_sha_from_payloads(ref_payload, None)
    assert sha == "abc123"


def test_resolve_tag_commit_sha_from_annotated_tag() -> None:
    ref_payload = {
        "object": {
            "type": "tag",
            "sha": "tag-object-sha",
        }
    }
    annotated_payload = {
        "object": {
            "type": "commit",
            "sha": "commit-sha",
        }
    }

    sha = resolve_tag_commit_sha_from_payloads(ref_payload, annotated_payload)
    assert sha == "commit-sha"


def test_resolve_tag_commit_sha_rejects_invalid_payload() -> None:
    with pytest.raises(RuntimeError, match="invalid git ref payload"):
        resolve_tag_commit_sha_from_payloads([], None)


def test_find_successful_required_run_matches_name() -> None:
    payload = {
        "workflow_runs": [
            {
                "name": "release-verify",
                "path": ".github/workflows/release-verify.yml",
                "conclusion": "success",
                "id": 123,
                "html_url": "https://example.test/run/123",
            }
        ]
    }

    run = find_successful_required_run(payload, required_workflow="release-verify")
    assert run is not None
    assert run["id"] == 123


def test_find_successful_required_run_requires_success() -> None:
    payload = {
        "workflow_runs": [
            {
                "name": "release-verify",
                "path": ".github/workflows/release-verify.yml",
                "conclusion": "failure",
            }
        ]
    }

    run = find_successful_required_run(payload, required_workflow="release-verify")
    assert run is None
