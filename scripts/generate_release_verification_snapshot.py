#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import struct
import zlib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

Color = tuple[int, int, int]

WHITE: Color = (255, 255, 255)
BLACK: Color = (20, 20, 20)
GREEN: Color = (56, 142, 60)
RED: Color = (198, 40, 40)
AMBER: Color = (245, 124, 0)
LIGHT_GRAY: Color = (230, 230, 230)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate release verification dashboard snapshot assets"
    )
    parser.add_argument("--report-date", default=date.today().isoformat())
    parser.add_argument("--sweep-json", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-png", required=True)
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid JSON object in {path}")
    return payload


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "pass"}
    return False


def _normalize_release_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_releases = payload.get("releases")
    if not isinstance(raw_releases, list):
        raise RuntimeError("sweep JSON missing releases list")

    rows: list[dict[str, Any]] = []
    for item in raw_releases:
        if not isinstance(item, dict):
            continue
        status_value = item.get("status")
        passed = _as_bool(item.get("passed", False))
        if isinstance(status_value, str) and status_value.strip() != "":
            status = status_value.strip().lower()
            passed = status == "pass"
        else:
            status = "pass" if passed else "fail"

        rows.append(
            {
                "tag_name": str(item.get("tag_name", "unknown")),
                "status": status,
                "passed": passed,
                "integrity_verified": _as_bool(item.get("integrity_verified", False)),
                "signature_verified": _as_bool(item.get("signature_verified", False)),
                "legacy_gap_applied": _as_bool(item.get("legacy_gap_applied", False)),
                "errors": item.get("errors", []),
            }
        )
    return rows


def _make_snapshot_payload(
    *,
    report_date: str,
    source_path: Path,
    releases: list[dict[str, Any]],
) -> dict[str, Any]:
    total = len(releases)
    passed = sum(1 for row in releases if bool(row["passed"]))
    failed = total - passed

    return {
        "report_date": report_date,
        "generated_at": datetime.now(UTC).isoformat(),
        "source": str(source_path),
        "totals": {
            "total_releases": total,
            "passed_releases": passed,
            "failed_releases": failed,
            "pass_rate": round((passed / total) if total > 0 else 0.0, 4),
        },
        "releases": releases,
    }


def _new_canvas(width: int, height: int, color: Color = WHITE) -> bytearray:
    r, g, b = color
    pixels = bytearray(width * height * 3)
    for idx in range(0, len(pixels), 3):
        pixels[idx] = r
        pixels[idx + 1] = g
        pixels[idx + 2] = b
    return pixels


def _set_pixel(pixels: bytearray, width: int, height: int, x: int, y: int, color: Color) -> None:
    if x < 0 or y < 0 or x >= width or y >= height:
        return
    idx = (y * width + x) * 3
    pixels[idx] = color[0]
    pixels[idx + 1] = color[1]
    pixels[idx + 2] = color[2]


def _fill_rect(
    pixels: bytearray,
    width: int,
    height: int,
    *,
    x: int,
    y: int,
    rect_w: int,
    rect_h: int,
    color: Color,
) -> None:
    for py in range(y, y + rect_h):
        for px in range(x, x + rect_w):
            _set_pixel(pixels, width, height, px, py, color)


def _draw_release_snapshot_png(payload: dict[str, Any], out_path: Path) -> None:
    releases = payload.get("releases", [])
    release_count = len(releases) if isinstance(releases, list) else 0

    width = max(760, 140 + max(release_count, 1) * 80)
    height = 320
    margin_left = 50
    margin_bottom = 40
    chart_top = 60
    chart_bottom = height - margin_bottom
    max_bar_height = chart_bottom - chart_top - 10

    pixels = _new_canvas(width, height, WHITE)

    # Chart area and axis
    _fill_rect(
        pixels,
        width,
        height,
        x=margin_left,
        y=chart_top,
        rect_w=width - margin_left - 30,
        rect_h=chart_bottom - chart_top,
        color=(249, 249, 249),
    )
    _fill_rect(
        pixels,
        width,
        height,
        x=margin_left,
        y=chart_bottom,
        rect_w=width - margin_left - 30,
        rect_h=2,
        color=BLACK,
    )

    # Legend blocks (green pass, amber partial, red fail)
    _fill_rect(pixels, width, height, x=50, y=20, rect_w=18, rect_h=10, color=GREEN)
    _fill_rect(pixels, width, height, x=74, y=20, rect_w=18, rect_h=10, color=AMBER)
    _fill_rect(pixels, width, height, x=98, y=20, rect_w=18, rect_h=10, color=RED)

    if release_count == 0:
        _fill_rect(
            pixels,
            width,
            height,
            x=margin_left + 20,
            y=chart_bottom - 30,
            rect_w=120,
            rect_h=20,
            color=LIGHT_GRAY,
        )
    else:
        bar_span = max(50, (width - margin_left - 80) // release_count)
        bar_width = max(24, int(bar_span * 0.55))

        for index, row in enumerate(releases):
            if not isinstance(row, dict):
                continue
            status = str(row.get("status", "fail")).lower()
            integrity = _as_bool(row.get("integrity_verified", False))
            signature = _as_bool(row.get("signature_verified", False))

            if status == "pass":
                ratio = 1.0
                color = GREEN
            else:
                checks = int(integrity) + int(signature)
                ratio = 0.35 + (checks * 0.2)
                color = AMBER if checks > 0 else RED

            bar_height = max(14, int(max_bar_height * min(ratio, 1.0)))
            x0 = margin_left + 12 + index * bar_span
            y0 = chart_bottom - bar_height
            _fill_rect(
                pixels,
                width,
                height,
                x=x0,
                y=y0,
                rect_w=bar_width,
                rect_h=bar_height,
                color=color,
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(_encode_png(width, height, pixels))


def _encode_png(width: int, height: int, rgb: bytearray) -> bytes:
    if len(rgb) != width * height * 3:
        raise RuntimeError("invalid RGB buffer length")

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + chunk_type
            + data
            + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    scanlines = bytearray()
    stride = width * 3
    for row in range(height):
        scanlines.append(0)  # no filter
        start = row * stride
        scanlines.extend(rgb[start : start + stride])

    compressed = zlib.compress(bytes(scanlines), level=9)
    return signature + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", compressed) + _chunk(b"IEND", b"")


def main() -> None:
    args = _parse_args()
    sweep_path = Path(args.sweep_json)
    out_json = Path(args.out_json)
    out_png = Path(args.out_png)

    sweep_payload = _load_json(sweep_path)
    releases = _normalize_release_rows(sweep_payload)
    snapshot_payload = _make_snapshot_payload(
        report_date=args.report_date,
        source_path=sweep_path,
        releases=releases,
    )

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(snapshot_payload, indent=2) + "\n", encoding="utf-8")
    _draw_release_snapshot_png(snapshot_payload, out_png)

    print(f"snapshot json: {out_json}")
    print(f"snapshot png: {out_png}")


if __name__ == "__main__":
    main()
