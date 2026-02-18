import asyncio

import pytest

from app.providers.anthropic import AnthropicProvider
from app.providers.base import ProviderError


def test_anthropic_chat_normalizes_response() -> None:
    provider = AnthropicProvider(api_key="secret")

    async def fake_post(path: str, body: dict[str, object]) -> dict[str, object]:
        assert path == "/v1/messages"
        assert body["model"] == "claude-3-5-sonnet-latest"
        assert body["system"] == "Be concise."
        assert body["messages"] == [{"role": "user", "content": "hello"}]
        return {
            "id": "msg_123",
            "model": "claude-3-5-sonnet-latest",
            "content": [{"type": "text", "text": "hello from anthropic"}],
            "usage": {"input_tokens": 7, "output_tokens": 5},
        }

    provider._post = fake_post  # type: ignore[method-assign]
    result = asyncio.run(
        provider.chat(
            model="claude-3-5-sonnet-latest",
            messages=[
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "hello"},
            ],
            max_tokens=32,
        )
    )
    assert result["object"] == "chat.completion"
    assert result["choices"][0]["message"]["content"] == "hello from anthropic"
    assert result["usage"]["total_tokens"] == 12


def test_anthropic_embeddings_not_supported() -> None:
    provider = AnthropicProvider(api_key="secret")
    with pytest.raises(ProviderError, match="does not expose embeddings"):
        asyncio.run(provider.embeddings(model="claude", inputs=["hello"]))


def test_anthropic_chat_stream_not_supported() -> None:
    provider = AnthropicProvider(api_key="secret")
    with pytest.raises(ProviderError, match="streaming is not enabled"):
        asyncio.run(_collect(provider.chat_stream(model="claude", messages=[], max_tokens=16)))


async def _collect(stream):
    return [chunk async for chunk in stream]
