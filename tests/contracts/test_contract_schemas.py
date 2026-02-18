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
