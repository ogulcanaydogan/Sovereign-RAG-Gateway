import asyncio

import httpx
import pytest

from app.providers.base import ProviderError
from app.providers.http_openai import HTTPOpenAIProvider


def test_chat_stream_delegates_to_stream_post() -> None:
    provider = HTTPOpenAIProvider(base_url="https://example.com", api_key="secret")

    async def fake_stream_post(path: str, body: dict[str, object]):
        assert path == "/v1/chat/completions"
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}
        yield {
            "id": "chunk-1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "gpt-4o-mini",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }

    provider._stream_post = fake_stream_post  # type: ignore[method-assign]
    chunks = asyncio.run(_collect(provider.chat_stream("gpt-4o-mini", [], 64)))
    assert chunks[0]["object"] == "chat.completion.chunk"


def test_raise_for_status_rate_limit() -> None:
    with pytest.raises(ProviderError, match="rate limit"):
        HTTPOpenAIProvider._raise_for_status(httpx.Response(status_code=429))


def test_raise_for_status_generic_error() -> None:
    with pytest.raises(ProviderError, match="Provider returned 400"):
        HTTPOpenAIProvider._raise_for_status(httpx.Response(status_code=400))


async def _collect(stream):
    return [chunk async for chunk in stream]
