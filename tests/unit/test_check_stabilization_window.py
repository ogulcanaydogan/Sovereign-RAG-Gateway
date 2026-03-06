from __future__ import annotations

from datetime import UTC, datetime

import pytest

import scripts.check_stabilization_window as stabilization
from scripts.check_stabilization_window import (
    _build_report_payload,
    _filter_window_runs,
    parse_required_counts,
)


def test_parse_required_counts_success() -> None:
    parsed = parse_required_counts("deploy-smoke=3,release-verify=2,ci=1")
    assert parsed == {"deploy-smoke": 3, "release-verify": 2, "ci": 1}


def test_parse_required_counts_rejects_invalid_item() -> None:
    with pytest.raises(ValueError, match="invalid required-counts entry"):
        parse_required_counts("deploy-smoke")


def test_filter_window_runs_counts_success_and_failure() -> None:
    window_start = datetime(2026, 3, 1, tzinfo=UTC)
    window_end = datetime(2026, 3, 8, tzinfo=UTC)

    payload = {
        "workflow_runs": [
            {"created_at": "2026-03-02T10:00:00Z", "conclusion": "success"},
            {"created_at": "2026-03-03T10:00:00Z", "conclusion": "failure"},
            {"created_at": "2026-02-20T10:00:00Z", "conclusion": "success"},
        ]
    }

    total, successes, failures = _filter_window_runs(payload, window_start, window_end)
    assert total == 2
    assert successes == 1
    assert failures == 1


def test_collect_window_stats_with_missing_workflow_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_resolve(*, repo: str, retries: int, retry_backoff_s: float) -> dict[str, int]:
        assert repo == "org/repo"
        assert retries == 2
        assert retry_backoff_s == 0.0
        return {"ci": 11}

    def _fake_run(path: str, retries: int, retry_backoff_s: float) -> object:
        assert "actions/workflows/11/runs" in path
        return {
            "workflow_runs": [
                {"created_at": "2026-03-01T10:00:00Z", "conclusion": "success"},
                {"created_at": "2026-03-01T12:00:00Z", "conclusion": "failure"},
            ]
        }

    monkeypatch.setattr(stabilization, "_resolve_workflow_ids", _fake_resolve)
    monkeypatch.setattr(stabilization, "_run_gh_json", _fake_run)

    stats, errors, window = stabilization.collect_window_stats(
        repo="org/repo",
        required_counts={"ci": 1, "deploy-smoke": 2},
        window_days=365,
        fail_on_missing=True,
        retries=2,
        retry_backoff_s=0.0,
    )

    assert "start" in window and "end" in window
    assert stats["ci"].success_runs == 1
    assert stats["ci"].failure_runs == 1
    assert stats["deploy-smoke"].success_runs == 0
    assert any("required workflow not found: deploy-smoke" in err for err in errors)


def test_build_report_payload_flags_missing_requirements() -> None:
    stats = {
        "deploy-smoke": stabilization.WorkflowWindowStats(
            workflow="deploy-smoke",
            required_successes=3,
            total_runs=2,
            success_runs=2,
            failure_runs=0,
        ),
        "release-verify": stabilization.WorkflowWindowStats(
            workflow="release-verify",
            required_successes=2,
            total_runs=2,
            success_runs=2,
            failure_runs=0,
        ),
    }
    payload = _build_report_payload(
        repository="org/repo",
        window={"start": "s", "end": "e"},
        stats=stats,
        errors=[],
    )

    assert payload["overall_pass"] is False
    missing = payload["missing_requirements"]
    assert isinstance(missing, list)
    assert missing[0]["workflow"] == "deploy-smoke"
