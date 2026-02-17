from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config.settings import clear_settings_cache
from app.main import create_app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("SRG_API_KEYS", "test-key")
    monkeypatch.setenv("SRG_AUDIT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SRG_OPA_SIMULATE_TIMEOUT", "false")
    clear_settings_cache()
    app = create_app()
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer test-key",
        "x-srg-tenant-id": "tenant-a",
        "x-srg-user-id": "user-1",
        "x-srg-classification": "phi",
    }
