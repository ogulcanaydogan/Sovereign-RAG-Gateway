import json
from pathlib import Path

from scripts.generate_weekly_evidence_report import WorkflowEvidence, render_report


def test_render_report_includes_workflow_and_release() -> None:
    report = render_report(
        report_date="2026-02-20",
        generated_at="2026-02-20T00:00:00+00:00",
        deploy_smoke=WorkflowEvidence(
            name="deploy-smoke",
            run_id="22200000001",
            run_url="https://example.test/deploy",
            completed_at="2026-02-20T00:01:00Z",
            result="success",
        ),
        release=WorkflowEvidence(
            name="release",
            run_id="22200000002",
            run_url="https://example.test/release",
            completed_at="2026-02-20T00:02:00Z",
            result="success",
        ),
        release_tag="v0.5.0-alpha.1",
        release_url="https://example.test/release/tag",
        benchmark_summary={"scenario": "enforce_redact", "metrics": {"latency_ms_p95": 123}},
    )
    assert "# Weekly Report - 2026-02-20" in report
    assert "22200000001" in report
    assert "v0.5.0-alpha.1" in report
    assert "Latency p95 (ms): `123`" in report


def test_render_report_handles_missing_benchmark_snapshot() -> None:
    report = render_report(
        report_date="2026-02-20",
        generated_at="2026-02-20T00:00:00+00:00",
        deploy_smoke=WorkflowEvidence(
            name="deploy-smoke",
            run_id="n/a",
            run_url="n/a",
            completed_at="n/a",
            result="unknown",
        ),
        release=WorkflowEvidence(
            name="release",
            run_id="n/a",
            run_url="n/a",
            completed_at="n/a",
            result="unknown",
        ),
        release_tag="",
        release_url="",
        benchmark_summary=None,
    )
    assert "No benchmark summary JSON was available" in report


def test_benchmark_summary_json_round_trip_for_render(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps({"scenario": "enforce_redact", "metrics": {"requests_total": 10}}),
        encoding="utf-8",
    )
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    report = render_report(
        report_date="2026-02-20",
        generated_at="2026-02-20T00:00:00+00:00",
        deploy_smoke=WorkflowEvidence("deploy-smoke", "1", "u1", "t1", "success"),
        release=WorkflowEvidence("release", "2", "u2", "t2", "success"),
        release_tag="v0.5.0-alpha.1",
        release_url="u3",
        benchmark_summary=payload,
    )
    assert "Requests: `10`" in report
