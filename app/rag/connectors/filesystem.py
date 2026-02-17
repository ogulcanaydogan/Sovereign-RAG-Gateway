import json
import re
from pathlib import Path
from typing import Any

from app.rag.types import Document, DocumentChunk

TOKEN_SPLIT_RE = re.compile(r"\W+")


class FilesystemConnector:
    def __init__(self, index_path: Path, connector_name: str = "filesystem"):
        self._index_path = index_path
        self._connector_name = connector_name

    def search(self, query: str, filters: dict[str, str], k: int) -> list[DocumentChunk]:
        if k < 1:
            return []

        query_tokens = self._tokens(query)
        records = self._load_records()

        ranked: list[DocumentChunk] = []
        for record in records:
            metadata = self._parse_metadata(record.get("metadata"))
            if not self._matches_filters(metadata, filters):
                continue

            chunk_text = str(record.get("text", "")).strip()
            if not chunk_text:
                continue

            chunk_tokens = self._tokens(chunk_text)
            overlap = len(query_tokens.intersection(chunk_tokens))
            if query_tokens:
                score = overlap / len(query_tokens)
            else:
                score = 0.0

            ranked.append(
                DocumentChunk(
                    source_id=str(record.get("source_id", "")),
                    connector=self._connector_name,
                    uri=str(record.get("uri", "")),
                    chunk_id=str(record.get("chunk_id", "")),
                    text=chunk_text,
                    score=round(score, 6),
                    metadata=metadata,
                )
            )

        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:k]

    def fetch(self, doc_id: str) -> Document | None:
        records = [
            entry
            for entry in self._load_records()
            if str(entry.get("source_id", "")) == doc_id
        ]
        if not records:
            return None

        first = records[0]
        uri = str(first.get("uri", ""))
        metadata = self._parse_metadata(first.get("metadata"))
        text = "\n".join(str(item.get("text", "")) for item in records if item.get("text"))

        return Document(source_id=doc_id, uri=uri, text=text, metadata=metadata)

    def _load_records(self) -> list[dict[str, Any]]:
        if not self._index_path.exists():
            return []

        records: list[dict[str, Any]] = []
        with self._index_path.open("r", encoding="utf-8") as file_handle:
            for raw_line in file_handle:
                line = raw_line.strip()
                if not line:
                    continue
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    records.append(parsed)
        return records

    @staticmethod
    def _matches_filters(metadata: dict[str, str], filters: dict[str, str]) -> bool:
        for key, expected in filters.items():
            if metadata.get(key) != expected:
                return False
        return True

    @staticmethod
    def _parse_metadata(raw: Any) -> dict[str, str]:
        if not isinstance(raw, dict):
            return {}
        parsed: dict[str, str] = {}
        for key, value in raw.items():
            parsed[str(key)] = str(value)
        return parsed

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in TOKEN_SPLIT_RE.split(text.lower()) if token}
