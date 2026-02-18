from __future__ import annotations

import re
from hashlib import sha256
from math import sqrt
from typing import Protocol

import httpx


class EmbeddingGenerator(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, preserving order."""


class HashEmbeddingGenerator:
    def __init__(self, embedding_dim: int):
        if embedding_dim < 1:
            raise ValueError("embedding_dim must be >= 1")
        self._embedding_dim = embedding_dim

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._text_to_vector(text) for text in texts]

    def _text_to_vector(self, text: str) -> list[float]:
        vector = [0.0] * self._embedding_dim
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        if not tokens:
            return vector

        for token in tokens:
            digest = sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:2], byteorder="big") % self._embedding_dim
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            vector[idx] += sign

        norm = sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [round(value / norm, 6) for value in vector]


class HTTPOpenAIEmbeddingGenerator:
    def __init__(
        self,
        endpoint: str,
        model: str,
        embedding_dim: int,
        api_key: str | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
        classification: str | None = None,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ):
        if embedding_dim < 1:
            raise ValueError("embedding_dim must be >= 1")
        self._endpoint = endpoint
        self._model = model
        self._embedding_dim = embedding_dim
        self._api_key = api_key
        self._tenant_id = tenant_id
        self._user_id = user_id
        self._classification = classification
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if self._tenant_id:
            headers["x-srg-tenant-id"] = self._tenant_id
        if self._user_id:
            headers["x-srg-user-id"] = self._user_id
        if self._classification:
            headers["x-srg-classification"] = self._classification

        payload = {"model": self._model, "input": texts}
        if self._transport is None:
            client = httpx.Client(timeout=self._timeout_seconds)
        else:
            client = httpx.Client(timeout=self._timeout_seconds, transport=self._transport)

        with client:
            response = client.post(self._endpoint, headers=headers, json=payload)

        if response.status_code != 200:
            raise RuntimeError(
                f"embeddings request failed ({response.status_code}): {response.text[:200]}"
            )

        body = response.json()
        data = body.get("data")
        if not isinstance(data, list):
            raise RuntimeError("embeddings response missing data array")

        vectors_by_index: dict[int, list[float]] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            embedding = item.get("embedding")
            if not isinstance(index, int) or not isinstance(embedding, list):
                continue
            parsed_vector = [float(value) for value in embedding]
            if len(parsed_vector) != self._embedding_dim:
                raise RuntimeError(
                    f"unexpected embedding dimension: expected {self._embedding_dim}, "
                    f"got {len(parsed_vector)}"
                )
            vectors_by_index[index] = parsed_vector

        ordered = [vectors_by_index.get(idx) for idx in range(len(texts))]
        if any(vector is None for vector in ordered):
            raise RuntimeError("embeddings response missing one or more indexes")
        return [vector for vector in ordered if vector is not None]


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in values) + "]"
