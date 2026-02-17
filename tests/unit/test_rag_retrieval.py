from dataclasses import dataclass

import pytest

from app.rag.registry import ConnectorRegistry
from app.rag.retrieval import (
    ConnectorNotFoundError,
    RetrievalDeniedError,
    RetrievalOrchestrator,
    RetrievalRequest,
)
from app.rag.types import Document, DocumentChunk


@dataclass
class StubConnector:
    def search(self, query: str, filters: dict[str, str], k: int) -> list[DocumentChunk]:
        return [
            DocumentChunk(
                source_id="doc-a",
                connector="filesystem",
                uri="file:///docs/a.txt",
                chunk_id="doc-a:0",
                text=f"Result for {query}",
                score=0.8,
                metadata=filters,
            )
        ][:k]

    def fetch(self, doc_id: str) -> Document | None:
        return Document(source_id=doc_id, uri=f"file:///docs/{doc_id}.txt", text="x")


def test_retrieve_success() -> None:
    registry = ConnectorRegistry()
    registry.register("filesystem", StubConnector())
    orchestrator = RetrievalOrchestrator(registry=registry)

    chunks = orchestrator.retrieve(
        request=RetrievalRequest(query="hello", connector="filesystem", k=1, filters={}),
        allowed_connectors={"filesystem"},
    )

    assert len(chunks) == 1
    assert chunks[0].source_id == "doc-a"


def test_retrieve_denied_by_policy() -> None:
    registry = ConnectorRegistry()
    registry.register("filesystem", StubConnector())
    orchestrator = RetrievalOrchestrator(registry=registry)

    with pytest.raises(RetrievalDeniedError):
        orchestrator.retrieve(
            request=RetrievalRequest(query="hello", connector="filesystem", k=1, filters={}),
            allowed_connectors={"postgres"},
        )


def test_retrieve_missing_connector() -> None:
    orchestrator = RetrievalOrchestrator(registry=ConnectorRegistry())

    with pytest.raises(ConnectorNotFoundError):
        orchestrator.retrieve(
            request=RetrievalRequest(query="hello", connector="filesystem", k=1, filters={}),
            allowed_connectors=None,
        )
