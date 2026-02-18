import asyncio

from app.providers.azure_openai import AzureOpenAIProvider


def test_azure_openai_chat_normalizes_model() -> None:
    provider = AzureOpenAIProvider(
        endpoint="https://example.openai.azure.com",
        api_key="secret",
    )

    async def fake_post(
        deployment: str,
        operation: str,
        body: dict[str, object],
    ) -> dict[str, object]:
        assert deployment == "chat-deploy"
        assert operation == "chat/completions"
        assert body["max_tokens"] == 64
        return {
            "id": "abc",
            "object": "chat.completion",
            "created": 1,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    provider._post = fake_post  # type: ignore[method-assign]
    result = asyncio.run(
        provider.chat(
            model="chat-deploy",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=64,
        )
    )
    assert result["model"] == "chat-deploy"


def test_azure_openai_embeddings_normalizes_model() -> None:
    provider = AzureOpenAIProvider(
        endpoint="https://example.openai.azure.com",
        api_key="secret",
    )

    async def fake_post(
        deployment: str,
        operation: str,
        body: dict[str, object],
    ) -> dict[str, object]:
        assert deployment == "embed-deploy"
        assert operation == "embeddings"
        assert body["input"] == ["hello"]
        return {
            "object": "list",
            "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
            "usage": {"prompt_tokens": 1, "total_tokens": 1},
        }

    provider._post = fake_post  # type: ignore[method-assign]
    result = asyncio.run(provider.embeddings(model="embed-deploy", inputs=["hello"]))
    assert result["model"] == "embed-deploy"
