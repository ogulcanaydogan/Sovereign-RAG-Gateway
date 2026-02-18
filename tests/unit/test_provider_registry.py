import asyncio
from collections.abc import AsyncIterator

import pytest

from app.providers.base import ProviderCapabilities, ProviderError
from app.providers.registry import (
    ProviderCost,
    ProviderEntry,
    ProviderRegistry,
    ProviderRoutingResult,
    route_embeddings_with_fallback,
    route_stream_with_fallback,
    route_with_fallback,
)
from app.providers.stub import StubProvider


def _make_registry(*entries: ProviderEntry) -> ProviderRegistry:
    registry = ProviderRegistry()
    for entry in entries:
        registry.register(entry)
    return registry


def test_register_and_list() -> None:
    stub = StubProvider()
    registry = _make_registry(
        ProviderEntry(name="a", provider=stub, priority=10),
        ProviderEntry(name="b", provider=stub, priority=5),
    )
    names = [e.name for e in registry.list_providers()]
    assert names == ["b", "a"]


def test_disabled_provider_excluded() -> None:
    stub = StubProvider()
    registry = _make_registry(
        ProviderEntry(name="a", provider=stub, priority=10),
        ProviderEntry(name="b", provider=stub, priority=5, enabled=False),
    )
    names = [e.name for e in registry.list_providers()]
    assert names == ["a"]


def test_cheapest_for_tokens() -> None:
    stub = StubProvider()
    registry = _make_registry(
        ProviderEntry(
            name="expensive",
            provider=stub,
            cost=ProviderCost(input_per_token=0.03, output_per_token=0.06),
        ),
        ProviderEntry(
            name="cheap",
            provider=stub,
            cost=ProviderCost(input_per_token=0.001, output_per_token=0.002),
        ),
    )
    result = registry.cheapest_for_tokens(1000, 500)
    assert result is not None
    assert result.name == "cheap"


def test_fallback_chain_primary_first() -> None:
    stub = StubProvider()
    registry = _make_registry(
        ProviderEntry(name="primary", provider=stub, priority=10),
        ProviderEntry(name="secondary", provider=stub, priority=5),
    )
    chain = registry.fallback_chain("primary")
    names = [e.name for e in chain]
    assert names[0] == "primary"
    assert "secondary" in names


def test_route_with_fallback_success() -> None:
    stub = StubProvider()
    registry = _make_registry(
        ProviderEntry(name="primary", provider=stub, priority=0),
    )
    result = asyncio.run(
        route_with_fallback(
            registry, "primary", "gpt-4o-mini", [{"role": "user", "content": "hi"}], None
        )
    )
    assert isinstance(result, ProviderRoutingResult)
    assert result.provider_name == "primary"
    assert result.attempts == 1
    assert result.fallback_chain == ["primary"]


def test_route_with_fallback_on_429() -> None:
    stub = StubProvider()
    registry = _make_registry(
        ProviderEntry(name="primary", provider=stub, priority=0),
        ProviderEntry(name="secondary", provider=stub, priority=10),
    )
    with pytest.raises(ProviderError):
        asyncio.run(
            route_with_fallback(
                registry,
                "primary",
                "error-429-model",
                [{"role": "user", "content": "hi"}],
                None,
            )
        )


def test_route_no_providers_raises() -> None:
    registry = ProviderRegistry()
    with pytest.raises(ProviderError, match="No eligible providers"):
        asyncio.run(
            route_with_fallback(
                registry, "missing", "gpt-4o-mini", [{"role": "user", "content": "hi"}], None
            )
        )


def test_eligible_chain_filters_streaming_and_provider_allowlist() -> None:
    stub = StubProvider()
    registry = _make_registry(
        ProviderEntry(
            name="a",
            provider=stub,
            priority=1,
            capabilities=ProviderCapabilities(streaming=False),
        ),
        ProviderEntry(
            name="b",
            provider=stub,
            priority=2,
            capabilities=ProviderCapabilities(streaming=True),
        ),
    )
    chain = registry.eligible_chain(
        primary="a",
        operation="chat",
        model="gpt-4o-mini",
        requires_stream=True,
        allowed_provider_names={"b"},
    )
    assert [entry.name for entry in chain] == ["b"]


def test_route_embeddings_filters_by_capability() -> None:
    stub = StubProvider()
    registry = _make_registry(
        ProviderEntry(
            name="chat-only",
            provider=stub,
            priority=1,
            capabilities=ProviderCapabilities(chat=True, embeddings=False),
        ),
        ProviderEntry(
            name="full",
            provider=stub,
            priority=2,
            capabilities=ProviderCapabilities(chat=True, embeddings=True),
        ),
    )
    result = asyncio.run(
        route_embeddings_with_fallback(
            registry=registry,
            primary="chat-only",
            model="text-embedding-3-small",
            inputs=["hello"],
        )
    )
    assert result.provider_name == "full"


class _StreamOnlyProvider:
    async def chat(
        self, model: str, messages: list[dict[str, str]], max_tokens: int | None
    ) -> dict[str, object]:
        _ = model
        _ = messages
        _ = max_tokens
        return {"id": "unused"}

    async def embeddings(self, model: str, inputs: list[str]) -> dict[str, object]:
        _ = model
        _ = inputs
        return {"object": "list", "data": [], "model": "unused", "usage": {}}

    async def chat_stream(
        self, model: str, messages: list[dict[str, str]], max_tokens: int | None
    ) -> AsyncIterator[dict[str, object]]:
        _ = model
        _ = messages
        _ = max_tokens
        yield {"id": "chunk-1", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}


def test_route_stream_with_fallback_success() -> None:
    registry = _make_registry(
        ProviderEntry(
            name="streaming",
            provider=_StreamOnlyProvider(),  # type: ignore[arg-type]
            capabilities=ProviderCapabilities(chat=True, embeddings=False, streaming=True),
            priority=1,
        )
    )
    routed = asyncio.run(
        route_stream_with_fallback(
            registry=registry,
            primary="streaming",
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=32,
        )
    )
    chunks = asyncio.run(_collect_chunks(routed.stream))
    assert routed.provider_name == "streaming"
    assert routed.first_chunk is not None
    assert routed.first_chunk["choices"][0]["finish_reason"] == "stop"
    assert chunks == []


async def _collect_chunks(stream: AsyncIterator[dict[str, object]]) -> list[dict[str, object]]:
    return [chunk async for chunk in stream]
