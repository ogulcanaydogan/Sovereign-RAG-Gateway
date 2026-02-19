from scripts.check_benchmark_trend import evaluate_trend


def test_benchmark_trend_passes_when_within_regression_limits() -> None:
    baseline = {
        "metrics": {
            "latency_ms_p95": 145.0,
            "leakage_rate": 0.004,
            "cost_drift_pct": 0.0,
            "citation_presence_rate": 1.0,
        }
    }
    current = {
        "metrics": {
            "latency_ms_p95": 150.0,
            "leakage_rate": 0.0045,
            "cost_drift_pct": 1.5,
            "citation_presence_rate": 0.98,
        }
    }
    failures = evaluate_trend(
        current_summary=current,
        baseline_summary=baseline,
        max_latency_regression_pct=20.0,
        max_leakage_regression_abs=0.002,
        max_abs_cost_drift_regression_pct=3.0,
        max_citation_drop_abs=0.1,
    )
    assert failures == []


def test_benchmark_trend_fails_when_regressions_exceed_limits() -> None:
    baseline = {
        "metrics": {
            "latency_ms_p95": 145.0,
            "leakage_rate": 0.004,
            "cost_drift_pct": 0.0,
            "citation_presence_rate": 1.0,
        }
    }
    current = {
        "metrics": {
            "latency_ms_p95": 220.0,
            "leakage_rate": 0.01,
            "cost_drift_pct": 9.0,
            "citation_presence_rate": 0.7,
        }
    }
    failures = evaluate_trend(
        current_summary=current,
        baseline_summary=baseline,
        max_latency_regression_pct=20.0,
        max_leakage_regression_abs=0.002,
        max_abs_cost_drift_regression_pct=3.0,
        max_citation_drop_abs=0.1,
    )
    assert len(failures) == 4


def test_benchmark_trend_returns_failure_for_missing_metrics() -> None:
    failures = evaluate_trend(
        current_summary={"metrics": {}},
        baseline_summary={"metrics": {}},
        max_latency_regression_pct=20.0,
        max_leakage_regression_abs=0.002,
        max_abs_cost_drift_regression_pct=3.0,
        max_citation_drop_abs=0.1,
    )
    assert len(failures) == 1
    assert "missing or null" in failures[0]
