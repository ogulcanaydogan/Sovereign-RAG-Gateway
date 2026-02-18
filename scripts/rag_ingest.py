#!/usr/bin/env python3
import argparse
import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

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
) -> int:
    if psycopg is None:
        raise RuntimeError("psycopg is required for postgres ingestion")
    if not TABLE_NAME_RE.match(table):
        raise ValueError(f"Invalid table name: {table}")

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

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute(ddl)
            for record in records:
                vector = _vector_literal(_text_to_vector(str(record["text"]), embedding_dim))
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
                        vector,
                    ],
                )
        conn.commit()

    return len(records)


def _text_to_vector(text: str, embedding_dim: int) -> list[float]:
    digest = sha256(text.encode("utf-8")).digest()
    values = [round((byte - 128) / 128.0, 6) for byte in digest[:embedding_dim]]
    if len(values) < embedding_dim:
        values.extend([0.0] * (embedding_dim - len(values)))
    return values


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in values) + "]"


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

    count = ingest_to_postgres(
        input_dir=input_dir,
        dsn=args.postgres_dsn,
        table=args.postgres_table,
        embedding_dim=args.embedding_dim,
        chunk_size_words=args.chunk_size_words,
        overlap_words=args.overlap_words,
    )
    print(f"Upserted {count} chunks into {args.postgres_table}")


if __name__ == "__main__":
    main()
