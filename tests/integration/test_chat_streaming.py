import json


def test_chat_endpoint_stream_success(client, auth_headers) -> None:
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gpt-4o-mini",
            "stream": True,
            "messages": [{"role": "user", "content": "stream this response"}],
            "max_tokens": 64,
        },
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = [line for line in response.iter_lines() if line]

    assert lines[-1] == "data: [DONE]"
    first_payload = json.loads(lines[0].removeprefix("data: "))
    assert first_payload["object"] == "chat.completion.chunk"
    assert first_payload["choices"][0]["delta"]["role"] == "assistant"

    finish_payload = json.loads(lines[-2].removeprefix("data: "))
    assert finish_payload["choices"][0]["finish_reason"] == "stop"


def test_chat_endpoint_stream_provider_error_mapping(client, auth_headers) -> None:
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "error-429-stream",
            "stream": True,
            "messages": [{"role": "user", "content": "trigger upstream limit"}],
            "max_tokens": 64,
        },
    )

    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "provider_rate_limited"
