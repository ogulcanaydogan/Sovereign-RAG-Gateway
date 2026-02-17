def test_embeddings_endpoint_success(client, auth_headers) -> None:
    response = client.post(
        "/v1/embeddings",
        headers=auth_headers,
        json={
            "model": "text-embedding-3-small",
            "input": ["hello", "world"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert body["model"] == "text-embedding-3-small"
    assert len(body["data"]) == 2
    assert len(body["data"][0]["embedding"]) == 16
    assert body["usage"]["prompt_tokens"] >= 2


def test_embeddings_endpoint_empty_input_returns_422(client, auth_headers) -> None:
    response = client.post(
        "/v1/embeddings",
        headers=auth_headers,
        json={
            "model": "text-embedding-3-small",
            "input": [],
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "request_validation_failed"
