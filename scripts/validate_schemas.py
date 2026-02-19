#!/usr/bin/env python3
import json
from pathlib import Path

from jsonschema import validate


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    contracts = root / "docs" / "contracts" / "v1"

    policy_schema = json.loads(
        (contracts / "policy-decision.schema.json").read_text(encoding="utf-8")
    )
    audit_schema = json.loads((contracts / "audit-event.schema.json").read_text(encoding="utf-8"))
    citations_schema = json.loads(
        (contracts / "citations-extension.schema.json").read_text(encoding="utf-8")
    )

    policy_fixture = {
        "decision_id": "fixture-1",
        "allow": True,
        "policy_hash": "abc",
        "evaluated_at": "2026-02-17T00:00:00Z",
        "transforms": [],
    }
    audit_fixture = {
        "event_id": "evt-1",
        "request_id": "req-1",
        "tenant_id": "t1",
        "user_id": "u1",
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
        "tokens_out": 10,
        "cost_usd": 0.00002,
        "policy_hash": "abc",
        "trace_id": "req-1",
        "budget": {
            "tenant_id": "t1",
            "ceiling": 1000,
            "used": 50,
            "remaining": 950,
            "window_seconds": 3600,
            "utilization_pct": 5.0,
        },
        "webhook_events": [
            {"event_type": "redaction_hit", "delivery_success_count": 1}
        ],
        "input_redaction_count": 0,
        "output_redaction_count": 0,
        "payload_hash": "h1",
        "prev_hash": "",
        "created_at": "2026-02-17T00:00:00Z",
    }
    evidence_schema = json.loads(
        (contracts / "evidence-bundle.schema.json").read_text(encoding="utf-8")
    )
    evidence_fixture = {
        "bundle_version": "v1",
        "request_id": "req-1",
        "generated_at": "2026-02-17T00:00:00Z",
        "policy": {
            "decision_id": "decision-1",
            "policy_hash": "abc",
            "policy_mode": "enforce",
            "allow": True,
            "deny_reason": None,
        },
        "redaction": {
            "count": 0,
            "request_payload_hash": "req-hash",
            "redacted_payload_hash": "redacted-hash",
        },
        "retrieval": {
            "enabled": False,
            "connector": None,
            "citations": [],
        },
        "provider": {
            "provider": "stub",
            "selected_model": "gpt-4o-mini",
            "attempts": 1,
            "fallback_chain": [],
            "provider_request_hash": "provider-req-hash",
            "provider_response_hash": "provider-resp-hash",
        },
        "usage": {
            "tokens_in": 10,
            "tokens_out": 10,
            "cost_usd": 0.00002,
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
    citations_fixture = {
        "choices": [
            {
                "message": {
                    "citations": [
                        {
                            "source_id": "src-1",
                            "connector": "filesystem",
                            "uri": "file:///tmp/doc.txt",
                            "chunk_id": "chunk-1",
                            "score": 0.99,
                        }
                    ]
                }
            }
        ]
    }

    validate(instance=policy_fixture, schema=policy_schema)
    validate(instance=audit_fixture, schema=audit_schema)
    validate(instance=citations_fixture, schema=citations_schema)
    validate(instance=evidence_fixture, schema=evidence_schema)
    print("Schema validation succeeded")


if __name__ == "__main__":
    main()
