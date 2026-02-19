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
        "x-srg-classification": "phi",
    }


def test_budget_enforcement_deny_returns_429(monkeypatch, tmp_path: Path) -> None:
    client = _build_client(
        monkeypatch,
        tmp_path,
        extra_env={
            "SRG_BUDGET_ENABLED": "true",
            "SRG_BUDGET_DEFAULT_CEILING": "10",
        },
    )
    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers(),
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 64,
        },
    )
    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "budget_exceeded"

    log_path = Path(str(client.app.state.chat_service._settings.audit_log_path))
    rows = log_path.read_text(encoding="utf-8").splitlines()
    assert rows
    payload = json.loads(rows[-1])
    assert payload["provider"] == "budget-gate"
    assert payload["deny_reason"] == "budget_exceeded"
    assert payload["budget"]["ceiling"] == 10


def test_budget_usage_recorded_on_success(monkeypatch, tmp_path: Path) -> None:
    client = _build_client(
        monkeypatch,
        tmp_path,
        extra_env={
            "SRG_BUDGET_ENABLED": "true",
            "SRG_BUDGET_DEFAULT_CEILING": "1000",
        },
    )
    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers(),
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 8,
        },
    )
    assert response.status_code == 200
    summary = client.app.state.chat_service._budget_tracker.summary("tenant-a")
    assert int(summary["used"]) > 0
    assert int(summary["remaining"]) < int(summary["ceiling"])


def test_response_redaction_masks_provider_output(monkeypatch, tmp_path: Path) -> None:
    client = _build_client(
        monkeypatch,
        tmp_path,
        extra_env={"SRG_PROVIDER_FALLBACK_ENABLED": "false"},
    )

    async def fake_chat(model: str, messages: list[dict[str, str]], max_tokens: int | None):
        _ = model, messages, max_tokens
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Patient SSN 123-45-6789"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
        }

    service = client.app.state.chat_service
    service._provider_registry = None
    service._provider.chat = fake_chat  # type: ignore[method-assign]

    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers(),
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 200
    content = response.json()["choices"][0]["message"]["content"]
    assert "123-45-6789" not in content
    assert "[SSN_REDACTED]" in content

    log_path = Path(str(service._settings.audit_log_path))
    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert payload["output_redaction_count"] >= 1


def test_webhook_trigger_redaction_hit(monkeypatch, tmp_path: Path) -> None:
    client = _build_client(monkeypatch, tmp_path)
    events: list[str] = []
    service = client.app.state.chat_service

    def fake_queue(event_type, payload, webhook_events=None):  # type: ignore[no-untyped-def]
        _ = payload
        events.append(event_type.value)
        if webhook_events is not None:
            webhook_events.append({"event_type": event_type.value, "delivery_success_count": None})

    service._queue_webhook_event = fake_queue  # type: ignore[method-assign]

    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers(),
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "DOB 01/01/1990"}],
            "max_tokens": 8,
        },
    )
    assert response.status_code == 200
    assert "redaction_hit" in events


def test_trace_endpoint_returns_required_spans(monkeypatch, tmp_path: Path) -> None:
    client = _build_client(
        monkeypatch,
        tmp_path,
        extra_env={"SRG_TRACING_ENABLED": "true"},
    )
    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers(),
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 8,
        },
    )
    assert response.status_code == 200
    request_id = response.headers["x-request-id"]

    trace_response = client.get(f"/v1/traces/{request_id}", headers=_auth_headers())
    assert trace_response.status_code == 200
    body = trace_response.json()
    operations = {span["operation"] for span in body["spans"]}
    assert {"gateway.request", "policy.evaluate", "provider.call", "audit.persist"} <= operations


def test_otlp_exporter_posts_trace_when_enabled(monkeypatch, tmp_path: Path) -> None:
    captured: list[dict[str, object]] = []

    class _Response:
        status_code = 200
        text = ""

    def fake_post(url, *, headers, json, timeout):  # type: ignore[no-untyped-def]
        captured.append(
            {"url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        return _Response()

    monkeypatch.setattr("app.telemetry.tracing.httpx.post", fake_post)

    client = _build_client(
        monkeypatch,
        tmp_path,
        extra_env={
            "SRG_TRACING_ENABLED": "true",
            "SRG_TRACING_OTLP_ENABLED": "true",
            "SRG_TRACING_OTLP_ENDPOINT": "http://otel-collector:4318/v1/traces",
            "SRG_TRACING_OTLP_TIMEOUT_S": "1.5",
        },
    )
    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers(),
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 8,
        },
    )
    assert response.status_code == 200
    assert captured
    assert captured[0]["url"] == "http://otel-collector:4318/v1/traces"
