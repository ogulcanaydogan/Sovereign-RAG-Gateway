from pathlib import Path

from scripts.update_weekly_reports_index import WeeklyReportRow, build_index


def test_build_index_renders_markdown_table() -> None:
    content = build_index(
        [
            WeeklyReportRow(
                date="2026-02-20",
                filename="weekly-2026-02-20.md",
                run_id="22207623171",
                result="success",
            )
        ]
    )
    assert "| Week | Report | Deploy-smoke Run ID | Result |" in content
    assert "[weekly-2026-02-20.md](weekly-2026-02-20.md)" in content
    assert "`22207623171`" in content


def test_index_links_multiple_rows() -> None:
    rows = [
        WeeklyReportRow(
            date="2026-02-20",
            filename="weekly-2026-02-20.md",
            run_id="1",
            result="success",
        ),
        WeeklyReportRow(
            date="2026-02-19",
            filename="weekly-2026-02-19.md",
            run_id="2",
            result="success",
        ),
    ]
    content = build_index(rows)
    assert "weekly-2026-02-20.md" in content
    assert "weekly-2026-02-19.md" in content


def test_index_file_write_smoke(tmp_path: Path) -> None:
    out = tmp_path / "index.md"
    out.write_text(
        build_index(
            [
                WeeklyReportRow(
                    date="2026-02-20",
                    filename="weekly-2026-02-20.md",
                    run_id="3",
                    result="success",
                )
            ]
        ),
        encoding="utf-8",
    )
    assert out.exists()
    assert "weekly-2026-02-20.md" in out.read_text(encoding="utf-8")
