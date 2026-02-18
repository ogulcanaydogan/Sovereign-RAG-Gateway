from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


class ProviderError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        error_type: str = "provider",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.error_type = error_type


@dataclass(frozen=True)
class ProviderCapabilities:
    chat: bool = True
    embeddings: bool = True
    streaming: bool = False
    model_prefixes: tuple[str, ...] = ()

    def supports_model(self, model: str) -> bool:
        if not self.model_prefixes:
            return True
        return any(model.startswith(prefix) for prefix in self.model_prefixes)


class ChatProvider(Protocol):
    async def chat(
        self, model: str, messages: list[dict[str, str]], max_tokens: int | None
    ) -> dict[str, object]:
        """Return normalized provider response payload."""

    def chat_stream(
        self, model: str, messages: list[dict[str, str]], max_tokens: int | None
    ) -> AsyncIterator[dict[str, object]]:
        """Yield normalized OpenAI-style streaming chunks."""

    async def embeddings(self, model: str, inputs: list[str]) -> dict[str, object]:
        """Return normalized embeddings payload."""
