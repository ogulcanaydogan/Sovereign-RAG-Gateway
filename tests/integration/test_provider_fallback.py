"""Integration tests for multi-provider fallback routing."""


def test_chat_with_provider_registry_success(client, auth_headers) -> None:
    """Provider registry is wired in but primary succeeds on first try."""
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"


def test_embeddings_with_provider_registry_success(client, auth_headers) -> None:
    """Embeddings endpoint works through provider registry."""
    response = client.post(
        "/v1/embeddings",
        headers=auth_headers,
        json={"model": "text-embedding-3-small", "input": "hello"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"


def test_readiness_includes_provider_status(client, auth_headers) -> None:
    """Readiness endpoint reports provider registry status."""
    response = client.get("/readyz", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["dependencies"]["provider"] == "ok"
