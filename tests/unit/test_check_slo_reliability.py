import pytest

from scripts.check_slo_reliability import evaluate_slo_reliability, main


def _summary(
    *,
    requests_total: int,
    errors_total: int,
    latency_ms_p95: float,
    shed_rate: float = 0.0,
):
    return {
        "metrics": {
            "requests_total": requests_total,
            "errors_total": errors_total,
            "latency_ms_p95": latency_ms_p95,
            "shed_rate": shed_rate,
        }
    }


def test_evaluate_slo_reliability_passes_within_thresholds() -> None:
    result = evaluate_slo_reliability(
        benchmark_summary=_summary(requests_total=200, errors_total=1, latency_ms_p95=140.0),
        fault_summary={"totals": {"error_rate": 0.01, "failed_scenarios": 0}},
        soak_summary=_summary(
            requests_total=300,
            errors_total=2,
            latency_ms_p95=154.0,
            shed_rate=0.015,
        ),
        baseline_summary={"metrics": {"latency_ms_p95": 150.0}},
        max_error_rate=0.02,
        max_p95_regression_pct=10.0,
        max_nominal_shed_rate=0.02,
    )
    assert result["overall_pass"] is True
    assert result["missing_requirements"] == []


def test_evaluate_slo_reliability_fails_when_thresholds_exceed() -> None:
    result = evaluate_slo_reliability(
        benchmark_summary=_summary(requests_total=100, errors_total=4, latency_ms_p95=140.0),
        fault_summary={"totals": {"error_rate": 0.02, "failed_scenarios": 1}},
        soak_summary=_summary(
            requests_total=100,
            errors_total=2,
            latency_ms_p95=200.0,
            shed_rate=0.05,
        ),
        baseline_summary={"metrics": {"latency_ms_p95": 150.0}},
        max_error_rate=0.01,
        max_p95_regression_pct=10.0,
        max_nominal_shed_rate=0.02,
    )
    assert result["overall_pass"] is False
    names = {item["name"] for item in result["missing_requirements"]}
    assert "error_rate" in names
    assert "p95_regression_vs_baseline" in names
    assert "nominal_shed_rate" in names
    assert "fault_suite_scenarios" in names


def test_main_fails_on_missing_artifact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "check_slo_reliability.py",
            "--benchmark-summary",
            "/tmp/missing-benchmark.json",
            "--fault-summary",
            "/tmp/missing-fault.json",
            "--soak-summary",
            "/tmp/missing-soak.json",
            "--baseline-summary",
            "/tmp/missing-baseline.json",
        ],
    )
    with pytest.raises(SystemExit, match="file does not exist"):
        main()
