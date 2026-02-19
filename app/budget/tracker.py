"""Per-tenant sliding-window token budget enforcement.

Provides an in-process token budget tracker that uses a configurable
time window (default 1 hour) and per-tenant token ceiling.  Each tenant
is independently tracked.  When a request would push the tenant over
their budget the tracker raises ``BudgetExceededError``.

Thread-safe: all state is guarded by a ``threading.Lock``.

Design notes
------------
* In-process implementation avoids external Redis dependency for small
  deployments.
* Redis-backed implementation enables cross-pod budget enforcement.
* Entries older than the sliding window are pruned on every read to
  bound memory usage.
"""

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from time import monotonic, time
from typing import Any, Protocol
from uuid import uuid4

try:  # pragma: no cover - optional dependency at runtime
    import redis  # type: ignore[import-not-found,import-untyped]
except Exception:  # pragma: no cover - optional dependency at runtime
    redis = None


class BudgetExceededError(Exception):
    """Raised when a tenant's token usage exceeds their budget ceiling."""

    def __init__(self, tenant_id: str, used: int, ceiling: int, window_seconds: int):
        self.tenant_id = tenant_id
        self.used = used
        self.ceiling = ceiling
        self.window_seconds = window_seconds
        super().__init__(
            f"Token budget exceeded for tenant {tenant_id}: "
            f"{used}/{ceiling} tokens in {window_seconds}s window"
        )


class BudgetBackendError(Exception):
    """Raised when the budget backend is unavailable or misconfigured."""


class BudgetTracker(Protocol):
    def check(self, tenant_id: str, requested_tokens: int) -> None:
        """Raise BudgetExceededError if this request would exceed the ceiling."""

    def record(self, tenant_id: str, tokens: int) -> None:
        """Record actual token usage after a successful request."""

    def summary(self, tenant_id: str) -> dict[str, object]:
        """Return budget summary for this tenant."""


@dataclass
class UsageEntry:
    """A single recorded token usage event."""
    timestamp: float
    tokens: int


@dataclass
class TenantBucket:
    """Sliding-window token bucket for a single tenant."""
    entries: list[UsageEntry] = field(default_factory=list)

    def prune(self, cutoff: float) -> None:
        """Remove entries older than *cutoff* (monotonic timestamp)."""
        self.entries = [e for e in self.entries if e.timestamp >= cutoff]

    def total_tokens(self) -> int:
        return sum(e.tokens for e in self.entries)


class TokenBudgetTracker:
    """In-process sliding-window token budget tracker.

    Parameters
    ----------
    default_ceiling : int
        Default per-tenant token ceiling within the sliding window.
    window_seconds : int
        Sliding window duration in seconds.
    tenant_ceilings : dict, optional
        Per-tenant overrides for the token ceiling.
    """

    def __init__(
        self,
        default_ceiling: int = 100_000,
        window_seconds: int = 3600,
        tenant_ceilings: dict[str, int] | None = None,
    ) -> None:
        self._default_ceiling = default_ceiling
        self._window_seconds = window_seconds
        self._tenant_ceilings = dict(tenant_ceilings) if tenant_ceilings else {}
        self._buckets: dict[str, TenantBucket] = defaultdict(TenantBucket)
        self._lock = threading.Lock()

    @property
    def default_ceiling(self) -> int:
        return self._default_ceiling

    @property
    def window_seconds(self) -> int:
        return self._window_seconds

    def ceiling_for(self, tenant_id: str) -> int:
        """Return the effective token ceiling for a tenant."""
        return self._tenant_ceilings.get(tenant_id, self._default_ceiling)

    def check(self, tenant_id: str, requested_tokens: int) -> None:
        """Raise ``BudgetExceededError`` if this request would exceed the ceiling."""
        ceiling = self.ceiling_for(tenant_id)
        with self._lock:
            bucket = self._buckets[tenant_id]
            cutoff = monotonic() - self._window_seconds
            bucket.prune(cutoff)
            current = bucket.total_tokens()
            if current + requested_tokens > ceiling:
                raise BudgetExceededError(
                    tenant_id=tenant_id,
                    used=current,
                    ceiling=ceiling,
                    window_seconds=self._window_seconds,
                )

    def record(self, tenant_id: str, tokens: int) -> None:
        """Record actual token usage after a successful request."""
        with self._lock:
            self._buckets[tenant_id].entries.append(
                UsageEntry(timestamp=monotonic(), tokens=tokens)
            )

    def usage(self, tenant_id: str) -> int:
        """Return current token usage for a tenant within the window."""
        with self._lock:
            bucket = self._buckets[tenant_id]
            cutoff = monotonic() - self._window_seconds
            bucket.prune(cutoff)
            return bucket.total_tokens()

    def remaining(self, tenant_id: str) -> int:
        """Return tokens remaining in budget for a tenant."""
        ceiling = self.ceiling_for(tenant_id)
        return max(0, ceiling - self.usage(tenant_id))

    def reset(self, tenant_id: str) -> None:
        """Clear all usage data for a tenant."""
        with self._lock:
            self._buckets.pop(tenant_id, None)

    def summary(self, tenant_id: str) -> dict[str, object]:
        """Return a summary dict suitable for API responses and audit events."""
        ceiling = self.ceiling_for(tenant_id)
        used = self.usage(tenant_id)
        return {
            "tenant_id": tenant_id,
            "window_seconds": self._window_seconds,
            "ceiling": ceiling,
            "used": used,
            "remaining": max(0, ceiling - used),
            "utilization_pct": round(used / ceiling * 100, 2) if ceiling > 0 else 0.0,
        }


class RedisTokenBudgetTracker:
    """Redis-backed sliding-window token tracker for multi-replica deployments."""

    def __init__(
        self,
        redis_url: str,
        default_ceiling: int = 100_000,
        window_seconds: int = 3600,
        tenant_ceilings: dict[str, int] | None = None,
        key_prefix: str = "srg:budget",
        ttl_seconds: int = 7200,
    ) -> None:
        if redis is None:  # pragma: no cover - runtime dependency gate
            raise BudgetBackendError(
                "Redis budget backend selected but redis package is not installed"
            )
        self._default_ceiling = default_ceiling
        self._window_seconds = window_seconds
        self._tenant_ceilings = dict(tenant_ceilings) if tenant_ceilings else {}
        self._key_prefix = key_prefix
        self._ttl_seconds = max(ttl_seconds, window_seconds * 2)
        try:
            self._client: Any = redis.Redis.from_url(redis_url, decode_responses=True)
            self._client.ping()
        except Exception as exc:  # pragma: no cover - runtime guard
            raise BudgetBackendError(f"Failed to initialize Redis budget backend: {exc}") from exc

    @property
    def default_ceiling(self) -> int:
        return self._default_ceiling

    @property
    def window_seconds(self) -> int:
        return self._window_seconds

    def ceiling_for(self, tenant_id: str) -> int:
        return self._tenant_ceilings.get(tenant_id, self._default_ceiling)

    def _key(self, tenant_id: str) -> str:
        return f"{self._key_prefix}:{tenant_id}"

    @staticmethod
    def _member_tokens(member: str) -> int:
        # member format: "<timestamp>:<tokens>:<uuid>"
        parts = member.split(":")
        if len(parts) < 3:
            return 0
        try:
            return max(int(parts[1]), 0)
        except ValueError:
            return 0

    def _current_usage(self, tenant_id: str) -> int:
        key = self._key(tenant_id)
        now = time()
        cutoff = now - self._window_seconds
        try:
            self._client.zremrangebyscore(key, 0, cutoff)
            members: list[str] = self._client.zrangebyscore(key, cutoff, "+inf")
        except Exception as exc:
            raise BudgetBackendError(f"Redis read failed: {exc}") from exc
        return sum(self._member_tokens(member) for member in members)

    def check(self, tenant_id: str, requested_tokens: int) -> None:
        ceiling = self.ceiling_for(tenant_id)
        current = self._current_usage(tenant_id)
        if current + requested_tokens > ceiling:
            raise BudgetExceededError(
                tenant_id=tenant_id,
                used=current,
                ceiling=ceiling,
                window_seconds=self._window_seconds,
            )

    def record(self, tenant_id: str, tokens: int) -> None:
        key = self._key(tenant_id)
        now = time()
        member = f"{now:.6f}:{max(tokens, 0)}:{uuid4().hex}"
        try:
            pipe = self._client.pipeline()
            pipe.zadd(key, {member: now})
            pipe.expire(key, self._ttl_seconds)
            pipe.execute()
        except Exception as exc:
            raise BudgetBackendError(f"Redis write failed: {exc}") from exc

    def usage(self, tenant_id: str) -> int:
        return self._current_usage(tenant_id)

    def summary(self, tenant_id: str) -> dict[str, object]:
        ceiling = self.ceiling_for(tenant_id)
        used = self.usage(tenant_id)
        return {
            "tenant_id": tenant_id,
            "window_seconds": self._window_seconds,
            "ceiling": ceiling,
            "used": used,
            "remaining": max(0, ceiling - used),
            "utilization_pct": round(used / ceiling * 100, 2) if ceiling > 0 else 0.0,
        }
