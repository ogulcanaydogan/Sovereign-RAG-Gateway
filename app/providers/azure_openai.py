"""Azure OpenAI adapter."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.providers.base import ProviderError


class AzureOpenAIProvider:
    """Provider that calls Azure OpenAI deployment-scoped endpoints."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        api_version: str = "2024-10-21",
        timeout_s: float = 30.0,
    ):
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._api_version = api_version
        self._timeout = timeout_s

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int | None,
    ) -> dict[str, object]:
        body: dict[str, object] = {"messages": messages}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        result = await self._post(deployment=model, operation="chat/completions", body=body)
        result.setdefault("model", model)
        return result

    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int | None,
    ) -> AsyncIterator[dict[str, object]]:
        body: dict[str, object] = {
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        return self._stream_post(deployment=model, operation="chat/completions", body=body)

    async def embeddings(self, model: str, inputs: list[str]) -> dict[str, object]:
        body: dict[str, object] = {"input": inputs}
        result = await self._post(deployment=model, operation="embeddings", body=body)
        result.setdefault("model", model)
        return result

    async def _stream_post(
        self,
        deployment: str,
        operation: str,
        body: dict[str, object],
    ) -> AsyncIterator[dict[str, object]]:
        url = f"{self._endpoint}/openai/deployments/{deployment}/{operation}"
        headers = {
            "api-key": self._api_key,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    url,
                    params={"api-version": self._api_version},
                    json=body,
                    headers=headers,
                ) as resp:
                    self._raise_for_status(resp)
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            break
                        try:
                            parsed = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(parsed, dict):
                            parsed.setdefault("model", deployment)
                            yield parsed
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

    async def _post(
        self,
        deployment: str,
        operation: str,
        body: dict[str, object],
    ) -> dict[str, object]:
        url = f"{self._endpoint}/openai/deployments/{deployment}/{operation}"
        headers = {
            "api-key": self._api_key,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url,
                    params={"api-version": self._api_version},
                    json=body,
                    headers=headers,
                )
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

        self._raise_for_status(resp)

        result: dict[str, object] = resp.json()
        return result

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
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
                message=f"Provider returned {resp.status_code}",
            )
