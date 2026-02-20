import asyncio
import json
from pathlib import Path

from app.webhooks.dispatcher import (
    WebhookDispatcher,
    WebhookEndpoint,
    WebhookEventType,
)


def test_webhook_dispatcher_delivers_to_subscribed_endpoint(
    monkeypatch,
) -> None:
    captured: list[dict[str, object]] = []

    async def fake_post(self, url: str, content: str, headers: dict[str, str]):  # type: ignore[no-untyped-def]  # noqa: ANN001
        captured.append(
            {
                "url": url,
                "content": content,
                "headers": headers,
            }
        )

        class _Response:
            status_code = 200

        return _Response()

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    dispatcher = WebhookDispatcher(
        endpoints=[
            WebhookEndpoint(
                url="https://example.test/webhook",
                secret="secret",
                event_types=frozenset({WebhookEventType.POLICY_DENIED}),
            )
        ]
    )

    results = asyncio.run(
        dispatcher.dispatch(
            WebhookEventType.POLICY_DENIED,
            {"request_id": "req-1"},
        )
    )
    assert len(results) == 1
    assert results[0].success is True
    assert len(captured) == 1
    assert captured[0]["url"] == "https://example.test/webhook"
    assert "X-SRG-Signature" in captured[0]["headers"]  # type: ignore[index]

    body = json.loads(str(captured[0]["content"]))
    assert body["event_id"].startswith("evt-")
    assert body["event_type"] == "policy_denied"
    assert body["gateway_version"] == "0.5.0"
    assert "X-SRG-Idempotency-Key" in captured[0]["headers"]  # type: ignore[index]


def test_webhook_dispatcher_should_fire_only_for_subscribed_event() -> None:
    dispatcher = WebhookDispatcher(
        endpoints=[
            WebhookEndpoint(
                url="https://example.test/webhook",
                event_types=frozenset({WebhookEventType.REDACTION_HIT}),
            )
        ]
    )
    assert dispatcher.should_fire(WebhookEventType.REDACTION_HIT) is True
    assert dispatcher.should_fire(WebhookEventType.BUDGET_EXCEEDED) is False


def test_webhook_dispatcher_retries_retryable_status(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    status_codes = [503, 200]

    async def fake_post(self, url: str, content: str, headers: dict[str, str]):  # type: ignore[no-untyped-def]  # noqa: ANN001
        calls.append({"url": url, "content": content, "headers": headers})

        class _Response:
            status_code = status_codes.pop(0)

        return _Response()

    async def fake_sleep(duration: float) -> None:
        _ = duration

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    monkeypatch.setattr("app.webhooks.dispatcher.asyncio.sleep", fake_sleep)

    dispatcher = WebhookDispatcher(
        endpoints=[
            WebhookEndpoint(
                url="https://example.test/retry",
                event_types=frozenset({WebhookEventType.PROVIDER_ERROR}),
            )
        ],
        max_retries=2,
        backoff_base_s=0.0,
        backoff_max_s=0.0,
    )
    results = asyncio.run(
        dispatcher.dispatch(WebhookEventType.PROVIDER_ERROR, {"request_id": "req-retry"})
    )
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].attempt_count == 2
    assert len(calls) == 2
    assert results[0].idempotency_key != ""


def test_webhook_dispatcher_writes_dead_letter_on_failure(tmp_path: Path, monkeypatch) -> None:
    dead_letter = tmp_path / "webhook_dlq.jsonl"

    async def fake_post(self, url: str, content: str, headers: dict[str, str]):  # type: ignore[no-untyped-def]  # noqa: ANN001
        _ = url, content, headers

        class _Response:
            status_code = 500

        return _Response()

    async def fake_sleep(duration: float) -> None:
        _ = duration

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    monkeypatch.setattr("app.webhooks.dispatcher.asyncio.sleep", fake_sleep)

    dispatcher = WebhookDispatcher(
        endpoints=[
            WebhookEndpoint(
                url="https://example.test/fail",
                event_types=frozenset({WebhookEventType.BUDGET_EXCEEDED}),
            )
        ],
        max_retries=1,
        backoff_base_s=0.0,
        backoff_max_s=0.0,
        dead_letter_path=dead_letter,
    )
    results = asyncio.run(
        dispatcher.dispatch(WebhookEventType.BUDGET_EXCEEDED, {"request_id": "req-fail"})
    )
    assert len(results) == 1
    assert results[0].success is False
    lines = dead_letter.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event_type"] == "budget_exceeded"
    assert record["attempt_count"] == 2
    assert record["idempotency_key"] != ""
