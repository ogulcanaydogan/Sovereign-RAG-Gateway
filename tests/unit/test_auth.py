def test_missing_bearer_token_returns_401(client) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "auth_missing"


def test_invalid_bearer_token_returns_401(client, auth_headers) -> None:
    headers = dict(auth_headers)
    headers["Authorization"] = "Bearer wrong"
    response = client.post(
        "/v1/chat/completions",
        headers=headers,
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_invalid"


def test_missing_required_headers_returns_422(client) -> None:
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-key"},
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "missing_required_headers"
