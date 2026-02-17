from pathlib import Path

from fastapi.testclient import TestClient

from app.config.settings import clear_settings_cache
from app.main import create_app


def test_policy_timeout_fail_closed(monkeypatch, tmp_path: Path, auth_headers) -> None:
    monkeypatch.setenv("SRG_API_KEYS", "test-key")
    monkeypatch.setenv("SRG_AUDIT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SRG_OPA_SIMULATE_TIMEOUT", "true")
    clear_settings_cache()

    client = TestClient(create_app())
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "policy_unavailable"
