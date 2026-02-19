import base64

from app.rag.connectors.confluence import ConfluenceConnector


def _search_result(doc_id: str, title: str, excerpt: str, space: str = "OPS") -> dict[str, object]:
    return {
        "content": {
            "id": doc_id,
            "title": title,
            "type": "page",
            "space": {"key": space},
        },
        "excerpt": excerpt,
        "_links": {"webui": f"/spaces/{space}/pages/{doc_id}"},
    }


def test_confluence_auth_header() -> None:
    headers = ConfluenceConnector._build_headers("user@example.com", "token-123")
    expected = base64.b64encode(b"user@example.com:token-123").decode("ascii")
    assert headers["Authorization"] == f"Basic {expected}"


def test_confluence_search_pagination_merges_results(monkeypatch) -> None:
    connector = ConfluenceConnector(
        base_url="https://example.atlassian.net",
        email="user@example.com",
        api_token="token",
    )

    first_page = [_search_result(str(index), f"Doc {index}", "alpha") for index in range(25)]
    second_page = [_search_result("26", "Doc 26", "alpha beta")]
    calls: list[int] = []

    def fake_get_json(path: str, params: dict[str, object]) -> dict[str, object]:
        assert path == "/rest/api/search"
        start = int(params["start"])
        calls.append(start)
        if start == 0:
            return {"results": first_page}
        if start == 25:
            return {"results": second_page}
        return {"results": []}

    monkeypatch.setattr(connector, "_get_json", fake_get_json)

    results = connector.search(query="alpha", filters={}, k=30)
    assert len(results) == 26
    assert calls == [0, 25]


def test_confluence_search_filter_and_scoring(monkeypatch) -> None:
    connector = ConfluenceConnector(
        base_url="https://example.atlassian.net",
        email="user@example.com",
        api_token="token",
    )

    records = [
        {
            "source_id": "a",
            "uri": "https://example/wiki/a",
            "text": "incident alpha beta",
            "metadata": {"space": "OPS", "type": "page", "title": "A"},
        },
        {
            "source_id": "b",
            "uri": "https://example/wiki/b",
            "text": "beta",
            "metadata": {"space": "ENG", "type": "page", "title": "B"},
        },
    ]

    monkeypatch.setattr(connector, "_search_records", lambda query: records)

    results = connector.search(query="alpha beta", filters={"space": "OPS"}, k=5)
    assert len(results) == 1
    assert results[0].source_id == "a"
    assert results[0].score > 0


def test_confluence_fetch_page(monkeypatch) -> None:
    connector = ConfluenceConnector(
        base_url="https://example.atlassian.net",
        email="user@example.com",
        api_token="token",
        spaces={"OPS"},
    )

    def fake_get_json(path: str, params: dict[str, object]) -> dict[str, object]:
        assert path == "/rest/api/content/42"
        _ = params
        return {
            "id": "42",
            "title": "Runbook",
            "type": "page",
            "space": {"key": "OPS"},
            "version": {"number": 7},
            "body": {"storage": {"value": "<p>Restart service</p>"}},
            "_links": {"webui": "/spaces/OPS/pages/42"},
        }

    monkeypatch.setattr(connector, "_get_json", fake_get_json)

    document = connector.fetch("42")
    assert document is not None
    assert document.source_id == "42"
    assert "Restart service" in document.text
    assert document.metadata["space"] == "OPS"
