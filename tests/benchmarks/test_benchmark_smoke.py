import json
from pathlib import Path

from scripts.benchmark_runner import load_dataset, run_benchmark


def test_benchmark_runner_writes_expected_files(tmp_path: Path) -> None:
    dataset = [
        {
            "request_id": "req-1",
            "tenant_id": "tenant-a",
            "classification": "phi",
            "is_rag": False,
            "input": "Synthetic note",
        }
    ]
    run_benchmark(
        out_dir=tmp_path,
        scenario="enforce_redact",
        dataset_version="v1",
        dataset_rows=dataset,
    )

    assert (tmp_path / "raw/request_metrics.csv").exists()
    summary = json.loads((tmp_path / "results_summary.json").read_text(encoding="utf-8"))
    assert summary["project"] == "sovereign-rag-gateway"
    assert "metrics" in summary


def test_load_dataset_fallback_when_file_missing(tmp_path: Path) -> None:
    rows = load_dataset(tmp_path / "missing.jsonl")
    assert len(rows) == 1
