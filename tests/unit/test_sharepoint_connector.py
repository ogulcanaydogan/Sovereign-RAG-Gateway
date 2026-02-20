import pytest

from app.rag.connectors.sharepoint import ManagedIdentityTokenProvider, SharePointConnector


class _FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeHTTPClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, params=None, headers=None):  # noqa: ANN001
        self.calls.append(
            {
                "url": url,
                "params": dict(params or {}),
                "headers": dict(headers or {}),
            }
        )
        return _FakeResponse(payload=self.payload)


def _search_item(item_id: str, name: str, path: str) -> dict[str, object]:
    return {
        "id": item_id,
        "name": name,
        "webUrl": f"https://contoso.sharepoint.com/:w:/r/sites/site/{item_id}",
        "lastModifiedDateTime": "2026-02-20T00:00:00Z",
        "parentReference": {"path": path},
    }


def test_sharepoint_search_pagination_merges_results(monkeypatch) -> None:
    connector = SharePointConnector(
        site_id="site-id",
        bearer_token="token",
    )
    first_page = [
        _search_item("1", "Runbook One", "/drives/drive-1/root:/Ops"),
        _search_item("2", "Runbook Two", "/drives/drive-1/root:/Ops"),
    ]
    second_page = [_search_item("3", "Runbook Three", "/drives/drive-1/root:/Ops")]
    calls: list[str] = []

    def fake_get_json(path: str, params: dict[str, object]) -> dict[str, object]:
        calls.append(path)
        assert params["$top"] == 50
        return {
            "value": first_page,
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next-page",
        }

    def fake_get_json_absolute(url: str) -> dict[str, object]:
        calls.append(url)
        assert url == "https://graph.microsoft.com/v1.0/next-page"
        return {"value": second_page}

    monkeypatch.setattr(connector, "_get_json", fake_get_json)
    monkeypatch.setattr(connector, "_get_json_absolute", fake_get_json_absolute)

    results = connector.search(query="runbook", filters={}, k=10)
    assert len(results) == 3
    assert calls == [
        "/sites/site-id/drive/root/search(q='runbook')",
        "https://graph.microsoft.com/v1.0/next-page",
    ]


def test_sharepoint_search_applies_filters_and_path_prefix(monkeypatch) -> None:
    connector = SharePointConnector(
        site_id="site-id",
        bearer_token="token",
        allowed_path_prefixes={"/drives/drive-1/root:/Ops"},
    )
    records = [
        {
            "source_id": "1",
            "uri": "https://contoso/doc/1",
            "text": "incident alpha beta",
            "metadata": {
                "name": "Ops Runbook.md",
                "path": "/drives/drive-1/root:/Ops/Runbooks",
            },
        },
        {
            "source_id": "2",
            "uri": "https://contoso/doc/2",
            "text": "beta only",
            "metadata": {
                "name": "Engineering Notes.md",
                "path": "/drives/drive-1/root:/Engineering",
            },
        },
    ]
    monkeypatch.setattr(connector, "_search_records", lambda query: records)

    results = connector.search(
        query="alpha beta",
        filters={"name": "Ops Runbook.md"},
        k=5,
    )
    assert len(results) == 1
    assert results[0].source_id == "1"
    assert results[0].score > 0


def test_sharepoint_fetch_document(monkeypatch) -> None:
    connector = SharePointConnector(
        site_id="site-id",
        bearer_token="token",
        allowed_path_prefixes={"/drives/drive-1/root:/Ops"},
    )

    def fake_get_json(path: str, params: dict[str, object]) -> dict[str, object]:
        assert path == "/sites/site-id/drive/items/doc-42"
        _ = params
        return {
            "id": "doc-42",
            "name": "Ops Playbook.md",
            "webUrl": "https://contoso.sharepoint.com/doc-42",
            "lastModifiedDateTime": "2026-02-20T00:00:00Z",
            "parentReference": {"path": "/drives/drive-1/root:/Ops/Playbooks"},
            "@microsoft.graph.downloadUrl": "https://download/doc-42",
        }

    monkeypatch.setattr(connector, "_get_json", fake_get_json)
    monkeypatch.setattr(
        connector,
        "_get_text",
        lambda url: "Escalation runbook for provider throttling" if "download" in url else "",
    )

    document = connector.fetch("doc-42")
    assert document is not None
    assert document.source_id == "doc-42"
    assert "provider throttling" in document.text
    assert document.metadata["path"] == "/drives/drive-1/root:/Ops/Playbooks"


def test_sharepoint_search_uses_token_provider_header(monkeypatch) -> None:
    client = _FakeHTTPClient(payload={"value": []})
    connector = SharePointConnector(
        site_id="site-id",
        token_provider=lambda: "token-from-provider",
        http_client=client,
    )
    monkeypatch.setattr(connector, "_search_records", lambda query: [])
    _ = connector.search(query="runbook", filters={}, k=3)

    _ = connector._get_json("/sites/site-id/drive/root/search(q='runbook')", {"$top": 50})
    assert client.calls[-1]["headers"]["Authorization"] == "Bearer token-from-provider"


def test_managed_identity_token_provider_caches_until_expiry() -> None:
    client = _FakeHTTPClient(payload={"access_token": "mi-token", "expires_in": 3600})
    provider = ManagedIdentityTokenProvider(
        endpoint="http://localhost/token",
        resource="https://graph.microsoft.com/",
        client_id="user-assigned-id",
        http_client=client,
    )

    first = provider.get_token()
    second = provider.get_token()

    assert first == "mi-token"
    assert second == "mi-token"
    assert len(client.calls) == 1
    params = client.calls[0]["params"]
    assert params["client_id"] == "user-assigned-id"
    assert params["resource"] == "https://graph.microsoft.com/"


def test_managed_identity_token_provider_raises_on_missing_token() -> None:
    client = _FakeHTTPClient(payload={"expires_in": 30})
    provider = ManagedIdentityTokenProvider(
        endpoint="http://localhost/token",
        resource="https://graph.microsoft.com/",
        http_client=client,
    )

    with pytest.raises(RuntimeError, match="access_token"):
        provider.get_token()
