#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config.settings import clear_settings_cache
from app.main import create_app


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _contract_checks(contracts_dir: Path) -> list[CheckResult]:
    required = [
        "policy-decision.schema.json",
        "audit-event.schema.json",
        "citations-extension.schema.json",
    ]
    results: list[CheckResult] = []
    for name in required:
        path = contracts_dir / name
        results.append(
            CheckResult(
                name=f"contract:{name}",
                passed=path.exists(),
                detail=str(path),
            )
        )
    return results


def _api_checks() -> list[CheckResult]:
    clear_settings_cache()
    client = TestClient(create_app())
    auth_headers = {
        "Authorization": "Bearer dev-key",
        "x-srg-tenant-id": "tenant-a",
        "x-srg-user-id": "migration-bot",
        "x-srg-classification": "public",
    }

    checks: list[CheckResult] = []
    for endpoint in ["/healthz", "/readyz"]:
        response = client.get(endpoint)
        checks.append(
            CheckResult(
                name=f"endpoint:{endpoint}",
                passed=response.status_code == 200,
                detail=f"status={response.status_code}",
            )
        )

    models = client.get("/v1/models", headers=auth_headers)
    checks.append(
        CheckResult(
            name="endpoint:/v1/models(authenticated)",
            passed=models.status_code == 200,
            detail=f"status={models.status_code}",
        )
    )

    unauth = client.get("/v1/models")
    body: dict[str, Any] = {}
    try:
        body = unauth.json()
    except json.JSONDecodeError:
        body = {}
    required_keys_present = {
        "code",
        "message",
        "type",
        "request_id",
    }.issubset(body.get("error", {}).keys())
    checks.append(
        CheckResult(
            name="error-envelope:unauthorized",
            passed=unauth.status_code == 401 and required_keys_present,
            detail=f"status={unauth.status_code}",
        )
    )
    return checks


def run_checks() -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[1]
    contracts_dir = project_root / "docs" / "contracts" / "v1"
    checks = _contract_checks(contracts_dir) + _api_checks()
    passed = all(check.passed for check in checks)
    return {
        "migration": "v0.2.0-rc1",
        "checks_passed": passed,
        "checks": [
            {"name": check.name, "passed": check.passed, "detail": check.detail} for check in checks
        ],
    }


def main() -> None:
    result = run_checks()
    print(json.dumps(result, indent=2))
    if not result["checks_passed"]:
        raise SystemExit("Migration checks failed")


if __name__ == "__main__":
    main()
