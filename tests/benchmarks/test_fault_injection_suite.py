import json
from pathlib import Path

from scripts.run_fault_injection_suite import main


def test_fault_injection_suite_writes_summary(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        '{"request_id":"req-1","tenant_id":"tenant-a","classification":"phi","is_rag":false,"input":"Synthetic"}\n',
        encoding="utf-8",
    )
    out_dir = tmp_path / "faults"

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_fault_injection_suite.py",
            "--dataset",
            str(dataset),
            "--out-dir",
            str(out_dir),
        ],
    )

    main()

    summary_path = out_dir / "fault-summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["totals"]["scenarios_total"] == 3
    assert summary["totals"]["failed_scenarios"] == 0
    assert len(summary["scenarios"]) == 3
