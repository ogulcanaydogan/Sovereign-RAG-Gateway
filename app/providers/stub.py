from collections.abc import AsyncIterator
from time import time
from uuid import uuid4

from app.providers.base import ProviderError
from app.rag.embeddings import HashEmbeddingGenerator


class StubProvider:
    def __init__(self, embedding_dim: int = 16):
        self._embedding_generator = HashEmbeddingGenerator(embedding_dim=embedding_dim)

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int | None,
    ) -> dict[str, object]:
        self._maybe_raise_provider_error(model)
        last_user_message = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        answer = f"Stub response: {last_user_message[:120]}"
        prompt_tokens = max(sum(len(m["content"].split()) for m in messages), 1)
        completion_tokens = max(len(answer.split()), 1)
        return {
            "id": f"chatcmpl-{uuid4().hex}",
            "object": "chat.completion",
            "created": int(time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": answer,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "max_tokens_applied": max_tokens,
        }

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int | None,
    ) -> AsyncIterator[dict[str, object]]:
        response = await self.chat(model=model, messages=messages, max_tokens=max_tokens)
        content = ""
        choices_raw = response.get("choices")
        if isinstance(choices_raw, list) and choices_raw:
            first_choice = choices_raw[0]
            if isinstance(first_choice, dict):
                message_raw = first_choice.get("message")
                if isinstance(message_raw, dict):
                    content_raw = message_raw.get("content")
                    if isinstance(content_raw, str):
                        content = content_raw

        created_raw = response.get("created")
        created = (
            int(created_raw)
            if isinstance(created_raw, int | float | str)
            else int(time())
        )
        response_id = str(response.get("id", f"chatcmpl-{uuid4().hex}"))
        chunk_size = 32

        pieces = [content[idx : idx + chunk_size] for idx in range(0, len(content), chunk_size)]
        if not pieces:
            pieces = [""]

        first = pieces[0]
        yield {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": first},
                    "finish_reason": None,
                }
            ],
        }

        for piece in pieces[1:]:
            yield {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": piece},
                        "finish_reason": None,
                    }
                ],
            }

        yield {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
            "usage": response.get("usage", {}),
        }

    async def embeddings(self, model: str, inputs: list[str]) -> dict[str, object]:
        self._maybe_raise_provider_error(model)
        data: list[dict[str, object]] = []
        prompt_tokens = 0
        for index, text in enumerate(inputs):
            vector = self._embedding_generator.embed_texts([text])[0]
            prompt_tokens += max(len(text.split()), 1)
            data.append(
                {
                    "object": "embedding",
                    "index": index,
                    "embedding": vector,
                }
            )

        return {
            "object": "list",
            "data": data,
            "model": model,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "total_tokens": prompt_tokens,
            },
        }

    @staticmethod
    def _maybe_raise_provider_error(model: str) -> None:
        if model.startswith("error-429"):
            raise ProviderError(
                status_code=429,
                code="provider_rate_limited",
                message="Provider rate limit exceeded",
                error_type="rate_limit",
            )
        if model.startswith("error-502"):
            raise ProviderError(
                status_code=502,
                code="provider_bad_gateway",
                message="Provider upstream bad gateway",
            )
