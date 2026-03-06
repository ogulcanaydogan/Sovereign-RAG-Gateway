import pytest

import scripts.check_ga_release_gate as ga_gate
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


def test_main_prerelease_tag_bypasses_same_commit_gate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        ga_gate,
        "resolve_tag_commit_sha",
        lambda **_: (_ for _ in ()).throw(AssertionError("must not resolve commit")),
    )
    monkeypatch.setattr(
        ga_gate,
        "_run_gh_json",
        lambda *_, **__: (_ for _ in ()).throw(AssertionError("must not call gh api")),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_ga_release_gate.py",
            "--repo",
            "org/repo",
            "--tag",
            "v0.8.0-alpha.1",
        ],
    )

    ga_gate.main()
    captured = capsys.readouterr()
    assert "GA gate bypassed for prerelease tag" in captured.out


def test_main_ga_tag_fails_when_same_commit_success_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ga_gate, "resolve_tag_commit_sha", lambda **_: "sha123")
    monkeypatch.setattr(
        ga_gate,
        "_run_gh_json",
        lambda *_, **__: {"workflow_runs": []},
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_ga_release_gate.py",
            "--repo",
            "org/repo",
            "--tag",
            "v0.8.0",
        ],
    )

    with pytest.raises(SystemExit, match="GA release gate failed"):
        ga_gate.main()


def test_main_ga_tag_passes_when_same_commit_success_exists(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(ga_gate, "resolve_tag_commit_sha", lambda **_: "sha123")
    monkeypatch.setattr(
        ga_gate,
        "_run_gh_json",
        lambda *_, **__: {
            "workflow_runs": [
                {
                    "name": "release-verify",
                    "path": ".github/workflows/release-verify.yml",
                    "conclusion": "success",
                    "id": 99,
                    "html_url": "https://example.test/runs/99",
                }
            ]
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_ga_release_gate.py",
            "--repo",
            "org/repo",
            "--tag",
            "v0.8.0",
            "--required-workflow",
            "release-verify",
        ],
    )

    ga_gate.main()
    captured = capsys.readouterr()
    assert "GA release gate passed" in captured.out
