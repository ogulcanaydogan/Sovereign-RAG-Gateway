def test_models_endpoint_success(client, auth_headers) -> None:
    response = client.get("/v1/models", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert isinstance(body["data"], list)
    assert any(item["id"] == "gpt-4o-mini" for item in body["data"])
