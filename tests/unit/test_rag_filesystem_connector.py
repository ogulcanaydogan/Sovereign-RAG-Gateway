import json
from pathlib import Path

from app.rag.connectors.filesystem import FilesystemConnector


def write_index(path: Path) -> None:
    rows = [
        {
            "source_id": "doc-a",
            "uri": "file:///docs/a.txt",
            "chunk_id": "doc-a:0",
            "text": "Patient has chest pain and shortness of breath",
            "metadata": {"department": "cardiology"},
        },
        {
            "source_id": "doc-b",
            "uri": "file:///docs/b.txt",
            "chunk_id": "doc-b:0",
            "text": "Discharge instructions include hydration and rest",
            "metadata": {"department": "general"},
        },
    ]
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_search_returns_ranked_chunks(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    write_index(index_path)

    connector = FilesystemConnector(index_path=index_path)
    chunks = connector.search(query="chest pain", filters={}, k=2)

    assert len(chunks) == 2
    assert chunks[0].source_id == "doc-a"
    assert chunks[0].score >= chunks[1].score


def test_search_honors_filters(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    write_index(index_path)

    connector = FilesystemConnector(index_path=index_path)
    chunks = connector.search(query="instructions", filters={"department": "cardiology"}, k=3)

    assert len(chunks) == 1
    assert chunks[0].source_id == "doc-a"


def test_fetch_returns_document(tmp_path: Path) -> None:
    index_path = tmp_path / "index.jsonl"
    write_index(index_path)

    connector = FilesystemConnector(index_path=index_path)
    document = connector.fetch("doc-a")

    assert document is not None
    assert document.source_id == "doc-a"
    assert "chest pain" in document.text
