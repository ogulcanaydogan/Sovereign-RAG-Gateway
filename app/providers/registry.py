"""Provider registry with cost-aware selection and fallback routing."""

import logging
from dataclasses import dataclass, field

from app.providers.base import ChatProvider, ProviderError

logger = logging.getLogger("srg.providers")


@dataclass(frozen=True)
class ProviderCost:
    """Cost per token in USD for a provider."""

    input_per_token: float = 0.0
    output_per_token: float = 0.0


@dataclass
class ProviderEntry:
    """A registered provider with its cost metadata and priority."""

    name: str
    provider: ChatProvider
    cost: ProviderCost = field(default_factory=ProviderCost)
    priority: int = 0
    enabled: bool = True


class ProviderRegistry:
    """Registry of LLM providers with cost-aware selection and fallback."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderEntry] = {}

    def register(self, entry: ProviderEntry) -> None:
        self._providers[entry.name] = entry
        logger.info(
            "provider_registered",
            extra={"provider": entry.name, "priority": entry.priority},
        )

    def get(self, name: str) -> ProviderEntry | None:
        return self._providers.get(name)

    def list_providers(self) -> list[ProviderEntry]:
        return sorted(
            [e for e in self._providers.values() if e.enabled],
            key=lambda e: e.priority,
        )

    def cheapest_for_tokens(
        self, estimated_input: int, estimated_output: int,
    ) -> ProviderEntry | None:
        """Select the cheapest enabled provider for a given token estimate."""
        enabled = [e for e in self._providers.values() if e.enabled]
        if not enabled:
            return None
        return min(
            enabled,
            key=lambda e: (
                e.cost.input_per_token * estimated_input
                + e.cost.output_per_token * estimated_output
            ),
        )

    def fallback_chain(self, primary: str) -> list[ProviderEntry]:
        """Return providers ordered for fallback: primary first, then by priority."""
        entries = [e for e in self._providers.values() if e.enabled]
        primary_entry = self._providers.get(primary)
        if primary_entry and primary_entry.enabled:
            others = sorted(
                [e for e in entries if e.name != primary],
                key=lambda e: e.priority,
            )
            return [primary_entry] + others
        return sorted(entries, key=lambda e: e.priority)


@dataclass
class ProviderRoutingResult:
    """Result of a provider routing attempt including fallback history."""

    provider_name: str
    result: dict[str, object]
    fallback_chain: list[str]
    attempts: int


async def route_with_fallback(
    registry: ProviderRegistry,
    primary: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int | None,
    retryable_codes: frozenset[int] = frozenset({429, 502, 503}),
) -> ProviderRoutingResult:
    """Route a chat request through providers with automatic fallback.

    Tries the primary provider first. On retryable errors (429, 502, 503),
    falls through to the next provider in priority order.
    """
    chain = registry.fallback_chain(primary)
    if not chain:
        raise ProviderError(
            status_code=503,
            code="no_providers_available",
            message="No enabled providers in registry",
        )

    attempts: list[str] = []
    last_error: ProviderError | None = None

    for entry in chain:
        attempts.append(entry.name)
        try:
            result = await entry.provider.chat(model, messages, max_tokens)
            logger.info(
                "provider_routed",
                extra={
                    "provider": entry.name,
                    "attempts": len(attempts),
                    "fallback_chain": attempts,
                },
            )
            return ProviderRoutingResult(
                provider_name=entry.name,
                result=result,
                fallback_chain=attempts,
                attempts=len(attempts),
            )
        except ProviderError as exc:
            last_error = exc
            if exc.status_code not in retryable_codes:
                raise
            logger.warning(
                "provider_fallback",
                extra={
                    "failed_provider": entry.name,
                    "error_code": exc.status_code,
                    "reason": exc.code,
                    "remaining": len(chain) - len(attempts),
                },
            )

    assert last_error is not None
    raise last_error


async def route_embeddings_with_fallback(
    registry: ProviderRegistry,
    primary: str,
    model: str,
    inputs: list[str],
    retryable_codes: frozenset[int] = frozenset({429, 502, 503}),
) -> ProviderRoutingResult:
    """Route an embeddings request through providers with automatic fallback."""
    chain = registry.fallback_chain(primary)
    if not chain:
        raise ProviderError(
            status_code=503,
            code="no_providers_available",
            message="No enabled providers in registry",
        )

    attempts: list[str] = []
    last_error: ProviderError | None = None

    for entry in chain:
        attempts.append(entry.name)
        try:
            result = await entry.provider.embeddings(model, inputs)
            return ProviderRoutingResult(
                provider_name=entry.name,
                result=result,
                fallback_chain=attempts,
                attempts=len(attempts),
            )
        except ProviderError as exc:
            last_error = exc
            if exc.status_code not in retryable_codes:
                raise
            logger.warning(
                "embeddings_provider_fallback",
                extra={
                    "failed_provider": entry.name,
                    "error_code": exc.status_code,
                    "remaining": len(chain) - len(attempts),
                },
            )

    assert last_error is not None
    raise last_error
