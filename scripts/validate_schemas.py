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
        "transforms_applied": [],
        "redaction_count": 0,
        "tokens_in": 10,
        "tokens_out": 10,
        "cost_usd": 0.00002,
        "policy_hash": "abc",
        "payload_hash": "h1",
        "prev_hash": "",
        "created_at": "2026-02-17T00:00:00Z",
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
    print("Schema validation succeeded")


if __name__ == "__main__":
    main()
