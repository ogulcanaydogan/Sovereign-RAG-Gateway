def test_provider_rate_limit_error_maps_to_429_for_chat(client, auth_headers) -> None:
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "error-429-model",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "provider_rate_limited"
    assert body["error"]["type"] == "rate_limit"


def test_provider_rate_limit_error_maps_to_429_for_embeddings(client, auth_headers) -> None:
    response = client.post(
        "/v1/embeddings",
        headers=auth_headers,
        json={
            "model": "error-429-model",
            "input": "hello",
        },
    )

    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "provider_rate_limited"
