from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_release_verification_snapshot import (
    _draw_release_snapshot_png,
    _make_snapshot_payload,
    _normalize_release_rows,
)


def test_normalize_release_rows_supports_status_and_passed() -> None:
    payload = {
        "releases": [
            {
                "tag_name": "v0.7.0",
                "status": "pass",
                "integrity_verified": True,
                "signature_verified": True,
            },
            {
                "tag_name": "v0.6.0",
                "passed": False,
                "integrity_verified": False,
                "signature_verified": False,
            },
        ]
    }

    rows = _normalize_release_rows(payload)
    assert rows[0]["passed"] is True
    assert rows[1]["status"] == "fail"


def test_make_snapshot_payload_computes_totals(tmp_path: Path) -> None:
    releases = [
        {"tag_name": "v0.7.0", "status": "pass", "passed": True},
        {"tag_name": "v0.6.0", "status": "fail", "passed": False},
    ]
    payload = _make_snapshot_payload(
        report_date="2026-03-03",
        source_path=tmp_path / "sweep.json",
        releases=releases,
    )
    assert payload["totals"]["total_releases"] == 2
    assert payload["totals"]["passed_releases"] == 1
    assert payload["totals"]["failed_releases"] == 1


def test_draw_release_snapshot_png_writes_png(tmp_path: Path) -> None:
    snapshot_payload = {
        "releases": [
            {
                "tag_name": "v0.7.0",
                "status": "pass",
                "integrity_verified": True,
                "signature_verified": True,
            },
            {
                "tag_name": "v0.6.0",
                "status": "fail",
                "integrity_verified": False,
                "signature_verified": False,
            },
        ]
    }

    out_path = tmp_path / "snapshot.png"
    _draw_release_snapshot_png(snapshot_payload, out_path)

    content = out_path.read_bytes()
    assert content.startswith(b"\x89PNG\r\n\x1a\n")


def test_main_flow_assets_can_be_written(tmp_path: Path) -> None:
    sweep_path = tmp_path / "sweep.json"
    sweep_path.write_text(
        json.dumps(
            {
                "releases": [
                    {
                        "tag_name": "v0.7.0",
                        "status": "pass",
                        "integrity_verified": True,
                        "signature_verified": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    rows = _normalize_release_rows(json.loads(sweep_path.read_text(encoding="utf-8")))
    payload = _make_snapshot_payload(
        report_date="2026-03-03",
        source_path=sweep_path,
        releases=rows,
    )
    json_path = tmp_path / "snapshot.json"
    png_path = tmp_path / "snapshot.png"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _draw_release_snapshot_png(payload, png_path)

    assert json.loads(json_path.read_text(encoding="utf-8"))["totals"]["passed_releases"] == 1
    assert png_path.exists()
