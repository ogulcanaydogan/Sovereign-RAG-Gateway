import re
from typing import Any, cast

from app.rag.embeddings import EmbeddingGenerator, HashEmbeddingGenerator, vector_literal
from app.rag.types import Document, DocumentChunk

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - import guard
    psycopg = cast(Any, None)
    dict_row = cast(Any, None)

TABLE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class PostgresPgvectorConnector:
    def __init__(
        self,
        dsn: str,
        table: str = "rag_chunks",
        embedding_dim: int = 16,
        connector_name: str = "postgres",
        embedding_generator: EmbeddingGenerator | None = None,
    ):
        if psycopg is None or dict_row is None:
            raise RuntimeError("psycopg is required for Postgres connector")
        if not TABLE_NAME_RE.match(table):
            raise ValueError(f"Invalid table name: {table}")

        self._dsn = dsn
        self._table = table
        self._embedding_dim = embedding_dim
        self._connector_name = connector_name
        self._embedding_generator = embedding_generator or HashEmbeddingGenerator(embedding_dim)

    def search(self, query: str, filters: dict[str, str], k: int) -> list[DocumentChunk]:
        if k < 1:
            return []

        query_vector_values = self._embedding_generator.embed_texts([query])[0]
        if len(query_vector_values) != self._embedding_dim:
            raise RuntimeError(
                f"embedding dimension mismatch for query vector: expected "
                f"{self._embedding_dim}, got {len(query_vector_values)}"
            )
        query_vector = vector_literal(query_vector_values)
        where_clauses: list[str] = []
        params: list[Any] = []

        for key, value in sorted(filters.items()):
            where_clauses.append("metadata ->> %s = %s")
            params.extend([key, value])

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        sql = (
            f"SELECT source_id, uri, chunk_id, text, metadata, "
            f"1 - (embedding <=> %s::vector) AS score "
            f"FROM {self._table} "
            f"{where_sql} "
            f"ORDER BY embedding <=> %s::vector "
            f"LIMIT %s"
        )

        rows: list[dict[str, Any]]
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, [query_vector, *params, query_vector, k])
                rows = list(cursor.fetchall())

        chunks: list[DocumentChunk] = []
        for row in rows:
            metadata = self._parse_metadata(row.get("metadata"))
            score = float(row.get("score", 0.0))
            chunks.append(
                DocumentChunk(
                    source_id=str(row.get("source_id", "")),
                    connector=self._connector_name,
                    uri=str(row.get("uri", "")),
                    chunk_id=str(row.get("chunk_id", "")),
                    text=str(row.get("text", "")),
                    score=round(score, 6),
                    metadata=metadata,
                )
            )
        return chunks

    def fetch(self, doc_id: str) -> Document | None:
        sql = (
            f"SELECT source_id, uri, chunk_id, text, metadata "
            f"FROM {self._table} "
            f"WHERE source_id = %s "
            f"ORDER BY chunk_id"
        )

        rows: list[dict[str, Any]]
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, [doc_id])
                rows = list(cursor.fetchall())

        if not rows:
            return None

        first = rows[0]
        metadata = self._parse_metadata(first.get("metadata"))
        text = "\n".join(str(item.get("text", "")) for item in rows if item.get("text"))
        return Document(
            source_id=doc_id,
            uri=str(first.get("uri", "")),
            text=text,
            metadata=metadata,
        )

    def ensure_schema(self) -> None:
        ddl = f"""
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE TABLE IF NOT EXISTS {self._table} (
            id BIGSERIAL PRIMARY KEY,
            source_id TEXT NOT NULL,
            uri TEXT NOT NULL,
            chunk_id TEXT NOT NULL UNIQUE,
            text TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            embedding VECTOR({self._embedding_dim}) NOT NULL
        );
        """
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(ddl)
            conn.commit()

    @staticmethod
    def _parse_metadata(raw: Any) -> dict[str, str]:
        if not isinstance(raw, dict):
            return {}
        return {str(key): str(value) for key, value in raw.items()}
