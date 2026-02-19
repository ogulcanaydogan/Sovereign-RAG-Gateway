"""Lightweight OpenTelemetry-compatible span collector.

This module provides an in-process span collector that captures structured
spans for each request lifecycle phase (policy evaluation, RAG retrieval,
redaction, provider call, audit write).  Spans are stored per-request and
can be exported as a JSON-serialisable list for diagnostics, audit, or
forwarding to an OTLP collector.

The design avoids a hard dependency on the ``opentelemetry-sdk`` package.
When a full OTel SDK is available, the ``OTLPSpanExporter`` can be used
via the export hook; otherwise spans are collected in-memory and can be
read via the ``/v1/traces`` diagnostics endpoint.

Thread-safe: per-request span buffers are isolated by request-id.
"""

import json
import logging
import re
import threading
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from time import perf_counter, time_ns
from typing import Any, Protocol
from uuid import uuid4

import httpx

logger = logging.getLogger("srg.tracing")

_NON_HEX_RE = re.compile(r"[^0-9a-fA-F]")


def _normalize_hex(value: str, length: int) -> str:
    normalized = _NON_HEX_RE.sub("", value).lower()
    if len(normalized) >= length:
        return normalized[:length]
    return normalized.rjust(length, "0")


def _otlp_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if value is None:
        return {"stringValue": "null"}
    if isinstance(value, (list, tuple)):
        return {
            "arrayValue": {
                "values": [_otlp_value(item) for item in value]
            }
        }
    if isinstance(value, dict):
        return {"stringValue": json.dumps(value, sort_keys=True, ensure_ascii=True)}
    return {"stringValue": str(value)}


def _otlp_attributes(attributes: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"key": key, "value": _otlp_value(value)}
        for key, value in attributes.items()
    ]


class TraceExporter(Protocol):
    def export_trace(self, trace_id: str, spans: list["Span"]) -> None:
        """Export a completed trace."""


class OTLPHTTPTraceExporter:
    """Best-effort OTLP/HTTP trace exporter.

    Exports traces in OpenTelemetry JSON mapping to an OTLP/HTTP endpoint
    (typically ``http://<collector>:4318/v1/traces``).
    """

    def __init__(
        self,
        endpoint: str,
        timeout_s: float = 2.0,
        headers: dict[str, str] | None = None,
        service_name: str = "sovereign-rag-gateway",
    ) -> None:
        self._endpoint = endpoint
        self._timeout_s = timeout_s
        self._headers = dict(headers or {})
        self._service_name = service_name

    def export_trace(self, trace_id: str, spans: list["Span"]) -> None:
        payload = self._to_payload(spans)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SovereignRAGGateway/trace-exporter",
            **self._headers,
        }
        try:
            response = httpx.post(
                self._endpoint,
                headers=headers,
                json=payload,
                timeout=self._timeout_s,
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "trace_export_failed",
                extra={
                    "trace_id": trace_id,
                    "endpoint": self._endpoint,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
            return
        if response.status_code >= 400:
            logger.warning(
                "trace_export_rejected",
                extra={
                    "trace_id": trace_id,
                    "endpoint": self._endpoint,
                    "status_code": response.status_code,
                    "response_body": response.text[:500],
                },
            )

    def _to_payload(self, spans: list["Span"]) -> dict[str, Any]:
        if not spans:
            return {"resourceSpans": []}
        service_name = spans[0].service or self._service_name
        otlp_spans: list[dict[str, Any]] = []
        for span in spans:
            start_ns = int(span.start_time_ms * 1_000_000)
            end_ns = int(span.end_time_ms * 1_000_000)
            otlp_span = {
                "traceId": _normalize_hex(span.trace_id, 32),
                "spanId": _normalize_hex(span.span_id, 16),
                "name": span.operation,
                "kind": 1,
                "startTimeUnixNano": str(start_ns),
                "endTimeUnixNano": str(end_ns),
                "attributes": _otlp_attributes(span.attributes),
                "events": [
                    {
                        "name": str(event.get("name", "event")),
                        "timeUnixNano": str(end_ns),
                        "attributes": _otlp_attributes(
                            event.get("attributes", {})
                            if isinstance(event.get("attributes", {}), dict)
                            else {}
                        ),
                    }
                    for event in span.events
                ],
                "status": {
                    "code": 1 if span.status == "ok" else 2,
                },
            }
            if span.parent_span_id:
                otlp_span["parentSpanId"] = _normalize_hex(span.parent_span_id, 16)
            otlp_spans.append(otlp_span)
        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": service_name},
                            }
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "srg.tracing"},
                            "spans": otlp_spans,
                        }
                    ],
                }
            ]
        }


@dataclass
class Span:
    """A single trace span."""
    trace_id: str
    span_id: str
    parent_span_id: str | None
    operation: str
    service: str = "sovereign-rag-gateway"
    start_time_ms: float = 0.0
    end_time_ms: float = 0.0
    duration_ms: float = 0.0
    status: str = "ok"
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SpanContext:
    """Context manager that captures a span with automatic timing."""

    def __init__(
        self,
        collector: "SpanCollector",
        trace_id: str,
        operation: str,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        self._collector = collector
        self._trace_id = trace_id
        self._operation = operation
        self._parent_span_id = parent_span_id
        self._attributes = dict(attributes) if attributes else {}
        self.span_id = uuid4().hex[:16]
        self._start_perf: float = 0.0
        self._start_unix_ns: int = 0
        self._span: Span | None = None
        self._events: list[dict[str, Any]] = []

    def __enter__(self) -> "SpanContext":
        self._start_perf = perf_counter()
        self._start_unix_ns = time_ns()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        end_perf = perf_counter()
        end_unix_ns = time_ns()
        duration = (end_perf - self._start_perf) * 1000
        status = "ok" if exc_type is None else "error"
        events: list[dict[str, Any]] = list(self._events)
        if exc_val is not None:
            events.append({
                "name": "exception",
                "attributes": {
                    "exception.type": type(exc_val).__name__,
                    "exception.message": str(exc_val)[:500],
                },
            })
            self._attributes["error.type"] = type(exc_val).__name__

        span = Span(
            trace_id=self._trace_id,
            span_id=self.span_id,
            parent_span_id=self._parent_span_id,
            operation=self._operation,
            start_time_ms=round(self._start_unix_ns / 1_000_000, 3),
            end_time_ms=round(end_unix_ns / 1_000_000, 3),
            duration_ms=round(duration, 3),
            status=status,
            attributes=self._attributes,
            events=events,
        )
        self._span = span
        self._collector.record_span(self._trace_id, span)

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a span attribute (call within the ``with`` block)."""
        self._attributes[key] = value

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Record a span event."""
        event = {
            "name": name,
            "attributes": attributes or {},
        }
        if self._span is None:
            self._events.append(event)
            return
        self._span.events.append(event)


class SpanCollector:
    """In-process span collector, keyed by trace (request) ID.

    Parameters
    ----------
    max_traces : int
        Maximum number of completed traces to retain.  Oldest traces
        are evicted when the limit is exceeded.
    """

    def __init__(
        self,
        max_traces: int = 1000,
        exporter: TraceExporter | None = None,
        export_root_operation: str = "gateway.request",
    ) -> None:
        self._max_traces = max_traces
        self._exporter = exporter
        self._export_root_operation = export_root_operation
        self._traces: dict[str, list[Span]] = defaultdict(list)
        self._trace_order: list[str] = []
        self._lock = threading.Lock()

    def span(
        self,
        trace_id: str,
        operation: str,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> SpanContext:
        """Create a span context manager."""
        return SpanContext(
            collector=self,
            trace_id=trace_id,
            operation=operation,
            parent_span_id=parent_span_id,
            attributes=attributes,
        )

    def record_span(self, trace_id: str, span: Span) -> None:
        """Record a completed span."""
        trace_snapshot: list[Span] | None = None
        with self._lock:
            self._traces[trace_id].append(span)
            if trace_id not in self._trace_order:
                self._trace_order.append(trace_id)
            if self._exporter is not None and span.operation == self._export_root_operation:
                trace_snapshot = list(self._traces.get(trace_id, []))
            # Evict oldest traces if over limit
            while len(self._trace_order) > self._max_traces:
                oldest = self._trace_order.pop(0)
                self._traces.pop(oldest, None)
        if trace_snapshot is not None and self._exporter is not None:
            try:
                self._exporter.export_trace(trace_id, trace_snapshot)
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                logger.warning(
                    "trace_export_unhandled_error",
                    extra={
                        "trace_id": trace_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )

    def get_trace(self, trace_id: str) -> list[dict[str, Any]]:
        """Return all spans for a given trace as dicts."""
        with self._lock:
            spans = self._traces.get(trace_id, [])
            return [s.to_dict() for s in spans]

    def list_traces(self, limit: int = 20) -> list[str]:
        """Return the most recent trace IDs."""
        with self._lock:
            return list(reversed(self._trace_order[-limit:]))

    def trace_count(self) -> int:
        with self._lock:
            return len(self._trace_order)

    def clear(self) -> None:
        with self._lock:
            self._traces.clear()
            self._trace_order.clear()
