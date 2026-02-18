import json
from pathlib import Path

import pytest

from app.rag.embeddings import EmbeddingGenerator
from scripts.rag_ingest import chunk_text, ingest_directory, ingest_to_postgres


def test_chunk_text_with_overlap() -> None:
    text = "one two three four five six"
    chunks = chunk_text(text, chunk_size_words=3, overlap_words=1)

    assert chunks == ["one two three", "three four five", "five six"]


def test_ingest_directory_emits_jsonl(tmp_path: Path) -> None:
    source_dir = tmp_path / "corpus"
    source_dir.mkdir(parents=True)
    (source_dir / "doc.txt").write_text("alpha beta gamma delta", encoding="utf-8")

    output = tmp_path / "index.jsonl"
    count = ingest_directory(source_dir, output, chunk_size_words=2, overlap_words=0)

    assert count == 2
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["source_id"]
    assert rows[0]["chunk_id"].endswith(":0")


class _BadEmbeddingGenerator(EmbeddingGenerator):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [[0.1, 0.2]]


def test_ingest_to_postgres_validates_embedding_batch_size(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ingest_to_postgres(
            input_dir=tmp_path,
            dsn="postgresql://localhost:5432/test",
            table="rag_chunks",
            embedding_batch_size=0,
        )


def test_ingest_to_postgres_rejects_embedding_dim_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("scripts.rag_ingest.psycopg", object())
    source_dir = tmp_path / "corpus"
    source_dir.mkdir(parents=True)
    (source_dir / "doc.txt").write_text("alpha beta gamma", encoding="utf-8")

    class _FakeCursor:
        def __enter__(self) -> "_FakeCursor":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, *_: object, **__: object) -> None:
            return None

    class _FakeConn:
        def __enter__(self) -> "_FakeConn":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def cursor(self) -> _FakeCursor:
            return _FakeCursor()

        def commit(self) -> None:
            return None

    class _FakePsycopg:
        @staticmethod
        def connect(_: str) -> _FakeConn:
            return _FakeConn()

    monkeypatch.setattr("scripts.rag_ingest.psycopg", _FakePsycopg())

    with pytest.raises(RuntimeError, match="embedding dimension mismatch"):
        ingest_to_postgres(
            input_dir=source_dir,
            dsn="postgresql://localhost:5432/test",
            table="rag_chunks",
            embedding_dim=16,
            embedding_generator=_BadEmbeddingGenerator(),
        )
