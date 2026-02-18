"""HTTP provider for OpenAI-compatible endpoints."""

import httpx

from app.providers.base import ProviderError


class HTTPOpenAIProvider:
    """Provider that calls any OpenAI-compatible chat/embeddings endpoint."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_s: float = 30.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_s

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int | None,
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "model": model,
            "messages": messages,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        return await self._post("/v1/chat/completions", body)

    async def embeddings(self, model: str, inputs: list[str]) -> dict[str, object]:
        body: dict[str, object] = {
            "model": model,
            "input": inputs,
        }
        return await self._post("/v1/embeddings", body)

    async def _post(self, path: str, body: dict[str, object]) -> dict[str, object]:
        url = f"{self._base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=body, headers=headers)
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
