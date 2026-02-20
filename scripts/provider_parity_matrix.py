#!/usr/bin/env python3
"""Generate provider compatibility matrix artifacts for CI and docs."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

from app.providers.anthropic import AnthropicProvider
from app.providers.azure_openai import AzureOpenAIProvider
from app.providers.base import ProviderError
from app.providers.http_openai import HTTPOpenAIProvider

ProviderName = Literal["http_openai", "azure_openai", "anthropic"]


@dataclass(frozen=True)
class ProviderParityResult:
    provider: ProviderName
    status: str
    chat_supported: bool
    embeddings_supported: bool
    streaming_supported: bool
    chat_shape_ok: bool
    embeddings_shape_ok: bool
    stream_shape_ok: bool
    notes: list[str]


EXPECTED_CAPABILITIES: dict[ProviderName, dict[str, bool]] = {
    "http_openai": {
        "chat_supported": True,
        "embeddings_supported": True,
        "streaming_supported": True,
    },
    "azure_openai": {
        "chat_supported": True,
        "embeddings_supported": True,
        "streaming_supported": True,
    },
    "anthropic": {
        "chat_supported": True,
        "embeddings_supported": False,
        "streaming_supported": False,
    },
}


async def _collect_stream(stream: Any, limit: int = 3) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    async for item in stream:
        if isinstance(item, dict):
            chunks.append(item)
        if len(chunks) >= limit:
            break
    return chunks


async def _evaluate_http_openai() -> ProviderParityResult:
    provider = HTTPOpenAIProvider(base_url="https://example.test", api_key="secret")
    notes: list[str] = []

    async def fake_post(path: str, body: dict[str, object]) -> dict[str, object]:
        if path == "/v1/chat/completions":
            return {
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 1,
                "model": str(body["model"]),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        return {
            "object": "list",
            "model": str(body["model"]),
            "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
            "usage": {"prompt_tokens": 1, "total_tokens": 1},
        }

    async def fake_stream_post(path: str, body: dict[str, object]) -> Any:
        _ = path, body
        yield {
            "id": "chunk-1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "gpt-4o-mini",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }

    provider._post = fake_post  # type: ignore[method-assign]
    provider._stream_post = fake_stream_post  # type: ignore[method-assign]

    chat_payload = await provider.chat("gpt-4o-mini", [{"role": "user", "content": "ping"}], 32)
    embedding_payload = await provider.embeddings("text-embedding-3-small", ["ping"])
    stream_chunks = await _collect_stream(provider.chat_stream("gpt-4o-mini", [], 16))

    chat_shape_ok = (
        isinstance(chat_payload.get("choices"), list)
        and isinstance(chat_payload.get("usage"), dict)
        and chat_payload.get("object") == "chat.completion"
    )
    embeddings_shape_ok = isinstance(embedding_payload.get("data"), list)
    stream_shape_ok = (
        len(stream_chunks) > 0
        and stream_chunks[0].get("object") == "chat.completion.chunk"
    )

    if not chat_shape_ok:
        notes.append("chat payload did not match expected OpenAI shape")
    if not embeddings_shape_ok:
        notes.append("embeddings payload did not match expected shape")
    if not stream_shape_ok:
        notes.append("stream payload did not include chunk object")

    return ProviderParityResult(
        provider="http_openai",
        status="pass",
        chat_supported=True,
        embeddings_supported=True,
        streaming_supported=True,
        chat_shape_ok=chat_shape_ok,
        embeddings_shape_ok=embeddings_shape_ok,
        stream_shape_ok=stream_shape_ok,
        notes=notes,
    )


async def _evaluate_azure_openai() -> ProviderParityResult:
    provider = AzureOpenAIProvider(endpoint="https://example.openai.azure.com", api_key="secret")
    notes: list[str] = []

    async def fake_post(
        deployment: str,
        operation: str,
        body: dict[str, object],
    ) -> dict[str, object]:
        if operation == "chat/completions":
            return {
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 1,
                "model": deployment,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        return {
            "object": "list",
            "model": deployment,
            "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
            "usage": {"prompt_tokens": 1, "total_tokens": 1},
        }

    async def fake_stream_post(
        deployment: str,
        operation: str,
        body: dict[str, object],
    ) -> Any:
        _ = deployment, operation, body
        yield {
            "id": "chunk-1",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "chat-deploy",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }

    provider._post = fake_post  # type: ignore[method-assign]
    provider._stream_post = fake_stream_post  # type: ignore[method-assign]

    chat_payload = await provider.chat("chat-deploy", [{"role": "user", "content": "ping"}], 32)
    embedding_payload = await provider.embeddings("embed-deploy", ["ping"])
    stream_chunks = await _collect_stream(provider.chat_stream("chat-deploy", [], 16))

    chat_shape_ok = (
        isinstance(chat_payload.get("choices"), list)
        and isinstance(chat_payload.get("usage"), dict)
        and chat_payload.get("model") == "chat-deploy"
    )
    embeddings_shape_ok = isinstance(embedding_payload.get("data"), list)
    stream_shape_ok = (
        len(stream_chunks) > 0
        and stream_chunks[0].get("object") == "chat.completion.chunk"
    )

    if not chat_shape_ok:
        notes.append("chat payload did not match expected Azure-normalized shape")
    if not embeddings_shape_ok:
        notes.append("embeddings payload did not match expected shape")
    if not stream_shape_ok:
        notes.append("stream payload did not include chunk object")

    return ProviderParityResult(
        provider="azure_openai",
        status="pass",
        chat_supported=True,
        embeddings_supported=True,
        streaming_supported=True,
        chat_shape_ok=chat_shape_ok,
        embeddings_shape_ok=embeddings_shape_ok,
        stream_shape_ok=stream_shape_ok,
        notes=notes,
    )


async def _evaluate_anthropic() -> ProviderParityResult:
    provider = AnthropicProvider(api_key="secret")
    notes: list[str] = []

    async def fake_post(path: str, body: dict[str, object]) -> dict[str, object]:
        _ = path, body
        return {
            "id": "msg_123",
            "model": "claude-3-5-sonnet-latest",
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 3, "output_tokens": 2},
        }

    provider._post = fake_post  # type: ignore[method-assign]

    chat_payload = await provider.chat(
        "claude-3-5-sonnet-latest",
        [{"role": "user", "content": "ping"}],
        32,
    )
    chat_shape_ok = (
        chat_payload.get("object") == "chat.completion"
        and isinstance(chat_payload.get("choices"), list)
        and isinstance(chat_payload.get("usage"), dict)
    )

    embeddings_supported = True
    try:
        await provider.embeddings("claude-3-5-sonnet-latest", ["ping"])
    except ProviderError as exc:
        embeddings_supported = False
        if exc.code != "provider_embeddings_unsupported":
            notes.append(f"unexpected embeddings error code: {exc.code}")

    streaming_supported = True
    try:
        await _collect_stream(provider.chat_stream("claude-3-5-sonnet-latest", [], 16))
    except ProviderError as exc:
        streaming_supported = False
        if exc.code != "provider_streaming_unsupported":
            notes.append(f"unexpected streaming error code: {exc.code}")

    return ProviderParityResult(
        provider="anthropic",
        status="pass",
        chat_supported=True,
        embeddings_supported=embeddings_supported,
        streaming_supported=streaming_supported,
        chat_shape_ok=chat_shape_ok,
        embeddings_shape_ok=not embeddings_supported,
        stream_shape_ok=not streaming_supported,
        notes=notes,
    )


async def evaluate_provider(provider: ProviderName) -> ProviderParityResult:
    if provider == "http_openai":
        return await _evaluate_http_openai()
    if provider == "azure_openai":
        return await _evaluate_azure_openai()
    return await _evaluate_anthropic()


def _with_expectation_status(result: ProviderParityResult) -> ProviderParityResult:
    expected = EXPECTED_CAPABILITIES[result.provider]
    notes = list(result.notes)
    status = "pass"

    for field_name, expected_value in expected.items():
        actual = getattr(result, field_name)
        if actual != expected_value:
            status = "fail"
            notes.append(
                f"expected {field_name}={expected_value}, got {actual}"
            )

    if result.chat_supported and not result.chat_shape_ok:
        status = "fail"
    if result.embeddings_supported and not result.embeddings_shape_ok:
        status = "fail"
    if result.streaming_supported and not result.stream_shape_ok:
        status = "fail"

    return ProviderParityResult(
        provider=result.provider,
        status=status,
        chat_supported=result.chat_supported,
        embeddings_supported=result.embeddings_supported,
        streaming_supported=result.streaming_supported,
        chat_shape_ok=result.chat_shape_ok,
        embeddings_shape_ok=result.embeddings_shape_ok,
        stream_shape_ok=result.stream_shape_ok,
        notes=notes,
    )


def render_markdown(results: list[ProviderParityResult]) -> str:
    lines = [
        "# Provider Parity Matrix",
        "",
        (
            "| Provider | Status | Chat | Embeddings | Streaming | "
            "Chat shape | Embeddings shape | Stream shape |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in results:
        lines.append(
            "| "
            f"{item.provider} | {item.status} | "
            f"{_flag(item.chat_supported)} | "
            f"{_flag(item.embeddings_supported)} | "
            f"{_flag(item.streaming_supported)} | "
            f"{_flag(item.chat_shape_ok)} | "
            f"{_flag(item.embeddings_shape_ok)} | "
            f"{_flag(item.stream_shape_ok)} |"
        )
    lines.append("")
    for item in results:
        if item.notes:
            lines.append(f"## Notes: {item.provider}")
            for note in item.notes:
                lines.append(f"- {note}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _flag(value: bool) -> str:
    return "yes" if value else "no"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate provider parity matrix artifacts")
    parser.add_argument(
        "--provider",
        choices=["all", "http_openai", "azure_openai", "anthropic"],
        default="all",
        help="Evaluate one provider or all providers",
    )
    parser.add_argument(
        "--out-json",
        default="",
        help="Optional path for JSON output",
    )
    parser.add_argument(
        "--out-markdown",
        default="",
        help="Optional path for Markdown output",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any provider parity check fails",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    providers: list[ProviderName]
    if args.provider == "all":
        providers = ["http_openai", "azure_openai", "anthropic"]
    else:
        providers = [cast(ProviderName, args.provider)]

    raw_results = [asyncio.run(evaluate_provider(provider)) for provider in providers]
    results = [_with_expectation_status(item) for item in raw_results]
    markdown = render_markdown(results)

    if args.out_json:
        json_path = Path(args.out_json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps([asdict(item) for item in results], indent=2),
            encoding="utf-8",
        )
    if args.out_markdown:
        markdown_path = Path(args.out_markdown)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown, encoding="utf-8")

    print(markdown)
    failed = [item for item in results if item.status != "pass"]
    if args.strict and failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
