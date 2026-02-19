from __future__ import annotations

import base64
import html
import re
from time import monotonic
from typing import Any

import httpx

from app.rag.types import Document, DocumentChunk

TOKEN_SPLIT_RE = re.compile(r"\W+")
TAG_RE = re.compile(r"<[^>]+>")


class JiraConnector:
    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        project_keys: set[str] | None = None,
        connector_name: str = "jira",
        cache_ttl_seconds: float = 60.0,
        timeout_s: float = 10.0,
        http_client: Any | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._connector_name = connector_name
        self._project_keys = {
            key.strip().upper() for key in (project_keys or set()) if key.strip()
        }
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
            if not self._project_allowed(metadata):
                continue
            if not self._matches_filters(metadata, filters):
                continue

            text = str(record.get("text", "")).strip()
            if text == "":
                continue

            source_id = str(record.get("source_id", "")).strip()
            uri = str(record.get("uri", "")).strip()
            if source_id == "" or uri == "":
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

        issue = self._fetch_issue(doc_id)
        if issue is None:
            return None

        metadata = self._parse_metadata(issue.get("metadata"))
        if not self._project_allowed(metadata):
            return None

        uri = str(issue.get("uri", "")).strip()
        text = str(issue.get("text", "")).strip()
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
        issues: list[dict[str, Any]] = []
        start_at = 0
        max_results = 50
        escaped = query.replace('"', "\\\"")

        while True:
            payload = self._get_json(
                "/rest/api/3/search",
                {
                    "jql": f'text ~ "\\"{escaped}\\""',
                    "startAt": start_at,
                    "maxResults": max_results,
                    "fields": "summary,description,project,issuetype,updated",
                },
            )
            rows = payload.get("issues")
            if not isinstance(rows, list) or len(rows) == 0:
                break

            for row in rows:
                if isinstance(row, dict):
                    parsed = self._parse_issue_record(row)
                    if parsed is not None:
                        issues.append(parsed)

            if len(rows) < max_results:
                break
            start_at += max_results

        return issues

    def _parse_issue_record(self, row: dict[str, Any]) -> dict[str, Any] | None:
        issue_id = str(row.get("id", "")).strip()
        issue_key = str(row.get("key", "")).strip()
        if issue_id == "":
            return None

        fields = row.get("fields")
        if not isinstance(fields, dict):
            fields = {}

        summary = str(fields.get("summary", "")).strip()
        description = self._extract_description(fields.get("description"))
        text = " ".join(part for part in [summary, description] if part).strip()

        project_key = ""
        project = fields.get("project")
        if isinstance(project, dict):
            project_key = str(project.get("key", "")).strip().upper()

        issue_type = ""
        issue_type_payload = fields.get("issuetype")
        if isinstance(issue_type_payload, dict):
            issue_type = str(issue_type_payload.get("name", "")).strip()

        updated = str(fields.get("updated", "")).strip()

        return {
            "source_id": issue_id,
            "uri": self._issue_uri(issue_key),
            "text": text,
            "metadata": {
                "key": issue_key,
                "project": project_key,
                "type": issue_type,
                "summary": summary,
                "updated": updated,
            },
        }

    def _fetch_issue(self, doc_id: str) -> dict[str, Any] | None:
        payload = self._get_json(
            f"/rest/api/3/issue/{doc_id}",
            {
                "fields": "summary,description,project,issuetype,updated,key",
            },
        )

        issue_id = str(payload.get("id", "")).strip()
        issue_key = str(payload.get("key", "")).strip()
        if issue_id == "":
            return None

        fields = payload.get("fields")
        if not isinstance(fields, dict):
            fields = {}

        summary = str(fields.get("summary", "")).strip()
        description = self._extract_description(fields.get("description"))
        text = "\n".join(part for part in [summary, description] if part).strip()
        if text == "":
            return None

        project_key = ""
        project = fields.get("project")
        if isinstance(project, dict):
            project_key = str(project.get("key", "")).strip().upper()

        issue_type = ""
        issue_type_payload = fields.get("issuetype")
        if isinstance(issue_type_payload, dict):
            issue_type = str(issue_type_payload.get("name", "")).strip()

        updated = str(fields.get("updated", "")).strip()

        return {
            "source_id": issue_id,
            "uri": self._issue_uri(issue_key),
            "text": text,
            "metadata": {
                "key": issue_key,
                "project": project_key,
                "type": issue_type,
                "summary": summary,
                "updated": updated,
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
            raise RuntimeError(f"Jira API returned {response.status_code}: {response.text[:200]}")

        parsed = response.json()
        if not isinstance(parsed, dict):
            raise RuntimeError("Jira API response must be an object")
        return parsed

    def _project_allowed(self, metadata: dict[str, str]) -> bool:
        if not self._project_keys:
            return True
        project = metadata.get("project", "").upper()
        return project in self._project_keys

    def _issue_uri(self, issue_key: str) -> str:
        key = issue_key.strip()
        if key == "":
            return self._base_url
        return f"{self._base_url}/browse/{key}"

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
    def _extract_description(value: object) -> str:
        if isinstance(value, str):
            plain = html.unescape(TAG_RE.sub(" ", value))
            return " ".join(plain.split()).strip()

        texts: list[str] = []

        def walk(node: object) -> None:
            if isinstance(node, dict):
                maybe_text = node.get("text")
                if isinstance(maybe_text, str):
                    texts.append(maybe_text)
                for child in node.values():
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(value)
        return " ".join(part.strip() for part in texts if part.strip())
