import base64

from app.rag.connectors.jira import JiraConnector


def _issue(issue_id: str, issue_key: str, summary: str, project: str = "OPS") -> dict[str, object]:
    return {
        "id": issue_id,
        "key": issue_key,
        "fields": {
            "summary": summary,
            "description": {
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "incident response runbook"}],
                    }
                ],
            },
            "project": {"key": project},
            "issuetype": {"name": "Task"},
            "updated": "2026-02-18T00:00:00.000+0000",
        },
    }


def test_jira_auth_header() -> None:
    headers = JiraConnector._build_headers("user@example.com", "token-123")
    expected = base64.b64encode(b"user@example.com:token-123").decode("ascii")
    assert headers["Authorization"] == f"Basic {expected}"


def test_jira_search_pagination_merges(monkeypatch) -> None:
    connector = JiraConnector(
        base_url="https://example.atlassian.net",
        email="user@example.com",
        api_token="token",
    )

    first = [_issue(str(index), f"OPS-{index}", "alpha") for index in range(50)]
    second = [_issue("51", "OPS-51", "alpha beta")]
    calls: list[int] = []

    def fake_get_json(path: str, params: dict[str, object]) -> dict[str, object]:
        assert path == "/rest/api/3/search"
        start_at = int(params["startAt"])
        calls.append(start_at)
        if start_at == 0:
            return {"issues": first}
        if start_at == 50:
            return {"issues": second}
        return {"issues": []}

    monkeypatch.setattr(connector, "_get_json", fake_get_json)

    results = connector.search(query="alpha", filters={}, k=100)
    assert len(results) == 51
    assert calls == [0, 50]


def test_jira_search_filter_and_scoring(monkeypatch) -> None:
    connector = JiraConnector(
        base_url="https://example.atlassian.net",
        email="user@example.com",
        api_token="token",
    )

    records = [
        {
            "source_id": "1",
            "uri": "https://example/browse/OPS-1",
            "text": "incident alpha beta",
            "metadata": {"project": "OPS", "key": "OPS-1", "type": "Task"},
        },
        {
            "source_id": "2",
            "uri": "https://example/browse/ENG-2",
            "text": "beta only",
            "metadata": {"project": "ENG", "key": "ENG-2", "type": "Task"},
        },
    ]
    monkeypatch.setattr(connector, "_search_records", lambda query: records)

    results = connector.search(query="alpha beta", filters={"project": "OPS"}, k=5)
    assert len(results) == 1
    assert results[0].source_id == "1"
    assert results[0].score > 0


def test_jira_fetch_issue(monkeypatch) -> None:
    connector = JiraConnector(
        base_url="https://example.atlassian.net",
        email="user@example.com",
        api_token="token",
        project_keys={"OPS"},
    )

    def fake_get_json(path: str, params: dict[str, object]) -> dict[str, object]:
        assert path == "/rest/api/3/issue/42"
        _ = params
        return _issue("42", "OPS-42", "Restart runbook", project="OPS")

    monkeypatch.setattr(connector, "_get_json", fake_get_json)

    doc = connector.fetch("42")
    assert doc is not None
    assert doc.source_id == "42"
    assert "incident response runbook" in doc.text
    assert doc.metadata["project"] == "OPS"
