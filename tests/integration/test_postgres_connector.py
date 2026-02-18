from __future__ import annotations

import json
import os
from uuid import uuid4

import pytest

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
            rows = [
                {
                    "source_id": "pg-doc-a",
                    "uri": "https://example.org/a",
                    "chunk_id": "pg-doc-a:0",
                    "text": "Patient has chest discomfort and requires cardiology follow-up",
                    "metadata": {"department": "cardiology"},
                },
                {
                    "source_id": "pg-doc-b",
                    "uri": "https://example.org/b",
                    "chunk_id": "pg-doc-b:0",
                    "text": "Discharge instructions include hydration and rest",
                    "metadata": {"department": "general"},
                },
            ]
            for row in rows:
                vector = connector._vector_literal(connector._text_to_vector(row["text"]))
                cursor.execute(
                    (
                        f"INSERT INTO {connector._table} "
                        "(source_id, uri, chunk_id, text, metadata, embedding) "
                        "VALUES (%s, %s, %s, %s, %s::jsonb, %s::vector)"
                    ),
                    [
                        row["source_id"],
                        row["uri"],
                        row["chunk_id"],
                        row["text"],
                        json.dumps(row["metadata"]),
                        vector,
                    ],
                )
        conn.commit()


@pytest.mark.skipif(not _dsn(), reason="SRG_TEST_POSTGRES_DSN is not configured")
def test_postgres_connector_search_and_fetch() -> None:
    table = f"rag_chunks_test_{uuid4().hex[:8]}"
    connector = PostgresPgvectorConnector(dsn=_dsn(), table=table)
    connector.ensure_schema()
    _seed_rows(connector)

    chunks = connector.search(
        query="cardiology follow-up",
        filters={"department": "cardiology"},
        k=2,
    )

    assert chunks
    assert chunks[0].connector == "postgres"
    assert chunks[0].source_id == "pg-doc-a"

    fetched = connector.fetch("pg-doc-a")
    assert fetched is not None
    assert fetched.source_id == "pg-doc-a"
    assert "cardiology" in fetched.text
