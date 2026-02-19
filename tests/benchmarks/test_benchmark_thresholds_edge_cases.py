"""Tests for benchmark threshold evaluation edge cases — null values,
missing metrics, type errors, and boundary conditions."""

from scripts.check_benchmark_thresholds import evaluate_thresholds


def _default_thresholds() -> dict[str, float]:
    return {
        "max_leakage_rate": 0.005,
        "max_latency_p95_ms": 250.0,
        "max_cost_drift_pct": 5.0,
        "min_citation_presence_rate": 0.5,
    }


def test_null_metric_values_produce_descriptive_failure() -> None:
    """Null/None metric values should produce clear failure messages,
    not raise an unhandled TypeError."""
    summary = {
        "metrics": {
            "leakage_rate": None,
            "latency_ms_p95": None,
            "cost_drift_pct": None,
            "citation_presence_rate": None,
        }
    }
    failures = evaluate_thresholds(summary=summary, **_default_thresholds())
    assert len(failures) >= 4
    assert any(
        "null" in f.lower() or "none" in f.lower() or "missing" in f.lower()
        for f in failures
    )


def test_missing_metrics_object_returns_failure() -> None:
    """Summary without a metrics object should return a failure, not crash."""
    failures = evaluate_thresholds(summary={}, **_default_thresholds())
    assert len(failures) == 1
    assert "missing metrics" in failures[0].lower()


def test_string_metric_value_handled_gracefully() -> None:
    """A string value like 'n/a' for a numeric metric should produce
    a descriptive failure, not a ValueError."""
    summary = {
        "metrics": {
            "leakage_rate": "n/a",
            "latency_ms_p95": 100.0,
            "cost_drift_pct": 0.0,
            "citation_presence_rate": 0.9,
        }
    }
    failures = evaluate_thresholds(summary=summary, **_default_thresholds())
    assert len(failures) >= 1
    assert any("leakage_rate" in f for f in failures)


def test_boundary_value_at_exact_threshold_passes() -> None:
    """A metric exactly at the threshold should pass (threshold is strict >)."""
    summary = {
        "metrics": {
            "leakage_rate": 0.005,
            "latency_ms_p95": 250.0,
            "cost_drift_pct": 5.0,
            "citation_presence_rate": 0.5,
        }
    }
    failures = evaluate_thresholds(summary=summary, **_default_thresholds())
    assert failures == []
