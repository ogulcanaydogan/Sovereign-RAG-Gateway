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

import threading
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from time import perf_counter
from typing import Any
from uuid import uuid4


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
        self._start: float = 0.0
        self._span: Span | None = None
        self._events: list[dict[str, Any]] = []

    def __enter__(self) -> "SpanContext":
        self._start = perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        end = perf_counter()
        duration = (end - self._start) * 1000
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
            start_time_ms=round(self._start * 1000, 3),
            end_time_ms=round(end * 1000, 3),
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

    def __init__(self, max_traces: int = 1000) -> None:
        self._max_traces = max_traces
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
        with self._lock:
            self._traces[trace_id].append(span)
            if trace_id not in self._trace_order:
                self._trace_order.append(trace_id)
            # Evict oldest traces if over limit
            while len(self._trace_order) > self._max_traces:
                oldest = self._trace_order.pop(0)
                self._traces.pop(oldest, None)

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
