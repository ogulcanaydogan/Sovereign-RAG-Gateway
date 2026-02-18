#!/usr/bin/env python3
import argparse
import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from app.rag.embeddings import (
    EmbeddingGenerator,
    HashEmbeddingGenerator,
    HTTPOpenAIEmbeddingGenerator,
    vector_literal,
)

try:
    import psycopg
except ImportError:  # pragma: no cover - import guard
    psycopg = cast(Any, None)

TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def chunk_text(text: str, chunk_size_words: int, overlap_words: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    step = max(chunk_size_words - overlap_words, 1)
    while start < len(words):
        end = start + chunk_size_words
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def build_records(
    input_dir: Path,
    chunk_size_words: int = 120,
    overlap_words: int = 20,
) -> list[dict[str, Any]]:
    supported_extensions = {".txt", ".md"}
    files = sorted(
        path for path in input_dir.rglob("*") if path.suffix.lower() in supported_extensions
    )

    records: list[dict[str, Any]] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        pieces = chunk_text(
            text,
            chunk_size_words=chunk_size_words,
            overlap_words=overlap_words,
        )
        if not pieces:
            continue

        source_id = sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:16]
        uri = path.resolve().as_uri()

        for idx, piece in enumerate(pieces):
            records.append(
                {
                    "source_id": source_id,
                    "uri": uri,
                    "chunk_id": f"{source_id}:{idx}",
                    "text": piece,
                    "metadata": {
                        "file_name": path.name,
                        "extension": path.suffix.lower().lstrip("."),
                    },
                }
            )

    return records


def ingest_directory(
    input_dir: Path,
    output_path: Path,
    chunk_size_words: int = 120,
    overlap_words: int = 20,
) -> int:
    records = build_records(
        input_dir=input_dir,
        chunk_size_words=chunk_size_words,
        overlap_words=overlap_words,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        for record in records:
            output_file.write(json.dumps(record, ensure_ascii=True) + "\n")
    return len(records)


def ingest_to_postgres(
    input_dir: Path,
    dsn: str,
    table: str,
    embedding_dim: int = 16,
    chunk_size_words: int = 120,
    overlap_words: int = 20,
    embedding_generator: EmbeddingGenerator | None = None,
    embedding_batch_size: int = 16,
) -> int:
    if psycopg is None:
        raise RuntimeError("psycopg is required for postgres ingestion")
    if not TABLE_NAME_RE.match(table):
        raise ValueError(f"Invalid table name: {table}")
    if embedding_batch_size < 1:
        raise ValueError("embedding_batch_size must be >= 1")

    records = build_records(
        input_dir=input_dir,
        chunk_size_words=chunk_size_words,
        overlap_words=overlap_words,
    )

    ddl = f"""
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE TABLE IF NOT EXISTS {table} (
      id BIGSERIAL PRIMARY KEY,
      source_id TEXT NOT NULL,
      uri TEXT NOT NULL,
      chunk_id TEXT NOT NULL UNIQUE,
      text TEXT NOT NULL,
      metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
      embedding VECTOR({embedding_dim}) NOT NULL
    );
    """

    generator = embedding_generator or HashEmbeddingGenerator(embedding_dim=embedding_dim)
    texts = [str(record["text"]) for record in records]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), embedding_batch_size):
        batch = texts[start : start + embedding_batch_size]
        batch_vectors = generator.embed_texts(batch)
        if len(batch_vectors) != len(batch):
            raise RuntimeError(
                f"embedding generator returned {len(batch_vectors)} vectors for "
                f"{len(batch)} inputs"
            )
        for vector in batch_vectors:
            if len(vector) != embedding_dim:
                raise RuntimeError(
                    f"embedding dimension mismatch: expected {embedding_dim}, got {len(vector)}"
                )
        vectors.extend(batch_vectors)

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute(ddl)
            for record, vector_values in zip(records, vectors, strict=True):
                vector_value = vector_literal(vector_values)
                cursor.execute(
                    (
                        f"INSERT INTO {table} "
                        "(source_id, uri, chunk_id, text, metadata, embedding) "
                        "VALUES (%s, %s, %s, %s, %s::jsonb, %s::vector) "
                        "ON CONFLICT (chunk_id) DO UPDATE SET "
                        "text = EXCLUDED.text, "
                        "metadata = EXCLUDED.metadata, "
                        "embedding = EXCLUDED.embedding"
                    ),
                    [
                        record["source_id"],
                        record["uri"],
                        record["chunk_id"],
                        record["text"],
                        json.dumps(record["metadata"], ensure_ascii=True),
                        vector_value,
                    ],
                )
        conn.commit()

    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest local docs into retrieval connector indexes"
    )
    parser.add_argument("--input-dir", required=True, help="Directory with .txt/.md source files")
    parser.add_argument(
        "--connector",
        choices=["filesystem", "postgres"],
        default="filesystem",
        help="Target connector backend",
    )
    parser.add_argument(
        "--output",
        default="artifacts/rag/filesystem_index.jsonl",
        help="Output index JSONL path for filesystem connector",
    )
    parser.add_argument("--postgres-dsn", default="", help="Postgres DSN for pgvector ingestion")
    parser.add_argument("--postgres-table", default="rag_chunks", help="Postgres table name")
    parser.add_argument("--embedding-dim", type=int, default=16)
    parser.add_argument(
        "--embedding-source",
        choices=["hash", "http"],
        default="hash",
        help="Embedding source for pgvector indexing",
    )
    parser.add_argument(
        "--embedding-endpoint",
        default="http://127.0.0.1:8000/v1/embeddings",
        help="OpenAI-compatible embeddings endpoint used when source=http",
    )
    parser.add_argument(
        "--embedding-model",
        default="text-embedding-3-small",
        help="Embedding model name for source=http",
    )
    parser.add_argument(
        "--embedding-api-key",
        default="",
        help="Bearer API key for source=http",
    )
    parser.add_argument("--embedding-tenant-id", default="", help="x-srg-tenant-id header")
    parser.add_argument("--embedding-user-id", default="", help="x-srg-user-id header")
    parser.add_argument(
        "--embedding-classification", default="", help="x-srg-classification header"
    )
    parser.add_argument("--embedding-batch-size", type=int, default=16)
    parser.add_argument("--chunk-size-words", type=int, default=120)
    parser.add_argument("--overlap-words", type=int, default=20)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if args.connector == "filesystem":
        count = ingest_directory(
            input_dir=input_dir,
            output_path=Path(args.output),
            chunk_size_words=args.chunk_size_words,
            overlap_words=args.overlap_words,
        )
        print(f"Wrote {count} chunks to {args.output}")
        return

    if not args.postgres_dsn:
        raise SystemExit("--postgres-dsn is required when --connector=postgres")

    embedding_generator: EmbeddingGenerator
    if args.embedding_source == "http":
        embedding_generator = HTTPOpenAIEmbeddingGenerator(
            endpoint=args.embedding_endpoint,
            model=args.embedding_model,
            embedding_dim=args.embedding_dim,
            api_key=args.embedding_api_key or None,
            tenant_id=args.embedding_tenant_id or None,
            user_id=args.embedding_user_id or None,
            classification=args.embedding_classification or None,
        )
    else:
        embedding_generator = HashEmbeddingGenerator(embedding_dim=args.embedding_dim)

    count = ingest_to_postgres(
        input_dir=input_dir,
        dsn=args.postgres_dsn,
        table=args.postgres_table,
        embedding_dim=args.embedding_dim,
        chunk_size_words=args.chunk_size_words,
        overlap_words=args.overlap_words,
        embedding_generator=embedding_generator,
        embedding_batch_size=args.embedding_batch_size,
    )
    print(f"Upserted {count} chunks into {args.postgres_table}")


if __name__ == "__main__":
    main()
