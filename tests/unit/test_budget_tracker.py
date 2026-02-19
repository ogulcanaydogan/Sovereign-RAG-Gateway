import pytest

from app.budget.tracker import BudgetExceededError, TokenBudgetTracker


def test_budget_tracker_records_and_reports_usage() -> None:
    tracker = TokenBudgetTracker(default_ceiling=100, window_seconds=3600)
    tracker.check("tenant-a", 20)
    tracker.record("tenant-a", 20)
    tracker.record("tenant-a", 10)

    assert tracker.usage("tenant-a") == 30
    summary = tracker.summary("tenant-a")
    assert summary["ceiling"] == 100
    assert summary["used"] == 30
    assert summary["remaining"] == 70


def test_budget_tracker_enforces_ceiling() -> None:
    tracker = TokenBudgetTracker(default_ceiling=50, window_seconds=3600)
    tracker.record("tenant-a", 45)

    with pytest.raises(BudgetExceededError):
        tracker.check("tenant-a", 10)

