def test_request_id_is_added(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.headers.get("x-request-id")
