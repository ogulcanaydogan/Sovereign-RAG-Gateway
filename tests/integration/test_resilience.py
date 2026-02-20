"""Resilience / chaos tests proving fail-closed guarantees under failure.

Each test simulates a specific failure mode and verifies the gateway
responds deterministically without silent data loss.
"""

import json as json_mod
from pathlib import Path

from fastapi.testclient import TestClient

from app.audit.writer import AuditValidationError
from app.budget.tracker import BudgetBackendError
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


def _auth_headers(classification: str = "phi") -> dict[str, str]:
    return {
        "Authorization": "Bearer test-key",
        "x-srg-tenant-id": "tenant-a",
        "x-srg-user-id": "user-1",
        "x-srg-classification": classification,
    }


# ------------------------------------------------------------------ #
# 1. Provider error mid-stream — audit still written
# ------------------------------------------------------------------ #


def test_provider_error_mid_stream_finally_block_runs(
    monkeypatch, tmp_path: Path, capfd
) -> None:
    """StubProvider error-timeout-stream yields one chunk then raises.

    Verify: the streaming finally block still executes (logs
    ``chat_stream_completed``) even when the provider errors mid-stream.
    """
    client = _build_client(
        monkeypatch,
        tmp_path,
        extra_env={"SRG_PROVIDER_FALLBACK_ENABLED": "false"},
    )

    try:
        with client.stream(
            "POST",
            "/v1/chat/completions",
            headers=_auth_headers("public"),
            json={
                "model": "error-timeout-stream",
                "stream": True,
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 8,
            },
        ) as response:
            for _line in response.iter_lines():
                pass
    except Exception:
        pass  # Expected: provider error propagates through ASGI stack

    # The finally block logged chat_stream_completed to stderr
    captured = capfd.readouterr()
    assert "chat_stream_completed" in captured.err


# ------------------------------------------------------------------ #
# 2. Budget backend unavailable — fail-closed 503
# ------------------------------------------------------------------ #


def test_budget_backend_unavailable_returns_503(monkeypatch, tmp_path: Path) -> None:
    """Budget check raises BudgetBackendError → gateway returns 503."""
    client = _build_client(
        monkeypatch,
        tmp_path,
        extra_env={
            "SRG_BUDGET_ENABLED": "true",
            "SRG_BUDGET_DEFAULT_CEILING": "10000",
        },
    )
    service = client.app.state.chat_service

    def _failing_check(tenant_id: str, requested_tokens: int) -> None:
        raise BudgetBackendError("Redis connection refused")

    service._budget_tracker.check = _failing_check  # type: ignore[union-attr]

    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers("public"),
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 8,
        },
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "budget_backend_unavailable"


# ------------------------------------------------------------------ #
# 3. All providers exhausted in fallback chain
# ------------------------------------------------------------------ #


def test_all_providers_exhausted_returns_502(monkeypatch, tmp_path: Path) -> None:
    """Every provider returns 502 → client gets the final error."""
    client = _build_client(monkeypatch, tmp_path)

    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers("public"),
        json={
            "model": "error-502-exhaust",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 8,
        },
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_bad_gateway"


# ------------------------------------------------------------------ #
# 4. OPA timeout in enforce mode — fail-closed 503
# ------------------------------------------------------------------ #


def test_opa_timeout_enforce_mode_returns_503(monkeypatch, tmp_path: Path) -> None:
    """OPA simulated timeout with enforce mode → 503 policy_unavailable."""
    client = _build_client(
        monkeypatch,
        tmp_path,
        extra_env={"SRG_OPA_SIMULATE_TIMEOUT": "true"},
    )

    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers("public"),
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 8,
        },
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "policy_unavailable"


# ------------------------------------------------------------------ #
# 5. Sequential budget exhaustion — accounting correctness
# ------------------------------------------------------------------ #


def test_sequential_budget_exhaustion(monkeypatch, tmp_path: Path) -> None:
    """First request within ceiling → 200, second exceeds → 429.

    Demonstrates budget accounting tracks actual usage across requests.
    """
    client = _build_client(
        monkeypatch,
        tmp_path,
        extra_env={
            "SRG_BUDGET_ENABLED": "true",
            "SRG_BUDGET_DEFAULT_CEILING": "20",
        },
    )

    # First request: estimate = prompt_words(~1) + max_tokens(16) = 17 ≤ 20 → passes
    r1 = client.post(
        "/v1/chat/completions",
        headers=_auth_headers("public"),
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 16,
        },
    )
    assert r1.status_code == 200

    # Second request: recorded(4) + estimate(17) = 21 > 20 → 429
    r2 = client.post(
        "/v1/chat/completions",
        headers=_auth_headers("public"),
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 16,
        },
    )
    assert r2.status_code == 429
    assert r2.json()["error"]["code"] == "budget_exceeded"


# ------------------------------------------------------------------ #
# 6. Webhook endpoint unreachable — request still succeeds
# ------------------------------------------------------------------ #


def test_webhook_unreachable_request_succeeds(monkeypatch, tmp_path: Path) -> None:
    """Webhook delivery failure does not block the primary request."""
    client = _build_client(
        monkeypatch,
        tmp_path,
        extra_env={
            "SRG_WEBHOOK_ENABLED": "true",
            "SRG_WEBHOOK_ENDPOINTS": json_mod.dumps(
                [
                    {
                        "url": "http://127.0.0.1:19999/unreachable",
                        "secret": "test",
                        "event_types": ["redaction_hit"],
                    }
                ]
            ),
            "SRG_WEBHOOK_TIMEOUT_S": "0.5",
            "SRG_WEBHOOK_MAX_RETRIES": "0",
        },
    )

    # PHI message triggers redaction → redaction_hit webhook event
    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers("phi"),
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "DOB 01/01/1990 SSN 123-45-6789"}],
            "max_tokens": 8,
        },
    )
    # Primary request succeeds despite webhook failure
    assert response.status_code == 200


# ------------------------------------------------------------------ #
# 7a. Audit write failure (non-streaming) — 502
# ------------------------------------------------------------------ #


def test_audit_write_failure_non_streaming_returns_502(
    monkeypatch, tmp_path: Path
) -> None:
    """Non-streaming audit failure → 502 audit_write_failed."""
    client = _build_client(monkeypatch, tmp_path)
    service = client.app.state.chat_service

    def _failing_write(event: dict) -> None:
        raise AuditValidationError("Simulated audit failure")

    service._audit_writer.write_event = _failing_write  # type: ignore[assignment]

    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers("public"),
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 8,
        },
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "audit_write_failed"


# ------------------------------------------------------------------ #
# 7b. Audit write failure (streaming) — stream completes normally
# ------------------------------------------------------------------ #


def test_audit_write_failure_streaming_completes(monkeypatch, tmp_path: Path) -> None:
    """Streaming audit failure is logged but does not crash the stream."""
    client = _build_client(monkeypatch, tmp_path)
    service = client.app.state.chat_service

    def _failing_write(event: dict) -> None:
        raise AuditValidationError("Simulated audit failure")

    service._audit_writer.write_event = _failing_write  # type: ignore[assignment]

    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers=_auth_headers("public"),
        json={
            "model": "gpt-4o-mini",
            "stream": True,
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 8,
        },
    ) as response:
        assert response.status_code == 200
        lines = [line for line in response.iter_lines() if line]

    assert lines[-1] == "data: [DONE]"
