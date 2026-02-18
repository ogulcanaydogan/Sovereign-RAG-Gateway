import json
from pathlib import Path

from app.config.settings import clear_settings_cache
from scripts.eval_citations import load_samples, run_eval


def _write_dataset(path: Path) -> None:
    rows = [
        {"id": "s1", "question": "triage guidance", "connector": "filesystem"},
        {"id": "s2", "question": "discharge instructions", "connector": "filesystem"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _write_index(path: Path) -> None:
    rows = [
        {
            "source_id": "doc-1",
            "uri": "file:///tmp/doc-1.txt",
            "chunk_id": "doc-1:0",
            "text": "Triage guidance requires masked identifiers",
            "metadata": {"department": "triage"},
        },
        {
            "source_id": "doc-2",
            "uri": "file:///tmp/doc-2.txt",
            "chunk_id": "doc-2:0",
            "text": "Discharge instructions include hydration and follow-up",
            "metadata": {"department": "general"},
        },
    ]
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_run_eval_reports_citations(monkeypatch, tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.jsonl"
    index_path = tmp_path / "index.jsonl"
    _write_dataset(dataset_path)
    _write_index(index_path)

    monkeypatch.setenv("SRG_API_KEYS", "dev-key")
    monkeypatch.setenv("SRG_RAG_FILESYSTEM_INDEX_PATH", str(index_path))
    monkeypatch.setenv("SRG_RAG_ALLOWED_CONNECTORS", "filesystem")
    monkeypatch.setenv("SRG_OPA_SIMULATE_TIMEOUT", "false")
    clear_settings_cache()

    samples = load_samples(dataset_path)
    summary = run_eval(samples=samples, model="gpt-4o-mini")

    assert summary["samples_total"] == 2
    assert float(summary["citation_presence_rate"]) >= 0.5
    assert len(summary["results"]) == 2
