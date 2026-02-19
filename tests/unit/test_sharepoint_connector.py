from app.rag.connectors.sharepoint import SharePointConnector


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
