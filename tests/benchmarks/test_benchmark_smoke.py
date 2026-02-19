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
    assert "fault_attribution_accuracy" in summary["metrics"]
    assert "detection_delay_ms_p95" in summary["metrics"]


def test_load_dataset_fallback_when_file_missing(tmp_path: Path) -> None:
    rows = load_dataset(tmp_path / "missing.jsonl")
    assert len(rows) == 1


def test_benchmark_runner_supports_fault_injection_scenario(tmp_path: Path) -> None:
    dataset = [
        {
            "request_id": "req-fault",
            "tenant_id": "tenant-a",
            "classification": "phi",
            "is_rag": True,
            "input": "Synthetic note with connector timeout simulation",
        }
    ]
    run_benchmark(
        out_dir=tmp_path,
        scenario="connector_timeout",
        dataset_version="v1",
        dataset_rows=dataset,
    )
    summary = json.loads((tmp_path / "results_summary.json").read_text(encoding="utf-8"))
    assert summary["metrics"]["fault_type"] == "retrieval_timeout"
    assert summary["metrics"]["errors_total"] == 1
