from __future__ import annotations

from pathlib import Path

from app.rag.types import DocumentChunk
from scripts.eval_pgvector_ranking import RankingSample, evaluate, load_samples


class _FakeConnector:
    def __init__(self, responses: dict[str, list[DocumentChunk]]):
        self._responses = responses

    def search(self, query: str, filters: dict[str, str], k: int) -> list[DocumentChunk]:
        _ = filters
        return self._responses.get(query, [])[:k]


def test_load_samples(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        '{"id":"s1","query":"q","expected_file_name":"doc-a.txt","filters":{"extension":"txt"}}\n',
        encoding="utf-8",
    )
    rows = load_samples(dataset)
    assert len(rows) == 1
    assert rows[0].sample_id == "s1"
    assert rows[0].filters == {"extension": "txt"}


def test_evaluate_calculates_recall_and_mrr() -> None:
    samples = [
        RankingSample("s1", "q1", "doc-a.txt", {}),
        RankingSample("s2", "q2", "doc-z.txt", {}),
    ]
    connector = _FakeConnector(
        {
            "q1": [
                DocumentChunk(
                    source_id="1",
                    connector="postgres",
                    uri="u",
                    chunk_id="c1",
                    text="a",
                    score=0.9,
                    metadata={"file_name": "doc-a.txt"},
                )
            ],
            "q2": [
                DocumentChunk(
                    source_id="2",
                    connector="postgres",
                    uri="u",
                    chunk_id="c2",
                    text="b",
                    score=0.8,
                    metadata={"file_name": "doc-x.txt"},
                )
            ],
        }
    )

    summary = evaluate(connector=connector, samples=samples, top_k=2)
    assert summary["samples_total"] == 2
    assert summary["recall_at_k"] == 0.5
    assert summary["mrr"] == 0.5
