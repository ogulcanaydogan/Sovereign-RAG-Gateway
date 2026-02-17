import json
from pathlib import Path

from scripts.rag_ingest import chunk_text, ingest_directory


def test_chunk_text_with_overlap() -> None:
    text = "one two three four five six"
    chunks = chunk_text(text, chunk_size_words=3, overlap_words=1)

    assert chunks == ["one two three", "three four five", "five six"]


def test_ingest_directory_emits_jsonl(tmp_path: Path) -> None:
    source_dir = tmp_path / "corpus"
    source_dir.mkdir(parents=True)
    (source_dir / "doc.txt").write_text("alpha beta gamma delta", encoding="utf-8")

    output = tmp_path / "index.jsonl"
    count = ingest_directory(source_dir, output, chunk_size_words=2, overlap_words=0)

    assert count == 2
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["source_id"]
    assert rows[0]["chunk_id"].endswith(":0")
