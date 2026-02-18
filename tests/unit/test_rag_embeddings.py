from __future__ import annotations

import json

import httpx
import pytest

from app.rag.embeddings import HashEmbeddingGenerator, HTTPOpenAIEmbeddingGenerator


def test_hash_embedding_generator_returns_requested_dim() -> None:
    generator = HashEmbeddingGenerator(embedding_dim=8)
    vectors = generator.embed_texts(["hello", "world"])

    assert len(vectors) == 2
    assert all(len(vector) == 8 for vector in vectors)
    assert vectors[0] != vectors[1]


def test_http_embedding_generator_success() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        assert request.headers["x-srg-tenant-id"] == "tenant-a"
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "text-embedding-3-small"
        return httpx.Response(
            status_code=200,
            json={
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2]},
                    {"index": 1, "embedding": [0.3, 0.4]},
                ]
            },
        )

    generator = HTTPOpenAIEmbeddingGenerator(
        endpoint="https://example.local/v1/embeddings",
        model="text-embedding-3-small",
        embedding_dim=2,
        api_key="test-key",
        tenant_id="tenant-a",
        user_id="ingest-bot",
        classification="phi",
        transport=httpx.MockTransport(_handler),
    )

    vectors = generator.embed_texts(["a", "b"])
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


def test_http_embedding_generator_dimension_mismatch() -> None:
    def _handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={"data": [{"index": 0, "embedding": [0.1]}]},
        )

    generator = HTTPOpenAIEmbeddingGenerator(
        endpoint="https://example.local/v1/embeddings",
        model="text-embedding-3-small",
        embedding_dim=2,
        transport=httpx.MockTransport(_handler),
    )

    with pytest.raises(RuntimeError, match="unexpected embedding dimension"):
        generator.embed_texts(["a"])
