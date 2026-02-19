from __future__ import annotations

import re
from time import monotonic
from typing import Any

import httpx

from app.rag.types import Document, DocumentChunk

TOKEN_SPLIT_RE = re.compile(r"\W+")


class SharePointConnector:
    """Read-only SharePoint retrieval connector via Microsoft Graph."""

    def __init__(
        self,
        site_id: str,
        bearer_token: str,
        base_url: str = "https://graph.microsoft.com/v1.0",
        drive_id: str | None = None,
        allowed_path_prefixes: set[str] | None = None,
        connector_name: str = "sharepoint",
        cache_ttl_seconds: float = 60.0,
        timeout_s: float = 10.0,
        http_client: Any | None = None,
    ) -> None:
        normalized_site_id = site_id.strip()
        if normalized_site_id == "":
            raise ValueError("site_id must be non-empty")
        normalized_token = bearer_token.strip()
        if normalized_token == "":
            raise ValueError("bearer_token must be non-empty")

        self._site_id = normalized_site_id
        self._base_url = base_url.rstrip("/")
        self._drive_id = (
            drive_id.strip()
            if isinstance(drive_id, str) and drive_id.strip()
            else None
        )
        self._connector_name = connector_name
        self._cache_ttl_seconds = max(cache_ttl_seconds, 0.0)
        self._allowed_path_prefixes = {
            self._normalize_path_prefix(prefix)
            for prefix in (allowed_path_prefixes or set())
            if prefix.strip()
        }
        self._headers = {
            "Authorization": f"Bearer {normalized_token}",
            "Accept": "application/json",
        }
        self._http = http_client or httpx.Client(timeout=timeout_s)

        self._search_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._document_cache: dict[str, tuple[float, Document]] = {}

    def search(self, query: str, filters: dict[str, str], k: int) -> list[DocumentChunk]:
        if k < 1:
            return []

        records = self._search_records(query)
        query_tokens = self._tokens(query)
        ranked: list[DocumentChunk] = []

        for record in records:
            metadata = self._parse_metadata(record.get("metadata"))
            if not self._path_allowed(metadata):
                continue
            if not self._matches_filters(metadata, filters):
                continue

            source_id = str(record.get("source_id", "")).strip()
            uri = str(record.get("uri", "")).strip()
            text = str(record.get("text", "")).strip()
            if source_id == "" or uri == "" or text == "":
                continue

            overlap = len(query_tokens.intersection(self._tokens(text)))
            score = overlap / len(query_tokens) if query_tokens else 0.0

            ranked.append(
                DocumentChunk(
                    source_id=source_id,
                    connector=self._connector_name,
                    uri=uri,
                    chunk_id=f"{source_id}#0",
                    text=text,
                    score=round(score, 6),
                    metadata=metadata,
                )
            )

        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:k]

    def fetch(self, doc_id: str) -> Document | None:
        cached = self._document_cache.get(doc_id)
        now = monotonic()
        if cached is not None and (now - cached[0]) < self._cache_ttl_seconds:
            return cached[1]

        metadata_payload = self._get_json(
            f"{self._drive_prefix()}/items/{doc_id}",
            {
                "$select": (
                    "id,name,webUrl,lastModifiedDateTime,parentReference,"
                    "@microsoft.graph.downloadUrl"
                )
            },
        )
        source_id = str(metadata_payload.get("id", "")).strip()
        uri = str(metadata_payload.get("webUrl", "")).strip()
        name = str(metadata_payload.get("name", "")).strip()
        if source_id == "" or uri == "":
            return None

        parent_reference = metadata_payload.get("parentReference")
        parent_path = ""
        if isinstance(parent_reference, dict):
            parent_path = str(parent_reference.get("path", "")).strip()

        metadata = {
            "name": name,
            "path": parent_path,
            "last_modified": str(metadata_payload.get("lastModifiedDateTime", "")).strip(),
        }
        if not self._path_allowed(metadata):
            return None

        download_url = str(metadata_payload.get("@microsoft.graph.downloadUrl", "")).strip()
        if download_url == "":
            return None

        text = self._get_text(download_url)
        if text == "":
            text = name
        if text == "":
            return None

        document = Document(source_id=source_id, uri=uri, text=text, metadata=metadata)
        self._document_cache[doc_id] = (now, document)
        return document

    def _search_records(self, query: str) -> list[dict[str, Any]]:
        cache_key = query.strip().lower()
        cached = self._search_cache.get(cache_key)
        now = monotonic()
        if cached is not None and (now - cached[0]) < self._cache_ttl_seconds:
            return cached[1]

        records = self._fetch_search_records(query)
        self._search_cache[cache_key] = (now, records)
        return records

    def _fetch_search_records(self, query: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        escaped_query = query.replace("'", "''")
        next_url: str | None = None
        path = f"{self._drive_prefix()}/root/search(q='{escaped_query}')"
        params: dict[str, object] = {"$top": 50}

        while True:
            payload = (
                self._get_json_absolute(next_url)
                if next_url
                else self._get_json(path=path, params=params)
            )
            values = payload.get("value")
            if not isinstance(values, list) or len(values) == 0:
                break

            for value in values:
                if not isinstance(value, dict):
                    continue
                parsed = self._parse_search_result(value)
                if parsed is not None:
                    records.append(parsed)

            raw_next = payload.get("@odata.nextLink")
            if not isinstance(raw_next, str) or raw_next.strip() == "":
                break
            next_url = raw_next.strip()

        return records

    def _parse_search_result(self, value: dict[str, Any]) -> dict[str, Any] | None:
        source_id = str(value.get("id", "")).strip()
        uri = str(value.get("webUrl", "")).strip()
        name = str(value.get("name", "")).strip()
        if source_id == "" or uri == "":
            return None

        parent_reference = value.get("parentReference")
        parent_path = ""
        if isinstance(parent_reference, dict):
            parent_path = str(parent_reference.get("path", "")).strip()

        text = " ".join(part for part in [name, parent_path] if part).strip()
        if text == "":
            return None

        return {
            "source_id": source_id,
            "uri": uri,
            "text": text,
            "metadata": {
                "name": name,
                "path": parent_path,
                "last_modified": str(value.get("lastModifiedDateTime", "")).strip(),
            },
        }

    def _get_json(self, path: str, params: dict[str, object]) -> dict[str, Any]:
        query_params: dict[str, str | int | float | bool | None] = {}
        for key, value in params.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                query_params[key] = value
        response = self._http.get(
            f"{self._base_url}{path}",
            params=query_params,
            headers=self._headers,
        )
        if int(response.status_code) >= 400:
            raise RuntimeError(
                f"SharePoint API returned {response.status_code}: {response.text[:200]}"
            )
        parsed = response.json()
        if not isinstance(parsed, dict):
            raise RuntimeError("SharePoint API response must be an object")
        return parsed

    def _get_json_absolute(self, url: str) -> dict[str, Any]:
        response = self._http.get(url, headers=self._headers)
        if int(response.status_code) >= 400:
            raise RuntimeError(
                f"SharePoint API returned {response.status_code}: {response.text[:200]}"
            )
        parsed = response.json()
        if not isinstance(parsed, dict):
            raise RuntimeError("SharePoint API response must be an object")
        return parsed

    def _get_text(self, url: str) -> str:
        response = self._http.get(url)
        if int(response.status_code) >= 400:
            raise RuntimeError(
                f"SharePoint file download returned {response.status_code}: {response.text[:200]}"
            )
        text = response.text
        if len(text) > 20_000:
            text = text[:20_000]
        return " ".join(text.split()).strip()

    def _drive_prefix(self) -> str:
        if self._drive_id:
            return f"/sites/{self._site_id}/drives/{self._drive_id}"
        return f"/sites/{self._site_id}/drive"

    def _path_allowed(self, metadata: dict[str, str]) -> bool:
        if not self._allowed_path_prefixes:
            return True
        normalized_path = self._normalize_path_prefix(metadata.get("path", ""))
        return any(
            normalized_path.startswith(prefix)
            for prefix in self._allowed_path_prefixes
        )

    @staticmethod
    def _normalize_path_prefix(value: str) -> str:
        normalized = value.strip().lower()
        if normalized == "":
            return ""
        if not normalized.startswith("/"):
            return f"/{normalized}"
        return normalized

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
        return {str(key): str(value) for key, value in raw.items()}

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in TOKEN_SPLIT_RE.split(text.lower()) if token}
