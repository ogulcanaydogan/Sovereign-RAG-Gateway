from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config.settings import clear_settings_cache
from app.main import create_app
from app.rag.connectors.postgres import PostgresPgvectorConnector


def _dsn() -> str:
    return os.getenv("SRG_TEST_POSTGRES_DSN", "")


def _seed_rows(connector: PostgresPgvectorConnector) -> None:
    import psycopg

    dsn = _dsn()
    if not dsn:
        raise RuntimeError("SRG_TEST_POSTGRES_DSN is not set")

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"TRUNCATE TABLE {connector._table}")
            text = "Clinical guideline for triage requires evidence-backed summary"
            vector = connector._vector_literal(connector._text_to_vector(text))
            cursor.execute(
                (
                    f"INSERT INTO {connector._table} "
                    "(source_id, uri, chunk_id, text, metadata, embedding) "
                    "VALUES (%s, %s, %s, %s, %s::jsonb, %s::vector)"
                ),
                [
                    "pg-doc-1",
                    "https://example.org/triage",
                    "pg-doc-1:0",
                    text,
                    json.dumps({"department": "triage"}),
                    vector,
                ],
            )
        conn.commit()


@pytest.mark.skipif(not _dsn(), reason="SRG_TEST_POSTGRES_DSN is not configured")
def test_chat_rag_postgres_includes_citations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    auth_headers: dict[str, str],
) -> None:
    table = f"rag_chunks_app_{uuid4().hex[:8]}"
    connector = PostgresPgvectorConnector(dsn=_dsn(), table=table)
    connector.ensure_schema()
    _seed_rows(connector)

    monkeypatch.setenv("SRG_API_KEYS", "test-key")
    monkeypatch.setenv("SRG_AUDIT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SRG_RAG_POSTGRES_DSN", _dsn())
    monkeypatch.setenv("SRG_RAG_POSTGRES_TABLE", table)
    monkeypatch.setenv("SRG_RAG_ALLOWED_CONNECTORS", "filesystem,postgres")
    monkeypatch.setenv("SRG_OPA_SIMULATE_TIMEOUT", "false")
    clear_settings_cache()

    client = TestClient(create_app())
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "share triage policy"}],
            "rag": {"enabled": True, "connector": "postgres", "top_k": 1},
        },
    )

    assert response.status_code == 200
    body = response.json()
    citations = body["choices"][0]["message"]["citations"]
    assert len(citations) == 1
    assert citations[0]["connector"] == "postgres"
    assert citations[0]["source_id"] == "pg-doc-1"
