"""Dead-letter storage backends for webhook delivery failures."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol


def _parse_timestamp(raw_value: object) -> datetime | None:
    if not isinstance(raw_value, str):
        return None
    candidate = raw_value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class DeadLetterWriteResult:
    backend: str
    written: int
    pruned: int


class DeadLetterStore(Protocol):
    backend: str
    path: Path

    def write(self, record: dict[str, Any]) -> DeadLetterWriteResult:
        """Persist one dead-letter record and optionally prune old records."""

    def load(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Load dead-letter records in write order."""


@dataclass
class JsonlDeadLetterStore:
    path: Path
    retention_days: int | None = None
    backend: str = "jsonl"

    def write(self, record: dict[str, Any]) -> DeadLetterWriteResult:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(record, ensure_ascii=True))
            file_handle.write("\n")
        pruned = self._prune()
        return DeadLetterWriteResult(backend=self.backend, written=1, pruned=pruned)

    def load(self, limit: int | None = None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as file_handle:
            for raw_line in file_handle:
                line = raw_line.strip()
                if not line:
                    continue
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    rows.append(parsed)
        if limit is None or limit <= 0:
            return rows
        return rows[:limit]

    def _prune(self) -> int:
        if self.retention_days is None or self.retention_days <= 0:
            return 0
        if not self.path.exists():
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        kept_lines: list[str] = []
        removed = 0
        with self.path.open("r", encoding="utf-8") as file_handle:
            for raw_line in file_handle:
                line = raw_line.strip()
                if not line:
                    continue
                keep = True
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    parsed = None
                timestamp = (
                    _parse_timestamp(parsed.get("timestamp"))
                    if isinstance(parsed, dict)
                    else None
                )
                if timestamp is not None and timestamp < cutoff:
                    keep = False
                if keep:
                    kept_lines.append(line)
                else:
                    removed += 1
        if removed > 0:
            with self.path.open("w", encoding="utf-8") as file_handle:
                for line in kept_lines:
                    file_handle.write(line)
                    file_handle.write("\n")
        return removed


@dataclass
class SQLiteDeadLetterStore:
    path: Path
    retention_days: int | None = None
    backend: str = "sqlite"

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS webhook_dead_letter (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    endpoint_url TEXT NOT NULL,
                    status_code INTEGER,
                    error TEXT,
                    attempt_count INTEGER NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    body_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_webhook_dead_letter_timestamp
                ON webhook_dead_letter(timestamp)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_webhook_dead_letter_event_type
                ON webhook_dead_letter(event_type)
                """
            )
            connection.commit()

    def write(self, record: dict[str, Any]) -> DeadLetterWriteResult:
        timestamp = str(record.get("timestamp", datetime.now(UTC).isoformat()))
        event_type = str(record.get("event_type", "unknown"))
        endpoint_url = str(record.get("endpoint_url", ""))
        raw_status_code = record.get("status_code")
        status_code = int(raw_status_code) if isinstance(raw_status_code, int) else None
        error = str(record.get("error")) if record.get("error") is not None else None
        attempt_count = int(record.get("attempt_count", 1))
        idempotency_key = str(record.get("idempotency_key", ""))
        body_json = json.dumps(record.get("body", {}), ensure_ascii=True)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO webhook_dead_letter (
                    timestamp,
                    event_type,
                    endpoint_url,
                    status_code,
                    error,
                    attempt_count,
                    idempotency_key,
                    body_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    event_type,
                    endpoint_url,
                    status_code,
                    error,
                    attempt_count,
                    idempotency_key,
                    body_json,
                ),
            )
            pruned = self._prune(connection)
            connection.commit()

        return DeadLetterWriteResult(backend=self.backend, written=1, pruned=pruned)

    def load(self, limit: int | None = None) -> list[dict[str, Any]]:
        sql = (
            "SELECT timestamp, event_type, endpoint_url, status_code, error, attempt_count, "
            "idempotency_key, body_json FROM webhook_dead_letter ORDER BY id ASC"
        )
        params: list[int] = []
        if limit is not None and limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        with self._connect() as connection:
            cursor = connection.execute(sql, tuple(params))
            rows = cursor.fetchall()
        parsed_rows: list[dict[str, Any]] = []
        for row in rows:
            body = json.loads(row["body_json"]) if row["body_json"] else {}
            parsed_rows.append(
                {
                    "timestamp": row["timestamp"],
                    "event_type": row["event_type"],
                    "endpoint_url": row["endpoint_url"],
                    "status_code": row["status_code"],
                    "error": row["error"],
                    "attempt_count": row["attempt_count"],
                    "idempotency_key": row["idempotency_key"],
                    "body": body,
                }
            )
        return parsed_rows

    def _prune(self, connection: sqlite3.Connection) -> int:
        if self.retention_days is None or self.retention_days <= 0:
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        cursor = connection.execute(
            "DELETE FROM webhook_dead_letter WHERE timestamp < ?",
            (cutoff.isoformat(),),
        )
        return int(cursor.rowcount or 0)


def create_dead_letter_store(
    *,
    backend: str,
    path: Path | None,
    retention_days: int | None,
) -> DeadLetterStore | None:
    if path is None:
        return None
    normalized_backend = backend.strip().lower()
    if normalized_backend == "sqlite":
        return SQLiteDeadLetterStore(path=path, retention_days=retention_days)
    if normalized_backend == "jsonl":
        return JsonlDeadLetterStore(path=path, retention_days=retention_days)
    raise ValueError(f"Unsupported dead-letter backend: {backend}")
