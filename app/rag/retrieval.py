from dataclasses import dataclass

from app.rag.registry import ConnectorRegistry
from app.rag.types import DocumentChunk


class ConnectorNotFoundError(Exception):
    """Raised when requested connector is not registered."""


class RetrievalDeniedError(Exception):
    """Raised when connector use is denied by policy constraints."""


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    connector: str
    k: int
    filters: dict[str, str]


class RetrievalOrchestrator:
    def __init__(self, registry: ConnectorRegistry, default_k: int = 3):
        self._registry = registry
        self._default_k = default_k

    def retrieve(
        self,
        request: RetrievalRequest,
        allowed_connectors: set[str] | None,
    ) -> list[DocumentChunk]:
        if allowed_connectors is not None and request.connector not in allowed_connectors:
            raise RetrievalDeniedError(f"connector '{request.connector}' is not allowed")

        try:
            connector = self._registry.get(request.connector)
        except KeyError as exc:
            raise ConnectorNotFoundError(request.connector) from exc

        top_k = request.k if request.k > 0 else self._default_k
        return connector.search(query=request.query, filters=request.filters, k=top_k)
