import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.webhooks.dead_letter_store import (
    JsonlDeadLetterStore,
    SQLiteDeadLetterStore,
    create_dead_letter_store,
)


def test_jsonl_dead_letter_store_writes_and_prunes(tmp_path: Path) -> None:
    store = JsonlDeadLetterStore(
        path=tmp_path / "dead_letter.jsonl",
        retention_days=1,
    )
    old_timestamp = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    new_timestamp = datetime.now(UTC).isoformat()

    first_result = store.write(
        {
            "timestamp": old_timestamp,
            "event_type": "policy_denied",
            "endpoint_url": "https://example.test/old",
            "attempt_count": 1,
            "idempotency_key": "old",
            "body": {"event_type": "policy_denied"},
        }
    )
    result = store.write(
        {
            "timestamp": new_timestamp,
            "event_type": "policy_denied",
            "endpoint_url": "https://example.test/new",
            "attempt_count": 1,
            "idempotency_key": "new",
            "body": {"event_type": "policy_denied"},
        }
    )

    assert result.written == 1
    assert first_result.pruned + result.pruned >= 1
    rows = store.load()
    assert len(rows) == 1
    assert rows[0]["endpoint_url"] == "https://example.test/new"


def test_sqlite_dead_letter_store_writes_loads_and_prunes(tmp_path: Path) -> None:
    store = SQLiteDeadLetterStore(
        path=tmp_path / "dead_letter.db",
        retention_days=1,
    )
    old_timestamp = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    new_timestamp = datetime.now(UTC).isoformat()

    first_result = store.write(
        {
            "timestamp": old_timestamp,
            "event_type": "provider_error",
            "endpoint_url": "https://example.test/old",
            "attempt_count": 2,
            "idempotency_key": "old",
            "body": {"event_type": "provider_error"},
        }
    )
    result = store.write(
        {
            "timestamp": new_timestamp,
            "event_type": "provider_error",
            "endpoint_url": "https://example.test/new",
            "attempt_count": 1,
            "idempotency_key": "new",
            "body": {"event_type": "provider_error"},
        }
    )

    assert result.written == 1
    assert first_result.pruned + result.pruned >= 1
    rows = store.load()
    assert len(rows) == 1
    assert rows[0]["endpoint_url"] == "https://example.test/new"


def test_create_dead_letter_store_selects_backend(tmp_path: Path) -> None:
    sqlite_store = create_dead_letter_store(
        backend="sqlite",
        path=tmp_path / "dead_letter.db",
        retention_days=30,
    )
    jsonl_store = create_dead_letter_store(
        backend="jsonl",
        path=tmp_path / "dead_letter.jsonl",
        retention_days=30,
    )
    assert sqlite_store is not None
    assert jsonl_store is not None
    assert sqlite_store.backend == "sqlite"
    assert jsonl_store.backend == "jsonl"


def test_jsonl_load_round_trip_body(tmp_path: Path) -> None:
    path = tmp_path / "dead_letter.jsonl"
    path.write_text(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "event_type": "budget_exceeded",
                "endpoint_url": "https://example.test",
                "attempt_count": 1,
                "idempotency_key": "abc",
                "body": {"event_type": "budget_exceeded", "payload": {"request_id": "req-1"}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    store = JsonlDeadLetterStore(path=path)
    rows = store.load()
    assert rows[0]["body"]["payload"]["request_id"] == "req-1"
