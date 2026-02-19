"""Provider registry with cost-aware selection and fallback routing."""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

from app.providers.base import ChatProvider, ProviderCapabilities, ProviderError

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
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)
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

    def eligible_chain(
        self,
        primary: str,
        operation: Literal["chat", "embeddings"],
        model: str,
        requires_stream: bool = False,
        allowed_provider_names: set[str] | None = None,
    ) -> list[ProviderEntry]:
        chain = self.fallback_chain(primary)
        return [
            entry
            for entry in chain
            if self._is_eligible(
                entry=entry,
                operation=operation,
                model=model,
                requires_stream=requires_stream,
                allowed_provider_names=allowed_provider_names,
            )
        ]

    @staticmethod
    def _is_eligible(
        entry: ProviderEntry,
        operation: Literal["chat", "embeddings"],
        model: str,
        requires_stream: bool,
        allowed_provider_names: set[str] | None,
    ) -> bool:
        if not entry.enabled:
            return False
        if allowed_provider_names is not None and entry.name not in allowed_provider_names:
            return False
        if operation == "chat" and not entry.capabilities.chat:
            return False
        if operation == "embeddings" and not entry.capabilities.embeddings:
            return False
        if requires_stream and not entry.capabilities.streaming:
            return False
        return entry.capabilities.supports_model(model)


@dataclass
class ProviderRoutingResult:
    """Result of a provider routing attempt including fallback history."""

    provider_name: str
    result: dict[str, object]
    fallback_chain: list[str]
    attempts: int


@dataclass
class ProviderStreamRoutingResult:
    """Result of a provider stream routing attempt including fallback history."""

    provider_name: str
    stream: AsyncIterator[dict[str, object]]
    first_chunk: dict[str, object] | None
    fallback_chain: list[str]
    attempts: int


async def route_with_fallback(
    registry: ProviderRegistry,
    primary: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int | None,
    allowed_provider_names: set[str] | None = None,
    retryable_codes: frozenset[int] = frozenset({429, 502, 503}),
) -> ProviderRoutingResult:
    """Route a chat request through providers with automatic fallback.

    Tries the primary provider first. On retryable errors (429, 502, 503),
    falls through to the next provider in priority order.
    """
    chain = registry.eligible_chain(
        primary=primary,
        operation="chat",
        model=model,
        requires_stream=False,
        allowed_provider_names=allowed_provider_names,
    )
    if not chain:
        raise ProviderError(
            status_code=503,
            code="no_provider_match",
            message="No eligible providers for requested chat operation",
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
    allowed_provider_names: set[str] | None = None,
    retryable_codes: frozenset[int] = frozenset({429, 502, 503}),
) -> ProviderRoutingResult:
    """Route an embeddings request through providers with automatic fallback."""
    chain = registry.eligible_chain(
        primary=primary,
        operation="embeddings",
        model=model,
        allowed_provider_names=allowed_provider_names,
    )
    if not chain:
        raise ProviderError(
            status_code=503,
            code="no_provider_match",
            message="No eligible providers for requested embeddings operation",
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


async def route_stream_with_fallback(
    registry: ProviderRegistry,
    primary: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int | None,
    allowed_provider_names: set[str] | None = None,
    retryable_codes: frozenset[int] = frozenset({429, 502, 503}),
) -> ProviderStreamRoutingResult:
    """Route a streaming chat request through providers with automatic fallback."""
    chain = registry.eligible_chain(
        primary=primary,
        operation="chat",
        model=model,
        requires_stream=True,
        allowed_provider_names=allowed_provider_names,
    )
    if not chain:
        raise ProviderError(
            status_code=503,
            code="no_provider_match",
            message="No eligible providers for requested streaming chat operation",
        )

    attempts: list[str] = []
    last_error: ProviderError | None = None

    for entry in chain:
        attempts.append(entry.name)
        try:
            stream = entry.provider.chat_stream(model, messages, max_tokens)
            first_chunk: dict[str, object] | None
            try:
                first_chunk = await anext(stream)
            except StopAsyncIteration:
                first_chunk = None
            return ProviderStreamRoutingResult(
                provider_name=entry.name,
                stream=stream,
                first_chunk=first_chunk,
                fallback_chain=attempts,
                attempts=len(attempts),
            )
        except ProviderError as exc:
            last_error = exc
            if exc.status_code not in retryable_codes:
                raise
            logger.warning(
                "stream_provider_fallback",
                extra={
                    "failed_provider": entry.name,
                    "error_code": exc.status_code,
                    "remaining": len(chain) - len(attempts),
                },
            )

    assert last_error is not None
    raise last_error
