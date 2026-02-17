from dataclasses import dataclass, field


@dataclass(frozen=True)
class DocumentChunk:
    source_id: str
    connector: str
    uri: str
    chunk_id: str
    text: str
    score: float
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Document:
    source_id: str
    uri: str
    text: str
    metadata: dict[str, str] = field(default_factory=dict)
