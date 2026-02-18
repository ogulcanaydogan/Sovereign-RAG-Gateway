import json
from pathlib import Path

from jsonschema import validate


def test_policy_schema_fixture() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = json.loads(
        (root / "docs/contracts/v1/policy-decision.schema.json").read_text(encoding="utf-8")
    )
    fixture = {
        "decision_id": "d1",
        "allow": True,
        "policy_hash": "hash",
        "evaluated_at": "2026-02-17T00:00:00Z",
        "connector_constraints": {"allowed_connectors": ["filesystem", "postgres"]},
        "transforms": [],
    }
    validate(instance=fixture, schema=schema)


def test_citations_schema_fixture() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = json.loads(
        (root / "docs/contracts/v1/citations-extension.schema.json").read_text(encoding="utf-8")
    )
    fixture = {
        "choices": [
            {
                "message": {
                    "citations": [
                        {
                            "source_id": "src-1",
                            "connector": "filesystem",
                            "uri": "file:///tmp/doc.txt",
                            "chunk_id": "chunk-1",
                            "score": 0.9,
                        }
                    ]
                }
            }
        ]
    }
    validate(instance=fixture, schema=schema)


def test_audit_event_schema_fixture() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = json.loads(
        (root / "docs/contracts/v1/audit-event.schema.json").read_text(encoding="utf-8")
    )
    fixture = {
        "event_id": "evt-1",
        "request_id": "req-1",
        "tenant_id": "tenant-a",
        "user_id": "user-1",
        "endpoint": "/v1/chat/completions",
        "requested_model": "gpt-4o-mini",
        "selected_model": "gpt-4o-mini",
        "provider": "stub",
        "policy_decision": "transform",
        "policy_decision_id": "decision-1",
        "policy_evaluated_at": "2026-02-17T00:00:00Z",
        "policy_allow": True,
        "policy_mode": "enforce",
        "transforms_applied": ["set_max_tokens"],
        "redaction_count": 1,
        "request_payload_hash": "req-hash",
        "redacted_payload_hash": "redacted-hash",
        "provider_request_hash": "provider-req-hash",
        "provider_response_hash": "provider-resp-hash",
        "retrieval_citations": [
            {
                "source_id": "src-1",
                "connector": "filesystem",
                "uri": "file:///tmp/doc.txt",
                "chunk_id": "chunk-1",
                "score": 0.9,
            }
        ],
        "streaming": False,
        "tokens_in": 10,
        "tokens_out": 12,
        "cost_usd": 0.000022,
        "policy_hash": "hash",
        "provider_constraints": {
            "allowed_providers": ["stub"],
            "allowed_models": ["gpt-4o-mini"],
        },
        "connector_constraints": {"allowed_connectors": ["filesystem"]},
        "provider_attempts": 1,
        "fallback_chain": ["stub"],
        "payload_hash": "hash-a",
        "prev_hash": "",
        "created_at": "2026-02-17T00:00:01Z",
    }
    validate(instance=fixture, schema=schema)


def test_evidence_bundle_schema_fixture() -> None:
    root = Path(__file__).resolve().parents[2]
    schema = json.loads(
        (root / "docs/contracts/v1/evidence-bundle.schema.json").read_text(
            encoding="utf-8"
        )
    )
    fixture = {
        "bundle_version": "v1",
        "request_id": "req-1",
        "generated_at": "2026-02-17T00:00:05Z",
        "policy": {
            "decision_id": "decision-1",
            "policy_hash": "hash",
            "policy_mode": "enforce",
            "allow": True,
            "deny_reason": None,
        },
        "redaction": {
            "count": 1,
            "request_payload_hash": "req-hash",
            "redacted_payload_hash": "redacted-hash",
        },
        "retrieval": {
            "enabled": True,
            "connector": "filesystem",
            "citations": [
                {
                    "source_id": "src-1",
                    "connector": "filesystem",
                    "uri": "file:///tmp/doc.txt",
                    "chunk_id": "chunk-1",
                    "score": 0.9,
                }
            ],
        },
        "provider": {
            "provider": "stub",
            "selected_model": "gpt-4o-mini",
            "attempts": 1,
            "fallback_chain": ["stub"],
            "provider_request_hash": "provider-req-hash",
            "provider_response_hash": "provider-resp-hash",
        },
        "usage": {
            "tokens_in": 10,
            "tokens_out": 12,
            "cost_usd": 0.000022,
        },
        "integrity": {
            "prev_hash": "",
            "payload_hash": "payload-hash",
            "chain_verified": True,
        },
        "source": {
            "audit_log_path": "artifacts/audit/events.jsonl",
            "event_id": "evt-1",
        },
    }
    validate(instance=fixture, schema=schema)
