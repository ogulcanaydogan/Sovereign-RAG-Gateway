"""Integration tests for mid-stream budget enforcement during streaming."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config.settings import clear_settings_cache
from app.main import create_app


def _build_client(
    monkeypatch,
    tmp_path: Path,
    extra_env: dict[str, str] | None = None,
) -> TestClient:
    monkeypatch.setenv("SRG_API_KEYS", "test-key")
    monkeypatch.setenv("SRG_AUDIT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SRG_OPA_SIMULATE_TIMEOUT", "false")
    if extra_env:
        for key, value in extra_env.items():
            monkeypatch.setenv(key, value)
    clear_settings_cache()
    return TestClient(create_app())


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer test-key",
        "x-srg-tenant-id": "tenant-a",
        "x-srg-user-id": "user-1",
        "x-srg-classification": "public",
    }


def test_streaming_mid_stream_budget_termination(monkeypatch, tmp_path: Path) -> None:
    """Stream starts normally but check_running returns False mid-stream.

    The mid-stream budget check fires every 5 chunks.  We patch
    ``check_running`` to return False on the first call so the stream
    is terminated with ``finish_reason="length"`` and audited with
    ``budget_mid_stream_terminated=True``.

    Pre-check passes because the ceiling is generous (500).  Only the
    mid-stream running check is patched to simulate budget exhaustion.
    """
    client = _build_client(
        monkeypatch,
        tmp_path,
        extra_env={
            "SRG_BUDGET_ENABLED": "true",
            "SRG_BUDGET_DEFAULT_CEILING": "500",
        },
    )

    # Patch check_running to always deny — simulates budget exceeded mid-stream
    service = client.app.state.chat_service
    service._budget_tracker.check_running = lambda t, a: False  # type: ignore[assignment]

    # Long message so the stub produces 5+ streamed chunks (120 chars echo,
    # 32-char chunk_size → 5 pieces).  Pre-check estimate = 20+8 = 28 ≤ 500.
    message = (
        "alpha bravo charlie delta echo foxtrot golf hotel "
        "india juliet kilo lima mike november oscar papa "
        "quebec romeo sierra tango"
    )

    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers=_auth_headers(),
        json={
            "model": "gpt-4o-mini",
            "stream": True,
            "messages": [{"role": "user", "content": message}],
            "max_tokens": 8,
        },
    ) as response:
        assert response.status_code == 200
        lines = [line for line in response.iter_lines() if line]

    # Stream should end properly with [DONE]
    assert lines[-1] == "data: [DONE]"

    # At least one chunk should have finish_reason="length" (budget termination)
    data_lines = [
        json.loads(line.removeprefix("data: "))
        for line in lines
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    finish_reasons = [
        choice.get("finish_reason")
        for chunk in data_lines
        for choice in chunk.get("choices", [])
        if choice.get("finish_reason")
    ]
    assert "length" in finish_reasons

    # Verify audit event
    audit_path = tmp_path / "events.jsonl"
    events = [
        json.loads(line)
        for line in audit_path.read_text().splitlines()
        if line.strip()
    ]
    stream_events = [e for e in events if e.get("streaming") is True]
    assert stream_events
    assert stream_events[-1].get("budget_mid_stream_terminated") is True
