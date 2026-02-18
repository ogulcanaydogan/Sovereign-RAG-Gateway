from __future__ import annotations

import base64
import html
import re
from time import monotonic
from typing import Any

import httpx

from app.rag.types import Document, DocumentChunk

TAG_RE = re.compile(r"<[^>]+>")
TOKEN_SPLIT_RE = re.compile(r"\W+")


class ConfluenceConnector:
    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        spaces: set[str] | None = None,
        connector_name: str = "confluence",
        cache_ttl_seconds: float = 60.0,
        timeout_s: float = 10.0,
        http_client: Any | None = None,
    ):
        root = base_url.rstrip("/")
        self._base_url = root if root.endswith("/wiki") else f"{root}/wiki"
        self._connector_name = connector_name
        self._spaces = {space.strip().lower() for space in (spaces or set()) if space.strip()}
        self._cache_ttl_seconds = max(cache_ttl_seconds, 0.0)

        self._headers = self._build_headers(email=email, api_token=api_token)
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
            if not self._space_allowed(metadata):
                continue
            if not self._matches_filters(metadata, filters):
                continue

            text = str(record.get("text", "")).strip()
            if not text:
                continue

            overlap = len(query_tokens.intersection(self._tokens(text)))
            score = overlap / len(query_tokens) if query_tokens else 0.0

            source_id = str(record.get("source_id", "")).strip()
            uri = str(record.get("uri", "")).strip()
            if source_id == "" or uri == "":
                continue

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

        page = self._fetch_page(doc_id)
        if page is None:
            return None

        metadata = self._parse_metadata(page.get("metadata"))
        if not self._space_allowed(metadata):
            return None

        uri = str(page.get("uri", "")).strip()
        text = str(page.get("text", "")).strip()
        if uri == "" or text == "":
            return None

        document = Document(source_id=doc_id, uri=uri, text=text, metadata=metadata)
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
        start = 0
        limit = 25
        escaped_query = query.replace('"', '\\"')

        while True:
            payload = self._get_json(
                "/rest/api/search",
                {
                    "cql": f'type=page AND text~"{escaped_query}"',
                    "start": start,
                    "limit": limit,
                    "expand": "content.space,content.body.storage",
                },
            )
            results = payload.get("results")
            if not isinstance(results, list) or len(results) == 0:
                break

            for item in results:
                if not isinstance(item, dict):
                    continue
                parsed = self._parse_search_result(item)
                if parsed is not None:
                    records.append(parsed)

            if len(results) < limit:
                break
            start += limit

        return records

    def _parse_search_result(self, item: dict[str, Any]) -> dict[str, Any] | None:
        content = item.get("content")
        if not isinstance(content, dict):
            return None

        source_id = str(content.get("id", "")).strip()
        if source_id == "":
            return None

        title = str(content.get("title", "")).strip()
        content_type = str(content.get("type", "page")).strip()

        space_key = ""
        space = content.get("space")
        if isinstance(space, dict):
            space_key = str(space.get("key", "")).strip()

        body_text = ""
        body = content.get("body")
        if isinstance(body, dict):
            storage = body.get("storage")
            if isinstance(storage, dict):
                body_text = str(storage.get("value", "")).strip()

        excerpt = str(item.get("excerpt", "")).strip()
        text = self._html_to_text(body_text if body_text else excerpt)
        if text == "":
            text = title

        links = item.get("_links")
        if not isinstance(links, dict):
            links = {}
        webui = str(links.get("webui", "")).strip()
        uri = self._resolve_uri(webui=webui)

        return {
            "source_id": source_id,
            "uri": uri,
            "text": text,
            "metadata": {
                "space": space_key,
                "type": content_type,
                "title": title,
            },
        }

    def _fetch_page(self, doc_id: str) -> dict[str, Any] | None:
        payload = self._get_json(
            f"/rest/api/content/{doc_id}",
            {
                "expand": "body.storage,space,version,title",
            },
        )

        source_id = str(payload.get("id", "")).strip()
        if source_id == "":
            return None

        title = str(payload.get("title", "")).strip()
        content_type = str(payload.get("type", "page")).strip()

        space_key = ""
        space = payload.get("space")
        if isinstance(space, dict):
            space_key = str(space.get("key", "")).strip()

        version_number = ""
        version = payload.get("version")
        if isinstance(version, dict):
            number = version.get("number")
            if isinstance(number, int):
                version_number = str(number)

        body_text = ""
        body = payload.get("body")
        if isinstance(body, dict):
            storage = body.get("storage")
            if isinstance(storage, dict):
                body_text = str(storage.get("value", "")).strip()

        links = payload.get("_links")
        if not isinstance(links, dict):
            links = {}
        webui = str(links.get("webui", "")).strip()

        text = self._html_to_text(body_text)
        if text == "":
            return None

        return {
            "source_id": source_id,
            "uri": self._resolve_uri(webui=webui),
            "text": text,
            "metadata": {
                "space": space_key,
                "type": content_type,
                "title": title,
                "version": version_number,
            },
        }

    def _get_json(self, path: str, params: dict[str, object]) -> dict[str, Any]:
        query_params: dict[str, str | int | float | bool | None] = {}
        for key, value in params.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                query_params[key] = value
        url = f"{self._base_url}{path}"
        response = self._http.get(url, params=query_params, headers=self._headers)
        if int(response.status_code) >= 400:
            raise RuntimeError(
                f"Confluence API returned {response.status_code}: {response.text[:200]}"
            )
        parsed = response.json()
        if not isinstance(parsed, dict):
            raise RuntimeError("Confluence API response must be an object")
        return parsed

    def _space_allowed(self, metadata: dict[str, str]) -> bool:
        if not self._spaces:
            return True
        space = metadata.get("space", "").lower()
        return space in self._spaces

    def _resolve_uri(self, webui: str) -> str:
        if webui.startswith("http"):
            return webui
        return f"{self._base_url}{webui}"

    @staticmethod
    def _build_headers(email: str, api_token: str) -> dict[str, str]:
        token = base64.b64encode(f"{email}:{api_token}".encode()).decode("ascii")
        return {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
        }

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

    @staticmethod
    def _html_to_text(value: str) -> str:
        without_tags = TAG_RE.sub(" ", value)
        plain = html.unescape(without_tags)
        normalized = " ".join(plain.split())
        return normalized.strip()
