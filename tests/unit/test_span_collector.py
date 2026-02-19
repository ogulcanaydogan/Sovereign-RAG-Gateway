from app.telemetry.tracing import OTLPHTTPTraceExporter, Span, SpanCollector


def test_span_collector_records_spans() -> None:
    collector = SpanCollector(max_traces=10)

    with collector.span(
        trace_id="req-1",
        operation="gateway.request",
        attributes={"endpoint": "/v1/chat/completions"},
    ):
        pass

    trace = collector.get_trace("req-1")
    assert len(trace) == 1
    assert trace[0]["operation"] == "gateway.request"
    assert trace[0]["attributes"]["endpoint"] == "/v1/chat/completions"


def test_span_collector_evicts_oldest_trace() -> None:
    collector = SpanCollector(max_traces=1)

    with collector.span(trace_id="req-1", operation="gateway.request"):
        pass
    with collector.span(trace_id="req-2", operation="gateway.request"):
        pass

    assert collector.get_trace("req-1") == []
    assert len(collector.get_trace("req-2")) == 1


def test_span_context_add_event_records_during_active_span() -> None:
    collector = SpanCollector(max_traces=10)

    with collector.span(trace_id="req-events", operation="policy.evaluate") as span:
        span.add_event("policy.input_built", {"tenant_id": "tenant-a"})

    trace = collector.get_trace("req-events")
    assert len(trace) == 1
    assert trace[0]["events"] == [
        {
            "name": "policy.input_built",
            "attributes": {"tenant_id": "tenant-a"},
        }
    ]


def test_span_collector_exports_trace_on_root_span_completion() -> None:
    exported: list[tuple[str, int]] = []

    class _Exporter:
        def export_trace(self, trace_id: str, spans: list[Span]) -> None:
            exported.append((trace_id, len(spans)))

    collector = SpanCollector(max_traces=10, exporter=_Exporter())

    with collector.span(trace_id="req-otlp", operation="gateway.request"):
        with collector.span(trace_id="req-otlp", operation="policy.evaluate"):
            pass

    assert exported == [("req-otlp", 2)]


def test_otlp_http_exporter_posts_otlp_json(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Response:
        status_code = 200
        text = ""

    def fake_post(url, *, headers, json, timeout):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("app.telemetry.tracing.httpx.post", fake_post)

    exporter = OTLPHTTPTraceExporter(
        endpoint="http://otel-collector:4318/v1/traces",
        timeout_s=1.5,
        headers={"Authorization": "Bearer token"},
        service_name="srg-test",
    )
    exporter.export_trace(
        trace_id="req-1",
        spans=[
            Span(
                trace_id="req-1",
                span_id="1234567890abcdef",
                parent_span_id=None,
                operation="gateway.request",
                start_time_ms=1000.0,
                end_time_ms=1200.0,
                duration_ms=200.0,
                attributes={"tenant_id": "tenant-a"},
            )
        ],
    )

    payload = captured["json"]
    assert captured["url"] == "http://otel-collector:4318/v1/traces"
    assert captured["timeout"] == 1.5
    assert isinstance(payload, dict)
    resource_spans = payload["resourceSpans"]  # type: ignore[index]
    assert resource_spans
