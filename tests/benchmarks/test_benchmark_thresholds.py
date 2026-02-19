from scripts.check_benchmark_thresholds import evaluate_thresholds


def test_benchmark_thresholds_pass_for_expected_summary() -> None:
    summary = {
        "metrics": {
            "leakage_rate": 0.004,
            "latency_ms_p95": 145.0,
            "cost_drift_pct": 0.0,
            "citation_presence_rate": 0.9,
        }
    }
    failures = evaluate_thresholds(
        summary=summary,
        max_leakage_rate=0.005,
        max_latency_p95_ms=250.0,
        max_cost_drift_pct=5.0,
        min_citation_presence_rate=0.5,
    )
    assert failures == []


def test_benchmark_thresholds_fail_on_violations() -> None:
    summary = {
        "metrics": {
            "leakage_rate": 0.01,
            "latency_ms_p95": 350.0,
            "cost_drift_pct": 8.5,
            "citation_presence_rate": 0.1,
        }
    }
    failures = evaluate_thresholds(
        summary=summary,
        max_leakage_rate=0.005,
        max_latency_p95_ms=250.0,
        max_cost_drift_pct=5.0,
        min_citation_presence_rate=0.5,
    )
    assert len(failures) == 4


def test_benchmark_thresholds_support_fault_metrics() -> None:
    summary = {
        "metrics": {
            "leakage_rate": 0.004,
            "latency_ms_p95": 145.0,
            "cost_drift_pct": 0.0,
            "citation_presence_rate": 0.9,
            "fault_attribution_accuracy": 0.98,
            "detection_delay_ms_p95": 300.0,
            "slo_burn_prediction_error_pct": 4.0,
            "false_positive_incident_rate": 0.02,
        }
    }
    failures = evaluate_thresholds(
        summary=summary,
        max_leakage_rate=0.005,
        max_latency_p95_ms=250.0,
        max_cost_drift_pct=5.0,
        min_citation_presence_rate=0.5,
        min_fault_attribution_accuracy=0.95,
        max_detection_delay_ms_p95=500.0,
        max_slo_burn_prediction_error_pct=5.0,
        max_false_positive_incident_rate=0.05,
    )
    assert failures == []
