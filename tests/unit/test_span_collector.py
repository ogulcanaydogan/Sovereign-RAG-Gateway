from app.telemetry.tracing import SpanCollector


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

