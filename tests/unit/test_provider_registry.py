import asyncio

import pytest

from app.providers.base import ProviderError
from app.providers.registry import (
    ProviderCost,
    ProviderEntry,
    ProviderRegistry,
    ProviderRoutingResult,
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
    result = asyncio.get_event_loop().run_until_complete(
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
        asyncio.get_event_loop().run_until_complete(
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
    with pytest.raises(ProviderError, match="No enabled providers"):
        asyncio.get_event_loop().run_until_complete(
            route_with_fallback(
                registry, "missing", "gpt-4o-mini", [{"role": "user", "content": "hi"}], None
            )
        )
