import json
from pathlib import Path

from scripts.replay_webhook_dead_letter import (
    build_idempotency_key,
    load_dead_letter,
    replay_dead_letter,
)


def test_load_dead_letter_reads_jsonl(tmp_path: Path) -> None:
    dead_letter = tmp_path / "dlq.jsonl"
    dead_letter.write_text(
        json.dumps({"event_type": "policy_denied", "endpoint_url": "https://example", "body": {}})
        + "\n",
        encoding="utf-8",
    )
    rows = load_dead_letter(dead_letter)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "policy_denied"


def test_replay_dead_letter_filters_and_limits() -> None:
    records = [
        {
            "event_type": "policy_denied",
            "endpoint_url": "https://example.test/a",
            "idempotency_key": "orig-1",
            "body": {"event_type": "policy_denied"},
        },
        {
            "event_type": "redaction_hit",
            "endpoint_url": "https://example.test/b",
            "idempotency_key": "orig-2",
            "body": {"event_type": "redaction_hit"},
        },
    ]
    summary = replay_dead_letter(
        records=records,
        event_types={"redaction_hit"},
        max_events=1,
        dry_run=True,
    )
    assert summary.considered_records == 1
    assert summary.attempted == 1
    assert summary.succeeded == 1
    assert summary.failed == 0


def test_replay_dead_letter_posts_with_replay_headers() -> None:
    records = [
        {
            "event_type": "budget_exceeded",
            "endpoint_url": "https://example.test/hook",
            "idempotency_key": "orig-key",
            "body": {"event_type": "budget_exceeded", "payload": {"request_id": "req-1"}},
        }
    ]
    captured: list[dict[str, object]] = []

    def fake_sender(
        endpoint_url: str,
        body_json: str,
        headers: dict[str, str],
        timeout_s: float,
    ) -> tuple[int, str]:
        captured.append(
            {
                "endpoint": endpoint_url,
                "body": body_json,
                "headers": headers,
                "timeout_s": timeout_s,
            }
        )
        return (202, "")

    summary = replay_dead_letter(
        records=records,
        timeout_s=3.5,
        idempotency_suffix="ci-replay",
        sender=fake_sender,
    )
    assert summary.failed == 0
    assert summary.succeeded == 1
    assert len(captured) == 1
    headers = captured[0]["headers"]
    assert isinstance(headers, dict)
    assert headers["X-SRG-Replay"] == "true"
    assert headers["X-SRG-Original-Idempotency-Key"] == "orig-key"
    assert headers["X-SRG-Idempotency-Key"] != "orig-key"
    assert captured[0]["timeout_s"] == 3.5


def test_replay_dead_letter_records_failure_for_non_2xx() -> None:
    records = [
        {
            "event_type": "provider_error",
            "endpoint_url": "https://example.test/hook",
            "idempotency_key": "orig-key",
            "body": {"event_type": "provider_error"},
        }
    ]

    def fake_sender(
        endpoint_url: str,
        body_json: str,
        headers: dict[str, str],
        timeout_s: float,
    ) -> tuple[int, str]:
        _ = endpoint_url, body_json, headers, timeout_s
        return (500, "")

    summary = replay_dead_letter(records=records, sender=fake_sender)
    assert summary.failed == 1
    assert summary.failures[0].status_code == 500


def test_build_idempotency_key_is_deterministic() -> None:
    body = {"event_type": "policy_denied", "payload": {"request_id": "req-1"}}
    first = build_idempotency_key(
        endpoint_url="https://example.test/webhook",
        body=body,
        original_key="orig-key",
        suffix="replay",
    )
    second = build_idempotency_key(
        endpoint_url="https://example.test/webhook",
        body=body,
        original_key="orig-key",
        suffix="replay",
    )
    assert first == second
