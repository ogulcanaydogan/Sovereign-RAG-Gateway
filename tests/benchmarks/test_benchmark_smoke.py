import json
from pathlib import Path

from scripts.benchmark_runner import run_benchmark


def test_benchmark_runner_writes_expected_files(tmp_path: Path) -> None:
    run_benchmark(out_dir=tmp_path, scenario="enforce_redact", dataset_version="v1")

    assert (tmp_path / "raw/request_metrics.csv").exists()
    summary = json.loads((tmp_path / "results_summary.json").read_text(encoding="utf-8"))
    assert summary["project"] == "sovereign-rag-gateway"
    assert "metrics" in summary
