import importlib
import json
import re
from time import monotonic
from typing import Any

from app.rag.types import Document, DocumentChunk

TOKEN_SPLIT_RE = re.compile(r"\W+")

boto3: Any | None
try:  # pragma: no cover - optional dependency
    boto3 = importlib.import_module("boto3")
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    boto3 = None


class S3Connector:
    """Connector backed by a JSONL index stored in S3."""

    def __init__(
        self,
        bucket: str,
        index_key: str,
        connector_name: str = "s3",
        region: str | None = None,
        endpoint_url: str | None = None,
        cache_ttl_seconds: float = 30.0,
        s3_client: Any | None = None,
    ):
        if s3_client is None:
            if boto3 is None:
                raise RuntimeError("boto3 is required for S3 connector")
            kwargs: dict[str, str] = {}
            if region:
                kwargs["region_name"] = region
            if endpoint_url:
                kwargs["endpoint_url"] = endpoint_url
            s3_client = boto3.client("s3", **kwargs)

        self._bucket = bucket
        self._index_key = index_key
        self._connector_name = connector_name
        self._s3 = s3_client
        self._cache_ttl_seconds = max(cache_ttl_seconds, 0.0)
        self._cache_records: list[dict[str, Any]] | None = None
        self._cache_loaded_at = 0.0

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
            score = overlap / len(query_tokens) if query_tokens else 0.0

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
        rows = [
            entry
            for entry in self._load_records()
            if str(entry.get("source_id", "")) == doc_id
        ]
        if not rows:
            return None

        first = rows[0]
        text = "\n".join(str(item.get("text", "")) for item in rows if item.get("text"))
        return Document(
            source_id=doc_id,
            uri=str(first.get("uri", "")),
            text=text,
            metadata=self._parse_metadata(first.get("metadata")),
        )

    def _load_records(self) -> list[dict[str, Any]]:
        now = monotonic()
        if (
            self._cache_records is not None
            and self._cache_ttl_seconds > 0
            and (now - self._cache_loaded_at) < self._cache_ttl_seconds
        ):
            return self._cache_records

        records = self._refresh_records()
        if records or self._cache_records is None:
            self._cache_records = records
            self._cache_loaded_at = now
        return self._cache_records

    def _refresh_records(self) -> list[dict[str, Any]]:
        object_keys = self._list_index_keys()
        if not object_keys:
            return []

        records: list[dict[str, Any]] = []
        for object_key in object_keys:
            text = self._read_object_text(object_key)
            if text == "":
                continue
            records.extend(self._parse_jsonl_records(text))
        return records

    def _list_index_keys(self) -> list[str]:
        if not self._index_key.endswith("/"):
            return [self._index_key]

        keys: list[str] = []
        continuation_token: str | None = None
        while True:
            kwargs: dict[str, object] = {
                "Bucket": self._bucket,
                "Prefix": self._index_key,
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            try:
                page = self._s3.list_objects_v2(**kwargs)
            except Exception:
                return []

            contents = page.get("Contents")
            if isinstance(contents, list):
                for item in contents:
                    if not isinstance(item, dict):
                        continue
                    key = item.get("Key")
                    if isinstance(key, str) and key.endswith(".jsonl"):
                        keys.append(key)

            if not bool(page.get("IsTruncated")):
                break
            token = page.get("NextContinuationToken")
            if not isinstance(token, str) or token == "":
                break
            continuation_token = token

        return sorted(keys)

    def _read_object_text(self, object_key: str) -> str:
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=object_key)
        except Exception:
            return ""

        body = response.get("Body")
        if body is None:
            return ""

        payload = body.read()
        if isinstance(payload, (bytes, bytearray)):
            return payload.decode("utf-8", errors="ignore")
        return str(payload)

    @staticmethod
    def _parse_jsonl_records(text: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                records.append(parsed)
        return records

    @staticmethod
    def _parse_metadata(raw: Any) -> dict[str, str]:
        if not isinstance(raw, dict):
            return {}
        return {str(key): str(value) for key, value in raw.items()}

    @staticmethod
    def _matches_filters(metadata: dict[str, str], filters: dict[str, str]) -> bool:
        for key, expected in filters.items():
            if metadata.get(key) != expected:
                return False
        return True

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in TOKEN_SPLIT_RE.split(text.lower()) if token}
