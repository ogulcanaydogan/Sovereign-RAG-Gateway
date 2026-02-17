import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from jsonschema import ValidationError, validate

from app.config.settings import Settings


class AuditValidationError(Exception):
    """Raised when audit payload is invalid."""


class AuditWriter:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._schema_path = settings.contracts_dir / "audit-event.schema.json"
        self._schema = json.loads(self._schema_path.read_text(encoding="utf-8"))
        self._log_path = settings.audit_log_path

    def write_event(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        payload.setdefault("event_id", str(uuid4()))
        payload.setdefault("created_at", datetime.now(UTC).isoformat())

        prev_hash = self._last_payload_hash()
        payload["prev_hash"] = prev_hash
        payload["payload_hash"] = self._calculate_payload_hash(payload)

        try:
            validate(instance=payload, schema=self._schema)
        except ValidationError as exc:
            raise AuditValidationError(str(exc)) from exc

        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

        return payload

    def _calculate_payload_hash(self, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return sha256(canonical.encode("utf-8")).hexdigest()

    def _last_payload_hash(self) -> str:
        if not self._log_path.exists():
            return ""

        last_line = self._read_last_line(self._log_path)
        if not last_line:
            return ""

        try:
            parsed = json.loads(last_line)
        except json.JSONDecodeError:
            return ""
        return str(parsed.get("payload_hash", ""))

    @staticmethod
    def _read_last_line(file_path: Path) -> str:
        with file_path.open("rb") as file_handle:
            file_handle.seek(0, 2)
            size = file_handle.tell()
            if size == 0:
                return ""

            position = size - 1
            while position > 0:
                file_handle.seek(position)
                if file_handle.read(1) == b"\n":
                    position += 1
                    break
                position -= 1

            file_handle.seek(position)
            return file_handle.read().decode("utf-8").strip()
