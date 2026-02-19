import asyncio
import json

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
    assert body["event_type"] == "policy_denied"
    assert body["gateway_version"] == "0.4.0-rc1"


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
