"""Async webhook dispatcher for audit events.

Fires HTTP POST notifications to registered webhook endpoints when
qualifying events occur (policy violations, provider fallbacks, budget
alerts, redaction hits).  Delivery is best-effort with configurable
retry and timeout.

Thread-safe: the dispatcher can be called from any coroutine context.
Non-blocking: fires webhooks in background tasks so they never delay
the API response.

Webhook payload is a JSON envelope:

    {
        "event_type": "policy_denied",
        "timestamp": "2026-02-19T12:00:00+00:00",
        "gateway_version": "0.4.0",
        "payload": { ... audit event fields ... }
    }

Signature verification: each POST includes an ``X-SRG-Signature``
header containing an HMAC-SHA256 of the JSON body, keyed by the
webhook secret.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx

logger = logging.getLogger("srg.webhooks")

GATEWAY_VERSION = "0.4.0"


class WebhookEventType(Enum):
    POLICY_DENIED = "policy_denied"
    PROVIDER_FALLBACK = "provider_fallback"
    BUDGET_WARNING = "budget_warning"
    BUDGET_EXCEEDED = "budget_exceeded"
    REDACTION_HIT = "redaction_hit"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class WebhookEndpoint:
    """A registered webhook receiver."""
    url: str
    secret: str = ""
    event_types: frozenset[WebhookEventType] = field(
        default_factory=lambda: frozenset(WebhookEventType)
    )
    enabled: bool = True


@dataclass
class WebhookDeliveryResult:
    """Result of a single webhook delivery attempt."""
    endpoint_url: str
    event_type: str
    status_code: int | None = None
    success: bool = False
    error: str | None = None
    duration_ms: float = 0.0
    attempt_count: int = 1
    idempotency_key: str = ""


class WebhookDispatcher:
    """Non-blocking webhook dispatcher with HMAC signing.

    Parameters
    ----------
    endpoints : list of ``WebhookEndpoint``
        Registered webhook receivers.
    timeout_s : float
        HTTP timeout for each webhook POST.
    max_retries : int
        Maximum number of retry attempts on transient failures.
    """

    def __init__(
        self,
        endpoints: list[WebhookEndpoint] | None = None,
        timeout_s: float = 5.0,
        max_retries: int = 1,
        backoff_base_s: float = 0.2,
        backoff_max_s: float = 2.0,
        dead_letter_path: Path | None = None,
    ) -> None:
        self._endpoints = list(endpoints) if endpoints else []
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._backoff_base_s = max(backoff_base_s, 0.0)
        self._backoff_max_s = max(backoff_max_s, self._backoff_base_s)
        self._dead_letter_path = dead_letter_path
        self._delivery_log: list[WebhookDeliveryResult] = []
        self._max_log_entries = 500

    @property
    def endpoint_count(self) -> int:
        return len(self._endpoints)

    def add_endpoint(self, endpoint: WebhookEndpoint) -> None:
        self._endpoints.append(endpoint)

    def should_fire(self, event_type: WebhookEventType) -> bool:
        """Check if any endpoint is subscribed to this event type."""
        return any(
            ep.enabled and event_type in ep.event_types
            for ep in self._endpoints
        )

    async def dispatch(
        self,
        event_type: WebhookEventType,
        payload: dict[str, Any],
    ) -> list[WebhookDeliveryResult]:
        """Dispatch a webhook event to all subscribed endpoints.

        Returns a list of delivery results (one per endpoint).
        """
        results: list[WebhookDeliveryResult] = []
        envelope = {
            "event_id": f"evt-{uuid4().hex}",
            "event_type": event_type.value,
            "timestamp": datetime.now(UTC).isoformat(),
            "gateway_version": GATEWAY_VERSION,
            "payload": payload,
        }
        body = json.dumps(envelope, separators=(",", ":"), ensure_ascii=True)

        for endpoint in self._endpoints:
            if not endpoint.enabled:
                continue
            if event_type not in endpoint.event_types:
                continue

            result = await self._deliver(
                endpoint=endpoint,
                body=body,
                event_type=event_type.value,
            )
            if not result.success:
                self._write_dead_letter(
                    endpoint=endpoint,
                    event_type=event_type.value,
                    body=body,
                    result=result,
                )
            results.append(result)
            self._record_delivery(result)

        return results

    async def _deliver(
        self,
        endpoint: WebhookEndpoint,
        body: str,
        event_type: str,
    ) -> WebhookDeliveryResult:
        """POST the webhook body to an endpoint with retry."""
        idempotency_key = hashlib.sha256(
            f"{endpoint.url}:{body}".encode()
        ).hexdigest()
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": f"SovereignRAGGateway/{GATEWAY_VERSION}",
            "X-SRG-Idempotency-Key": idempotency_key,
        }
        if endpoint.secret:
            signature = hmac.new(
                endpoint.secret.encode("utf-8"),
                body.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["X-SRG-Signature"] = f"sha256={signature}"

        last_error: str | None = None
        for attempt in range(1 + self._max_retries):
            started = perf_counter()
            try:
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    resp = await client.post(
                        endpoint.url, content=body, headers=headers
                    )
                    duration_ms = round((perf_counter() - started) * 1000, 3)
                    success = 200 <= resp.status_code < 300
                    retryable = resp.status_code in {429, 500, 502, 503, 504}
                    if not success and attempt < self._max_retries and retryable:
                        await asyncio.sleep(
                            min(
                                self._backoff_base_s * (2**attempt),
                                self._backoff_max_s,
                            )
                        )
                        continue
                    return WebhookDeliveryResult(
                        endpoint_url=endpoint.url,
                        event_type=event_type,
                        status_code=resp.status_code,
                        success=success,
                        duration_ms=duration_ms,
                        attempt_count=attempt + 1,
                        idempotency_key=idempotency_key,
                    )
            except httpx.HTTPError as exc:
                last_error = f"attempt {attempt + 1}: {type(exc).__name__}: {exc}"
                logger.warning(
                    "webhook_delivery_failed",
                    extra={
                        "endpoint": endpoint.url,
                        "attempt": attempt + 1,
                        "error": str(exc),
                    },
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(
                        min(
                            self._backoff_base_s * (2**attempt),
                            self._backoff_max_s,
                        )
                    )

        return WebhookDeliveryResult(
            endpoint_url=endpoint.url,
            event_type=event_type,
            success=False,
            error=last_error,
            duration_ms=0.0,
            attempt_count=self._max_retries + 1,
            idempotency_key=idempotency_key,
        )

    def _record_delivery(self, result: WebhookDeliveryResult) -> None:
        self._delivery_log.append(result)
        if len(self._delivery_log) > self._max_log_entries:
            self._delivery_log = self._delivery_log[-self._max_log_entries:]

    def recent_deliveries(self, limit: int = 20) -> list[WebhookDeliveryResult]:
        """Return the most recent delivery results."""
        return list(reversed(self._delivery_log[-limit:]))

    def _write_dead_letter(
        self,
        endpoint: WebhookEndpoint,
        event_type: str,
        body: str,
        result: WebhookDeliveryResult,
    ) -> None:
        if self._dead_letter_path is None:
            return
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "endpoint_url": endpoint.url,
            "status_code": result.status_code,
            "error": result.error,
            "attempt_count": result.attempt_count,
            "idempotency_key": result.idempotency_key,
            "body": json.loads(body),
        }
        try:
            self._dead_letter_path.parent.mkdir(parents=True, exist_ok=True)
            with self._dead_letter_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=True))
                fh.write("\n")
        except OSError as exc:  # pragma: no cover - runtime guard
            logger.warning(
                "webhook_dead_letter_write_failed",
                extra={
                    "path": str(self._dead_letter_path),
                    "error": str(exc),
                },
            )
