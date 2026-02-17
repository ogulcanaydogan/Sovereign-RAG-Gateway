from app.rag.connectors.base import Connector


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, name: str, connector: Connector) -> None:
        self._connectors[name] = connector

    def get(self, name: str) -> Connector:
        if name not in self._connectors:
            raise KeyError(name)
        return self._connectors[name]

    def list_names(self) -> list[str]:
        return sorted(self._connectors.keys())
