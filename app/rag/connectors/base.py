from typing import Protocol

from app.rag.types import Document, DocumentChunk


class Connector(Protocol):
    def search(self, query: str, filters: dict[str, str], k: int) -> list[DocumentChunk]:
        """Search ranked chunks for a query."""

    def fetch(self, doc_id: str) -> Document | None:
        """Fetch full document by source id."""
