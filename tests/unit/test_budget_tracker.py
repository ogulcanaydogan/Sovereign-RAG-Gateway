import pytest

from app.budget.tracker import (
    BudgetBackendError,
    BudgetExceededError,
    RedisTokenBudgetTracker,
    TokenBudgetTracker,
)


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


def test_redis_budget_tracker_enforces_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    storage: dict[str, list[tuple[float, str]]] = {}

    class _Pipeline:
        def __init__(self, client) -> None:  # type: ignore[no-untyped-def]
            self._client = client
            self._ops: list[tuple[str, tuple[object, ...]]] = []

        def zadd(self, key: str, mapping: dict[str, float]):  # type: ignore[no-untyped-def]
            self._ops.append(("zadd", (key, mapping)))
            return self

        def expire(self, key: str, ttl_seconds: int):  # type: ignore[no-untyped-def]
            self._ops.append(("expire", (key, ttl_seconds)))
            return self

        def execute(self):  # type: ignore[no-untyped-def]
            for op, args in self._ops:
                getattr(self._client, op)(*args)
            return []

    class _FakeRedisClient:
        def ping(self) -> bool:
            return True

        def pipeline(self) -> _Pipeline:
            return _Pipeline(self)

        def zadd(self, key: str, mapping: dict[str, float]) -> int:
            entries = storage.setdefault(key, [])
            for member, score in mapping.items():
                entries.append((score, member))
            return len(mapping)

        def expire(self, key: str, ttl_seconds: int) -> bool:
            _ = key, ttl_seconds
            return True

        def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
            entries = storage.get(key, [])
            remaining = [
                (score, member)
                for score, member in entries
                if not (min_score <= score <= max_score)
            ]
            removed = len(entries) - len(remaining)
            storage[key] = remaining
            return removed

        def zrangebyscore(self, key: str, min_score: float, max_score: str) -> list[str]:
            entries = storage.get(key, [])
            upper = float("inf") if max_score == "+inf" else float(max_score)
            return [
                member
                for score, member in sorted(entries, key=lambda item: item[0])
                if min_score <= score <= upper
            ]

    class _FakeRedisFactory:
        @staticmethod
        def from_url(url: str, decode_responses: bool = True) -> _FakeRedisClient:
            _ = url, decode_responses
            return _FakeRedisClient()

    class _FakeRedisModule:
        Redis = _FakeRedisFactory

    monkeypatch.setattr("app.budget.tracker.redis", _FakeRedisModule())

    tracker = RedisTokenBudgetTracker(
        redis_url="redis://localhost:6379/0",
        default_ceiling=50,
        window_seconds=3600,
        key_prefix="test:budget",
    )
    tracker.record("tenant-a", 45)
    with pytest.raises(BudgetExceededError):
        tracker.check("tenant-a", 10)
    summary = tracker.summary("tenant-a")
    assert summary["used"] == 45
    assert summary["remaining"] == 5


def test_redis_budget_tracker_raises_when_dependency_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.budget.tracker.redis", None)
    with pytest.raises(BudgetBackendError):
        RedisTokenBudgetTracker(redis_url="redis://localhost:6379/0")
