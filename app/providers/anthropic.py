"""Anthropic adapter."""

from __future__ import annotations

from time import time
from uuid import uuid4

import httpx

from app.providers.base import ProviderError


class AnthropicProvider:
    """Provider that calls Anthropic Messages API and normalizes to OpenAI shape."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        anthropic_version: str = "2023-06-01",
        timeout_s: float = 30.0,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._anthropic_version = anthropic_version
        self._timeout = timeout_s

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int | None,
    ) -> dict[str, object]:
        system_prompt, anthropic_messages = self._normalize_messages(messages)
        body: dict[str, object] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens if max_tokens is not None else 256,
        }
        if system_prompt:
            body["system"] = system_prompt

        result = await self._post(path="/v1/messages", body=body)
        content_items_raw = result.get("content")
        content_items = content_items_raw if isinstance(content_items_raw, list) else []
        text_blocks = [
            block.get("text", "")
            for block in content_items
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        answer = "".join(text_blocks).strip()
        usage_raw = result.get("usage")
        usage = usage_raw if isinstance(usage_raw, dict) else {}
        prompt_tokens = int(usage.get("input_tokens", 0))
        completion_tokens = int(usage.get("output_tokens", 0))

        return {
            "id": result.get("id", f"chatcmpl-{uuid4().hex}"),
            "object": "chat.completion",
            "created": int(time()),
            "model": str(result.get("model", model)),
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
        }

    async def embeddings(self, model: str, inputs: list[str]) -> dict[str, object]:
        _ = model
        _ = inputs
        raise ProviderError(
            status_code=501,
            code="provider_embeddings_unsupported",
            message="Anthropic provider does not expose embeddings for this gateway",
        )

    def _normalize_messages(
        self, messages: list[dict[str, str]]
    ) -> tuple[str, list[dict[str, str]]]:
        system_parts: list[str] = []
        normalized: list[dict[str, str]] = []

        for message in messages:
            role = str(message.get("role", "user"))
            content = str(message.get("content", "")).strip()
            if not content:
                continue
            if role == "system":
                system_parts.append(content)
                continue
            if role not in {"user", "assistant"}:
                role = "user"
            normalized.append({"role": role, "content": content})

        if not normalized:
            normalized = [{"role": "user", "content": "Continue."}]

        return "\n".join(system_parts).strip(), normalized

    async def _post(self, path: str, body: dict[str, object]) -> dict[str, object]:
        url = f"{self._base_url}{path}"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self._anthropic_version,
            "content-type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                status_code=503,
                code="provider_timeout",
                message=f"Provider request timed out: {exc}",
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderError(
                status_code=502,
                code="provider_connection_error",
                message=f"Cannot connect to provider: {exc}",
            ) from exc

        if resp.status_code == 429:
            raise ProviderError(
                status_code=429,
                code="provider_rate_limited",
                message="Provider rate limit exceeded",
                error_type="rate_limit",
            )
        if resp.status_code in {502, 503}:
            raise ProviderError(
                status_code=resp.status_code,
                code="provider_upstream_error",
                message=f"Provider returned {resp.status_code}",
            )
        if resp.status_code >= 400:
            raise ProviderError(
                status_code=resp.status_code,
                code="provider_error",
                message=f"Provider returned {resp.status_code}: {resp.text[:200]}",
            )

        result: dict[str, object] = resp.json()
        return result
