#!/usr/bin/env python3
"""Generate an index markdown for weekly benchmark/evidence reports."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

RUN_ID_PATTERN = re.compile(r"Run ID:\s*`([^`]+)`")
RESULT_PATTERN = re.compile(r"Result:\s*`([^`]+)`")


@dataclass(frozen=True)
class WeeklyReportRow:
    date: str
    filename: str
    run_id: str
    result: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update weekly reports index markdown")
    parser.add_argument(
        "--reports-dir",
        default="docs/benchmarks/reports",
        help="Directory containing weekly-YYYY-MM-DD.md reports",
    )
    parser.add_argument(
        "--out",
        default="docs/benchmarks/reports/index.md",
        help="Output index markdown path",
    )
    return parser.parse_args()


def _extract_row(report_path: Path) -> WeeklyReportRow:
    text = report_path.read_text(encoding="utf-8")
    run_match = RUN_ID_PATTERN.search(text)
    result_match = RESULT_PATTERN.search(text)
    date_part = report_path.stem.removeprefix("weekly-")
    return WeeklyReportRow(
        date=date_part,
        filename=report_path.name,
        run_id=run_match.group(1) if run_match else "n/a",
        result=result_match.group(1) if result_match else "n/a",
    )


def build_index(rows: list[WeeklyReportRow]) -> str:
    lines = [
        "# Weekly Reports Index",
        "",
        "Auto-generated index of weekly benchmark/evidence reports.",
        "",
        "| Week | Report | Deploy-smoke Run ID | Result |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.date} | [{row.filename}]({row.filename}) | `{row.run_id}` | `{row.result}` |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = _parse_args()
    reports_dir = Path(args.reports_dir)
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[WeeklyReportRow] = []
    for report_path in sorted(reports_dir.glob("weekly-*.md"), reverse=True):
        rows.append(_extract_row(report_path))

    index_content = build_index(rows)
    output_path.write_text(index_content, encoding="utf-8")
    print(f"updated weekly reports index: {output_path}")


if __name__ == "__main__":
    main()
