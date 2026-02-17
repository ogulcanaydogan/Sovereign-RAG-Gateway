import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config.settings import clear_settings_cache
from app.main import create_app


def write_index(path: Path) -> None:
    row = {
        "source_id": "doc-1",
        "uri": "file:///tmp/doc-1.txt",
        "chunk_id": "doc-1:0",
        "text": "Clinical guideline: summarize without identifiers.",
        "metadata": {"department": "triage"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_chat_rag_includes_citations(monkeypatch, tmp_path: Path, auth_headers) -> None:
    index_path = tmp_path / "index.jsonl"
    write_index(index_path)

    monkeypatch.setenv("SRG_API_KEYS", "test-key")
    monkeypatch.setenv("SRG_AUDIT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SRG_RAG_FILESYSTEM_INDEX_PATH", str(index_path))
    monkeypatch.setenv("SRG_RAG_ALLOWED_CONNECTORS", "filesystem")
    monkeypatch.setenv("SRG_OPA_SIMULATE_TIMEOUT", "false")
    clear_settings_cache()

    client = TestClient(create_app())
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "share triage guidance"}],
            "rag": {"enabled": True, "connector": "filesystem", "top_k": 1},
        },
    )

    assert response.status_code == 200
    body = response.json()
    citations = body["choices"][0]["message"]["citations"]
    assert len(citations) == 1
    assert citations[0]["connector"] == "filesystem"
    assert citations[0]["source_id"] == "doc-1"


def test_chat_rag_denies_unknown_connector(monkeypatch, tmp_path: Path, auth_headers) -> None:
    index_path = tmp_path / "index.jsonl"
    write_index(index_path)

    monkeypatch.setenv("SRG_API_KEYS", "test-key")
    monkeypatch.setenv("SRG_AUDIT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SRG_RAG_FILESYSTEM_INDEX_PATH", str(index_path))
    monkeypatch.setenv("SRG_RAG_ALLOWED_CONNECTORS", "filesystem")
    monkeypatch.setenv("SRG_OPA_SIMULATE_TIMEOUT", "false")
    clear_settings_cache()

    client = TestClient(create_app())
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "share triage guidance"}],
            "rag": {"enabled": True, "connector": "restricted-store", "top_k": 1},
        },
    )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "policy_denied"
