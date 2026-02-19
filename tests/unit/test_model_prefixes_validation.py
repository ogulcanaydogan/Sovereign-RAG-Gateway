"""Tests for model_prefixes validation in provider configuration parsing
and capability-based model eligibility filtering."""

from app.providers.base import ProviderCapabilities
from app.providers.registry import ProviderEntry, ProviderRegistry
from app.providers.stub import StubProvider


def _make_entry(name: str, prefixes: tuple[str, ...] = ()) -> ProviderEntry:
    return ProviderEntry(
        name=name,
        provider=StubProvider(),
        capabilities=ProviderCapabilities(
            chat=True,
            embeddings=True,
            streaming=True,
            model_prefixes=prefixes,
        ),
        priority=10,
    )


def test_model_prefix_match_allows_provider() -> None:
    """A provider with model_prefixes=('gpt-4',) should be eligible for 'gpt-4o-mini'."""
    registry = ProviderRegistry()
    registry.register(_make_entry("openai", prefixes=("gpt-4", "gpt-3.5")))

    chain = registry.eligible_chain(
        primary="openai",
        operation="chat",
        model="gpt-4o-mini",
    )
    assert len(chain) == 1
    assert chain[0].name == "openai"


def test_model_prefix_mismatch_excludes_provider() -> None:
    """A provider with model_prefixes=('gpt-4',) should NOT be eligible for 'claude-3'."""
    registry = ProviderRegistry()
    registry.register(_make_entry("openai", prefixes=("gpt-4",)))

    chain = registry.eligible_chain(
        primary="openai",
        operation="chat",
        model="claude-3-sonnet",
    )
    assert len(chain) == 0


def test_empty_model_prefixes_allows_all_models() -> None:
    """A provider with empty model_prefixes should accept any model."""
    registry = ProviderRegistry()
    registry.register(_make_entry("universal", prefixes=()))

    chain = registry.eligible_chain(
        primary="universal",
        operation="chat",
        model="any-model-name-at-all",
    )
    assert len(chain) == 1


def test_model_prefix_routes_to_correct_provider() -> None:
    """When multiple providers have different prefixes, routing selects the matching one."""
    registry = ProviderRegistry()
    registry.register(_make_entry("openai", prefixes=("gpt-4",)))
    registry.register(
        ProviderEntry(
            name="anthropic",
            provider=StubProvider(),
            capabilities=ProviderCapabilities(
                chat=True,
                embeddings=False,
                streaming=False,
                model_prefixes=("claude-",),
            ),
            priority=20,
        )
    )

    gpt_chain = registry.eligible_chain(primary="openai", operation="chat", model="gpt-4o")
    assert [e.name for e in gpt_chain] == ["openai"]

    claude_chain = registry.eligible_chain(
        primary="anthropic", operation="chat", model="claude-3-haiku"
    )
    assert [e.name for e in claude_chain] == ["anthropic"]
