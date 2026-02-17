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


class ChatProvider(Protocol):
    async def chat(
        self, model: str, messages: list[dict[str, str]], max_tokens: int | None
    ) -> dict[str, object]:
        """Return normalized provider response payload."""

    async def embeddings(self, model: str, inputs: list[str]) -> dict[str, object]:
        """Return normalized embeddings payload."""
