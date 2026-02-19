"""Tests for provider stream fallback — verifying that streaming requests
fall back to secondary providers on retryable errors and that chain
exhaustion raises the expected error."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.providers.base import ProviderCapabilities, ProviderError
from app.providers.registry import (
    ProviderEntry,
    ProviderRegistry,
    route_stream_with_fallback,
)
from app.providers.stub import StubProvider


class _FailingStreamProvider:
    """Provider that raises a retryable error on chat_stream."""

    def __init__(self, error_code: int = 429):
        self._error_code = error_code

    async def chat(
        self, model: str, messages: list[dict[str, str]], max_tokens: int | None
    ) -> dict[str, object]:
        _ = model, messages, max_tokens
        return {}

    async def embeddings(self, model: str, inputs: list[str]) -> dict[str, object]:
        _ = model, inputs
        return {}

    async def chat_stream(
        self, model: str, messages: list[dict[str, str]], max_tokens: int | None
    ) -> AsyncIterator[dict[str, object]]:
        raise ProviderError(
            status_code=self._error_code,
            code=f"provider_{self._error_code}",
            message=f"Simulated {self._error_code} error",
        )
        yield  # type: ignore[misc]  # pragma: no cover


def _make_registry(*entries: ProviderEntry) -> ProviderRegistry:
    registry = ProviderRegistry()
    for entry in entries:
        registry.register(entry)
    return registry


def test_stream_fallback_on_429_to_secondary() -> None:
    """Primary provider returns 429 → should fall back to secondary for streaming."""
    stub = StubProvider()
    registry = _make_registry(
        ProviderEntry(
            name="primary",
            provider=_FailingStreamProvider(429),  # type: ignore[arg-type]
            capabilities=ProviderCapabilities(chat=True, streaming=True),
            priority=1,
        ),
        ProviderEntry(
            name="secondary",
            provider=stub,
            capabilities=ProviderCapabilities(chat=True, streaming=True),
            priority=10,
        ),
    )

    result = asyncio.run(
        route_stream_with_fallback(
            registry=registry,
            primary="primary",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=32,
        )
    )
    assert result.provider_name == "secondary"
    assert result.attempts == 2
    assert result.fallback_chain == ["primary", "secondary"]
    assert result.first_chunk is not None


def test_stream_fallback_chain_exhausted_raises() -> None:
    """When all providers in the chain fail with retryable errors,
    the last ProviderError should be raised."""
    registry = _make_registry(
        ProviderEntry(
            name="p1",
            provider=_FailingStreamProvider(502),  # type: ignore[arg-type]
            capabilities=ProviderCapabilities(chat=True, streaming=True),
            priority=1,
        ),
        ProviderEntry(
            name="p2",
            provider=_FailingStreamProvider(503),  # type: ignore[arg-type]
            capabilities=ProviderCapabilities(chat=True, streaming=True),
            priority=10,
        ),
    )

    with pytest.raises(ProviderError, match="Simulated 503"):
        asyncio.run(
            route_stream_with_fallback(
                registry=registry,
                primary="p1",
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=32,
            )
        )


def test_stream_no_eligible_streaming_providers_raises() -> None:
    """When no providers support streaming, raise a clear ProviderError."""
    stub = StubProvider()
    registry = _make_registry(
        ProviderEntry(
            name="chat-only",
            provider=stub,
            capabilities=ProviderCapabilities(chat=True, streaming=False),
            priority=1,
        ),
    )

    with pytest.raises(ProviderError, match="No eligible providers"):
        asyncio.run(
            route_stream_with_fallback(
                registry=registry,
                primary="chat-only",
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=32,
            )
        )
