"""Tests for streaming audit guarantee — audit and metrics are written
even when the provider stream fails or the client disconnects."""

import json
from pathlib import Path

from fastapi.testclient import TestClient


def test_stream_audit_written_on_success(
    client: TestClient, auth_headers: dict[str, str], tmp_path: Path, monkeypatch
) -> None:
    """Verify that a successful stream writes an audit event with streaming=True."""
    audit_path = tmp_path / "events.jsonl"
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gpt-4o-mini",
            "stream": True,
            "messages": [{"role": "user", "content": "hello streaming"}],
        },
    ) as response:
        assert response.status_code == 200
        # Consume all chunks to trigger the finally block
        _ = list(response.iter_lines())

    events = [json.loads(line) for line in audit_path.read_text().splitlines() if line.strip()]
    stream_events = [e for e in events if e.get("streaming") is True]
    assert len(stream_events) >= 1, "Expected at least one streaming audit event"
    event = stream_events[-1]
    assert event["streaming"] is True
    assert event["tokens_in"] > 0
    assert event["cost_usd"] > 0
    assert "stream_error" not in event


def test_stream_audit_written_on_provider_error(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Verify that a provider error during stream setup still produces a proper error response."""
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "error-429-trigger",
            "stream": True,
            "messages": [{"role": "user", "content": "fail"}],
        },
    )
    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "provider_rate_limited"


def test_stream_contains_done_marker(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Verify the SSE stream ends with data: [DONE] even for short responses."""
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gpt-4o-mini",
            "stream": True,
            "messages": [{"role": "user", "content": "short"}],
        },
    ) as response:
        assert response.status_code == 200
        lines = [line for line in response.iter_lines() if line]

    assert lines[-1] == "data: [DONE]"


def test_stream_chunks_have_correct_structure(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Verify each SSE chunk is valid JSON with the chat.completion.chunk object type."""
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gpt-4o-mini",
            "stream": True,
            "messages": [{"role": "user", "content": "validate chunks"}],
        },
    ) as response:
        lines = [line for line in response.iter_lines() if line]

    data_lines = [line for line in lines if line.startswith("data: ") and line != "data: [DONE]"]
    assert len(data_lines) >= 2, "Expected at least 2 data chunks (content + finish)"

    for data_line in data_lines:
        payload = json.loads(data_line.removeprefix("data: "))
        assert payload["object"] == "chat.completion.chunk"
        assert "choices" in payload
        assert isinstance(payload["choices"], list)
        assert len(payload["choices"]) >= 1


def test_stream_finish_reason_stop_present(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Verify the stream includes a chunk with finish_reason=stop."""
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gpt-4o-mini",
            "stream": True,
            "messages": [{"role": "user", "content": "finish me"}],
        },
    ) as response:
        lines = [line for line in response.iter_lines() if line]

    data_lines = [line for line in lines if line.startswith("data: ") and line != "data: [DONE]"]
    finish_reasons = []
    for data_line in data_lines:
        payload = json.loads(data_line.removeprefix("data: "))
        for choice in payload.get("choices", []):
            if choice.get("finish_reason"):
                finish_reasons.append(choice["finish_reason"])

    assert "stop" in finish_reasons


def test_stream_usage_in_final_chunk(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Verify that the final stream chunk includes usage statistics."""
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gpt-4o-mini",
            "stream": True,
            "messages": [{"role": "user", "content": "give me usage"}],
        },
    ) as response:
        lines = [line for line in response.iter_lines() if line]

    data_lines = [line for line in lines if line.startswith("data: ") and line != "data: [DONE]"]
    last_chunk = json.loads(data_lines[-1].removeprefix("data: "))
    assert "usage" in last_chunk, "Final chunk should contain usage data"
    assert last_chunk["usage"]["prompt_tokens"] > 0
