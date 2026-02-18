from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from app.rag.connectors.postgres import PostgresPgvectorConnector
from scripts.rag_ingest import ingest_to_postgres


def _dsn() -> str:
    return os.getenv("SRG_TEST_POSTGRES_DSN", "")


@pytest.mark.skipif(not _dsn(), reason="SRG_TEST_POSTGRES_DSN is not configured")
def test_rag_ingest_to_postgres(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir(parents=True)
    (corpus / "note.txt").write_text(
        "Patient has chest discomfort and requires follow-up.",
        encoding="utf-8",
    )

    table = f"rag_chunks_ingest_{uuid4().hex[:8]}"
    count = ingest_to_postgres(
        input_dir=corpus,
        dsn=_dsn(),
        table=table,
        embedding_dim=16,
        chunk_size_words=20,
        overlap_words=0,
    )

    assert count == 1

    connector = PostgresPgvectorConnector(dsn=_dsn(), table=table)
    fetched = connector.fetch("non-existent")
    assert fetched is None

    chunks = connector.search(query="chest discomfort", filters={}, k=1)
    assert len(chunks) == 1
    assert chunks[0].connector == "postgres"
