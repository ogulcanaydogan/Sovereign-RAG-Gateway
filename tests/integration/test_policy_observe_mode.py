from pathlib import Path

from fastapi.testclient import TestClient

from app.config.settings import clear_settings_cache
from app.main import create_app


def test_observe_mode_allows_request_even_if_policy_would_deny(
    monkeypatch, tmp_path: Path, auth_headers
) -> None:
    monkeypatch.setenv("SRG_API_KEYS", "test-key")
    monkeypatch.setenv("SRG_AUDIT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SRG_OPA_MODE", "observe")
    monkeypatch.setenv("SRG_OPA_SIMULATE_TIMEOUT", "false")
    clear_settings_cache()

    client = TestClient(create_app())
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "forbidden-model",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "chat.completion"
