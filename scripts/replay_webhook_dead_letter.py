#!/usr/bin/env python3
import argparse
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class ReplayFailure:
    event_type: str
    endpoint_url: str
    reason: str
    status_code: int | None = None


@dataclass(frozen=True)
class ReplaySummary:
    total_records: int
    considered_records: int
    attempted: int
    succeeded: int
    failed: int
    dry_run: bool
    failures: list[ReplayFailure]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "considered_records": self.considered_records,
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "dry_run": self.dry_run,
            "failures": [
                {
                    "event_type": item.event_type,
                    "endpoint_url": item.endpoint_url,
                    "reason": item.reason,
                    "status_code": item.status_code,
                }
                for item in self.failures
            ],
        }


def load_dead_letter(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"dead-letter file does not exist: {path}")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file_handle:
        for line_number, raw_line in enumerate(file_handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise ValueError(f"dead-letter row {line_number} is not a JSON object")
            rows.append(parsed)
    return rows


def build_idempotency_key(
    endpoint_url: str,
    body: dict[str, Any],
    original_key: str,
    suffix: str,
) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload = f"{endpoint_url}|{original_key}|{suffix}|{canonical}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def replay_dead_letter(
    records: list[dict[str, Any]],
    *,
    event_types: set[str] | None = None,
    endpoint_override: str | None = None,
    max_events: int = 100,
    dry_run: bool = False,
    timeout_s: float = 5.0,
    idempotency_suffix: str = "replay",
    sender: Callable[[str, str, dict[str, str], float], tuple[int, str]] | None = None,
) -> ReplaySummary:
    normalized_types = {item.strip().lower() for item in (event_types or set()) if item.strip()}
    considered: list[dict[str, Any]] = []
    for record in records:
        record_event = str(record.get("event_type", "")).strip().lower()
        if normalized_types and record_event not in normalized_types:
            continue
        considered.append(record)
        if len(considered) >= max(0, max_events):
            break

    attempted = 0
    succeeded = 0
    failures: list[ReplayFailure] = []

    def default_sender(
        endpoint_url: str,
        body_json: str,
        headers: dict[str, str],
        request_timeout: float,
    ) -> tuple[int, str]:
        try:
            response = httpx.post(
                endpoint_url,
                content=body_json,
                headers=headers,
                timeout=request_timeout,
            )
        except httpx.HTTPError as exc:
            return (0, f"{type(exc).__name__}: {exc}")
        return (int(response.status_code), "")

    post = sender or default_sender

    for record in considered:
        event_type = str(record.get("event_type", "")).strip()
        endpoint_url = endpoint_override or str(record.get("endpoint_url", "")).strip()
        if endpoint_url == "":
            failures.append(
                ReplayFailure(
                    event_type=event_type,
                    endpoint_url="",
                    reason="missing endpoint_url",
                )
            )
            continue

        raw_body = record.get("body")
        if not isinstance(raw_body, dict):
            failures.append(
                ReplayFailure(
                    event_type=event_type,
                    endpoint_url=endpoint_url,
                    reason="body must be a JSON object",
                )
            )
            continue

        original_idempotency = str(record.get("idempotency_key", "")).strip()
        idempotency_key = build_idempotency_key(
            endpoint_url=endpoint_url,
            body=raw_body,
            original_key=original_idempotency,
            suffix=idempotency_suffix,
        )
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SovereignRAGGateway/webhook-replay",
            "X-SRG-Replay": "true",
            "X-SRG-Idempotency-Key": idempotency_key,
        }
        if original_idempotency:
            headers["X-SRG-Original-Idempotency-Key"] = original_idempotency

        body_json = json.dumps(raw_body, separators=(",", ":"), ensure_ascii=True)
        attempted += 1

        if dry_run:
            succeeded += 1
            continue

        status_code, error = post(endpoint_url, body_json, headers, timeout_s)
        if 200 <= status_code < 300:
            succeeded += 1
            continue

        failures.append(
            ReplayFailure(
                event_type=event_type,
                endpoint_url=endpoint_url,
                reason=error or "non-2xx response",
                status_code=status_code if status_code > 0 else None,
            )
        )

    return ReplaySummary(
        total_records=len(records),
        considered_records=len(considered),
        attempted=attempted,
        succeeded=succeeded,
        failed=len(failures),
        dry_run=dry_run,
        failures=failures,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay webhook dead-letter events")
    parser.add_argument(
        "--dead-letter",
        default="artifacts/audit/webhook_dead_letter.jsonl",
        help="Path to dead-letter JSONL",
    )
    parser.add_argument(
        "--event-types",
        default="",
        help="Comma-separated event type filters (default: all)",
    )
    parser.add_argument(
        "--endpoint-override",
        default="",
        help="Override endpoint URL for all replayed events",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=100,
        help="Maximum number of records to replay",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=5.0,
        help="HTTP timeout for replay POST",
    )
    parser.add_argument(
        "--idempotency-suffix",
        default="replay",
        help="Suffix used to derive replay idempotency key",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print replay plan without POSTing")
    parser.add_argument(
        "--report-out",
        default="",
        help="Optional JSON report output path",
    )
    args = parser.parse_args()

    try:
        records = load_dead_letter(Path(args.dead_letter))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(2) from exc

    event_types = {item.strip() for item in args.event_types.split(",") if item.strip()}
    summary = replay_dead_letter(
        records=records,
        event_types=event_types or None,
        endpoint_override=args.endpoint_override.strip() or None,
        max_events=args.max_events,
        dry_run=args.dry_run,
        timeout_s=args.timeout_s,
        idempotency_suffix=args.idempotency_suffix,
    )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dead_letter_path": str(Path(args.dead_letter)),
        "filters": {
            "event_types": sorted(event_types),
            "endpoint_override": args.endpoint_override.strip() or None,
            "max_events": args.max_events,
            "dry_run": args.dry_run,
        },
        "summary": summary.to_dict(),
    }
    if args.report_out.strip():
        report_path = Path(args.report_out)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        "Replay summary: "
        f"considered={summary.considered_records} "
        f"attempted={summary.attempted} "
        f"succeeded={summary.succeeded} "
        f"failed={summary.failed} "
        f"dry_run={summary.dry_run}"
    )
    if summary.failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
