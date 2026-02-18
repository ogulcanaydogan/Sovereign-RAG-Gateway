import json


def test_chat_endpoint_success(client, auth_headers) -> None:
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello patient DOB 01/01/1990"}],
            "temperature": 0.2,
            "max_tokens": 100,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["usage"]["total_tokens"] >= 1


def test_chat_endpoint_validation_error_shape(client, auth_headers) -> None:
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={"model": "gpt-4o-mini", "messages": []},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["type"] == "validation"


def test_chat_endpoint_audit_contains_policy_explainability(client, auth_headers) -> None:
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 200

    log_path = client.app.state.chat_service._settings.audit_log_path
    rows = log_path.read_text(encoding="utf-8").splitlines()
    assert rows
    payload = json.loads(rows[-1])
    assert payload["policy_decision_id"]
    assert payload["policy_evaluated_at"]
    assert payload["policy_mode"] in {"enforce", "observe"}
