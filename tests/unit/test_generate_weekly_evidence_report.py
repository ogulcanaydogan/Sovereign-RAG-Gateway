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


def test_render_report_includes_stabilization_and_snapshot_paths() -> None:
    report = render_report(
        report_date="2026-03-03",
        generated_at="2026-03-03T00:00:00+00:00",
        deploy_smoke=WorkflowEvidence("deploy-smoke", "11", "u11", "t11", "success"),
        release=WorkflowEvidence("release", "12", "u12", "t12", "success"),
        release_tag="v0.7.0",
        release_url="u13",
        benchmark_summary=None,
        stabilization_summary={
            "overall_pass": True,
            "observed": {
                "deploy-smoke": {
                    "success_runs": 3,
                    "required_successes": 3,
                    "pass": True,
                }
            },
        },
        release_snapshot_json_path="docs/benchmarks/reports/assets/release-verification/weekly-2026-03-03.json",
        release_snapshot_png_path="docs/benchmarks/reports/assets/release-verification/weekly-2026-03-03.png",
    )
    assert "## Stabilization Window" in report
    assert "Overall pass: `True`" in report
    assert "Snapshot JSON:" in report
    assert "weekly-2026-03-03.png" in report


def test_render_report_includes_slo_summary_section() -> None:
    report = render_report(
        report_date="2026-03-07",
        generated_at="2026-03-07T00:00:00+00:00",
        deploy_smoke=WorkflowEvidence("deploy-smoke", "21", "u21", "t21", "success"),
        release=WorkflowEvidence("release", "22", "u22", "t22", "success"),
        release_tag="v1.1.0-alpha.1",
        release_url="u23",
        benchmark_summary=None,
        slo_summary={
            "overall_pass": True,
            "thresholds": {
                "max_error_rate": 0.01,
                "max_p95_regression_pct": 10,
                "max_nominal_shed_rate": 0.02,
            },
            "observed": {
                "error_rate": 0.005,
                "p95_regression_vs_baseline_pct": 4.2,
                "nominal_shed_rate": 0.01,
            },
        },
        fault_summary={"totals": {"failed_scenarios": 0, "scenarios_total": 3, "error_rate": 0.01}},
        soak_summary={
            "metrics": {
                "latency_ms_p95": 160,
                "errors_total": 1,
                "requests_total": 200,
                "shed_rate": 0.01,
            }
        },
    )
    assert "## Reliability/SLO Summary" in report
    assert "p95_regression_vs_baseline_pct" in report
    assert "Fault suite:" in report
