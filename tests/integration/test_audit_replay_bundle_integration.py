import json
from pathlib import Path

from scripts.audit_replay_bundle import generate_bundle


def test_audit_replay_bundle_success(client, auth_headers, tmp_path: Path) -> None:
    response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "patient DOB 01/01/1990"}],
        },
    )

    assert response.status_code == 200
    request_id = response.headers["x-request-id"]

    audit_log = client.app.state.chat_service._settings.audit_log_path
    result = generate_bundle(
        request_id=request_id,
        audit_log_path=audit_log,
        out_dir=tmp_path / "evidence",
        include_chain_verify=True,
    )

    bundle = json.loads(result.bundle_path.read_text(encoding="utf-8"))
    assert bundle["request_id"] == request_id
    assert bundle["policy"]["policy_hash"]
    assert bundle["provider"]["provider"]
    assert bundle["provider"]["provider_request_hash"] is not None
    assert bundle["provider"]["provider_response_hash"] is not None


def test_audit_replay_bundle_policy_deny_has_null_provider_hashes(
    client, auth_headers, tmp_path: Path
) -> None:
    deny_response = client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "forbidden-model",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert deny_response.status_code == 403
    request_id = deny_response.headers["x-request-id"]

    audit_log = client.app.state.chat_service._settings.audit_log_path
    result = generate_bundle(
        request_id=request_id,
        audit_log_path=audit_log,
        out_dir=tmp_path / "evidence",
        include_chain_verify=True,
    )

    bundle = json.loads(result.bundle_path.read_text(encoding="utf-8"))
    assert bundle["policy"]["allow"] is False
    assert bundle["provider"]["provider"] == "policy-gate"
    assert bundle["provider"]["provider_request_hash"] is None
    assert bundle["provider"]["provider_response_hash"] is None
