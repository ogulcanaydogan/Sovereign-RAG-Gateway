import json
from pathlib import Path

import pytest

from scripts.audit_replay_bundle import (
    _hash_payload,
    generate_bundle,
    main,
)


def _write_event(log_path: Path, event: dict[str, object]) -> dict[str, object]:
    payload = dict(event)
    payload_hash = _hash_payload(payload)
    payload["payload_hash"] = payload_hash
    with log_path.open("a", encoding="utf-8") as file_handle:
        file_handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    return payload


def _base_event(request_id: str, prev_hash: str = "") -> dict[str, object]:
    return {
        "event_id": f"evt-{request_id}",
        "request_id": request_id,
        "tenant_id": "tenant-a",
        "user_id": "user-1",
        "endpoint": "/v1/chat/completions",
        "requested_model": "gpt-4o-mini",
        "selected_model": "gpt-4o-mini",
        "provider": "stub",
        "policy_decision": "allow",
        "policy_decision_id": "decision-1",
        "policy_evaluated_at": "2026-02-17T00:00:00Z",
        "policy_allow": True,
        "policy_mode": "enforce",
        "transforms_applied": [],
        "redaction_count": 0,
        "request_payload_hash": "req-hash",
        "redacted_payload_hash": "redacted-hash",
        "provider_request_hash": "provider-req-hash",
        "provider_response_hash": "provider-resp-hash",
        "retrieval_citations": [],
        "streaming": False,
        "tokens_in": 10,
        "tokens_out": 12,
        "cost_usd": 0.000022,
        "policy_hash": "hash",
        "provider_attempts": 1,
        "fallback_chain": ["stub"],
        "prev_hash": prev_hash,
        "created_at": "2026-02-17T00:00:01Z",
    }


def test_generate_bundle_success(tmp_path: Path) -> None:
    log_path = tmp_path / "events.jsonl"
    first = _write_event(log_path, _base_event("req-1", prev_hash=""))
    _write_event(log_path, _base_event("req-2", prev_hash=str(first["payload_hash"])))

    result = generate_bundle(
        request_id="req-2",
        audit_log_path=log_path,
        out_dir=tmp_path / "evidence",
        include_chain_verify=True,
    )

    assert result.bundle_path.exists()
    bundle = json.loads(result.bundle_path.read_text(encoding="utf-8"))
    assert bundle["request_id"] == "req-2"
    assert bundle["integrity"]["chain_verified"] is True


def test_generate_bundle_chain_tamper_detected(tmp_path: Path) -> None:
    log_path = tmp_path / "events.jsonl"
    first = _write_event(log_path, _base_event("req-1", prev_hash=""))
    second = _write_event(log_path, _base_event("req-2", prev_hash=str(first["payload_hash"])))

    tampered = dict(second)
    tampered["tokens_in"] = 999
    with log_path.open("w", encoding="utf-8") as file_handle:
        file_handle.write(json.dumps(first, ensure_ascii=True) + "\n")
        file_handle.write(json.dumps(tampered, ensure_ascii=True) + "\n")

    result = generate_bundle(
        request_id="req-2",
        audit_log_path=log_path,
        out_dir=tmp_path / "evidence",
        include_chain_verify=True,
    )

    bundle = json.loads(result.bundle_path.read_text(encoding="utf-8"))
    assert bundle["integrity"]["chain_verified"] is False


def test_request_not_found_exits_with_code_2(tmp_path: Path) -> None:
    log_path = tmp_path / "events.jsonl"
    _write_event(log_path, _base_event("req-1", prev_hash=""))

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--request-id",
                "missing-request",
                "--audit-log",
                str(log_path),
                "--out-dir",
                str(tmp_path / "evidence"),
            ]
        )

    assert exc.value.code == 2
