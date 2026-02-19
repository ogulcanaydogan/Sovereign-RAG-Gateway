from pathlib import Path

from fastapi.testclient import TestClient

from app.config.settings import clear_settings_cache
from app.main import create_app


def test_chat_rag_sharepoint_includes_citations(
    monkeypatch,
    tmp_path: Path,
    auth_headers: dict[str, str],
) -> None:
    monkeypatch.setenv("SRG_API_KEYS", "test-key")
    monkeypatch.setenv("SRG_AUDIT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SRG_RAG_ALLOWED_CONNECTORS", "filesystem,sharepoint")
    monkeypatch.setenv("SRG_RAG_SHAREPOINT_SITE_ID", "site-id")
    monkeypatch.setenv("SRG_RAG_SHAREPOINT_BEARER_TOKEN", "token")
    monkeypatch.setenv("SRG_OPA_SIMULATE_TIMEOUT", "false")

    def fake_search_records(self, query: str):  # type: ignore[no-untyped-def]
        _ = query
        return [
            {
                "source_id": "sp-doc-1",
                "uri": "https://contoso.sharepoint.com/sites/ops/Shared%20Documents/doc1",
                "text": "Incident response runbook for provider throttling",
                "metadata": {
                    "name": "runbook.md",
                    "path": "/drives/drive-1/root:/Ops/Runbooks",
                },
            }
        ]

    monkeypatch.setattr(
        "app.rag.connectors.sharepoint.SharePointConnector._search_records",
        fake_search_records,
    )

    clear_settings_cache()
    client = TestClient(create_app())
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "share incident runbook summary"}],
            "rag": {"enabled": True, "connector": "sharepoint", "top_k": 1},
        },
    )

    assert response.status_code == 200
    body = response.json()
    citations = body["choices"][0]["message"]["citations"]
    assert len(citations) == 1
    assert citations[0]["connector"] == "sharepoint"
    assert citations[0]["source_id"] == "sp-doc-1"
