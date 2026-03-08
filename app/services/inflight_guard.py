from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class InflightAcquireResult:
    allowed: bool
    reason: str | None
    global_inflight: int
    tenant_inflight: int


class InflightGuard:
    """In-process inflight limiter for global and tenant-scoped caps."""

    def __init__(
        self,
        *,
        global_limit: int,
        tenant_default_limit: int,
        tenant_limits: dict[str, int] | None = None,
    ) -> None:
        self._global_limit = max(int(global_limit), 0)
        self._tenant_default_limit = max(int(tenant_default_limit), 0)
        self._tenant_limits = {
            key: max(int(value), 0)
            for key, value in (tenant_limits or {}).items()
            if key and int(value) > 0
        }
        self._lock = Lock()
        self._global_inflight = 0
        self._tenant_inflight: dict[str, int] = defaultdict(int)

    @property
    def enabled(self) -> bool:
        return self._global_limit > 0 or self._tenant_default_limit > 0 or bool(self._tenant_limits)

    def try_acquire(self, tenant_id: str) -> InflightAcquireResult:
        if not tenant_id:
            tenant_id = "unknown"

        with self._lock:
            current_global = self._global_inflight
            current_tenant = self._tenant_inflight[tenant_id]

            if self._global_limit > 0 and current_global >= self._global_limit:
                return InflightAcquireResult(
                    allowed=False,
                    reason="global_limit",
                    global_inflight=current_global,
                    tenant_inflight=current_tenant,
                )

            tenant_limit = self._tenant_limit_for(tenant_id)
            if tenant_limit > 0 and current_tenant >= tenant_limit:
                return InflightAcquireResult(
                    allowed=False,
                    reason="tenant_limit",
                    global_inflight=current_global,
                    tenant_inflight=current_tenant,
                )

            self._global_inflight = current_global + 1
            self._tenant_inflight[tenant_id] = current_tenant + 1
            return InflightAcquireResult(
                allowed=True,
                reason=None,
                global_inflight=self._global_inflight,
                tenant_inflight=self._tenant_inflight[tenant_id],
            )

    def release(self, tenant_id: str) -> None:
        if not tenant_id:
            tenant_id = "unknown"

        with self._lock:
            if self._global_inflight > 0:
                self._global_inflight -= 1
            current_tenant = self._tenant_inflight.get(tenant_id, 0)
            if current_tenant <= 1:
                self._tenant_inflight.pop(tenant_id, None)
            else:
                self._tenant_inflight[tenant_id] = current_tenant - 1

    def _tenant_limit_for(self, tenant_id: str) -> int:
        configured = self._tenant_limits.get(tenant_id)
        if configured is not None and configured > 0:
            return configured
        return self._tenant_default_limit
