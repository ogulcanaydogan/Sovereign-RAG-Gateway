from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast
from uuid import uuid4

import httpx
from jsonschema import ValidationError, validate

from app.config.settings import Settings
from app.policy.models import PolicyDecision


class PolicyTimeoutError(Exception):
    """Raised when policy evaluation times out."""


class PolicyValidationError(Exception):
    """Raised when policy decision payload does not match schema."""


class OPAClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._schema_path = settings.contracts_dir / "policy-decision.schema.json"
        self._schema = self._schema_path.read_text(encoding="utf-8")
        self._schema_json = self._schema_as_json()

    def evaluate(self, payload: dict[str, Any]) -> PolicyDecision:
        if self._settings.opa_simulate_timeout:
            raise PolicyTimeoutError("OPA timed out")

        if self._settings.opa_url:
            decision_payload = self._evaluate_remote(payload)
        else:
            decision_payload = self._evaluate_local(payload)

        decision_payload.setdefault("decision_id", str(uuid4()))
        decision_payload.setdefault("policy_hash", sha256(self._schema.encode("utf-8")).hexdigest())
        decision_payload.setdefault("evaluated_at", datetime.now(UTC).isoformat())
        decision_payload.setdefault("transforms", [])

        try:
            validate(instance=decision_payload, schema=self._schema_json)
        except ValidationError as exc:
            raise PolicyValidationError(str(exc)) from exc

        return PolicyDecision.from_dict(decision_payload)

    def _evaluate_remote(self, payload: dict[str, Any]) -> dict[str, Any]:
        opa_url = self._settings.opa_url
        if not opa_url:
            raise PolicyValidationError("OPA URL is not configured")
        try:
            response = httpx.post(
                opa_url,
                json={"input": payload},
                timeout=self._settings.opa_timeout_ms / 1000,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise PolicyTimeoutError("OPA timed out") from exc
        except httpx.HTTPError as exc:
            raise PolicyTimeoutError(f"OPA request failed: {exc}") from exc

        parsed = response.json()
        if not isinstance(parsed, dict):
            raise PolicyValidationError("OPA response must be an object")

        raw_result = parsed.get("result", parsed)
        if not isinstance(raw_result, dict):
            raise PolicyValidationError("OPA result must be an object")

        return cast(dict[str, Any], raw_result)

    def _evaluate_local(self, payload: dict[str, Any]) -> dict[str, Any]:
        requested_model = str(payload.get("requested_model", ""))
        classification = str(payload.get("classification", "public"))
        connector_targets = [
            str(item) for item in cast(list[object], payload.get("connector_targets", []))
        ]
        allowed_connectors = sorted(self._settings.rag_allowed_connector_set)

        allow = not requested_model.startswith("forbidden")
        deny_reason = None if allow else "model_not_allowed"
        if allow and any(item not in allowed_connectors for item in connector_targets):
            allow = False
            deny_reason = "connector_not_allowed"

        transforms: list[dict[str, Any]] = []
        if allow and classification in {"phi", "pii"}:
            transforms.append(
                {
                    "type": "prepend_system_guardrail",
                    "args": {
                        "text": "Do not expose sensitive identifiers. Use masked placeholders.",
                    },
                }
            )
            transforms.append({"type": "set_max_tokens", "args": {"value": 256}})

        decision_payload: dict[str, Any] = {
            "decision_id": str(uuid4()),
            "allow": allow,
            "policy_hash": sha256(self._schema.encode("utf-8")).hexdigest(),
            "evaluated_at": datetime.now(UTC).isoformat(),
            "transforms": transforms,
            "provider_constraints": {
                "allowed_providers": ["stub"],
                "allowed_models": [requested_model],
            },
            "connector_constraints": {
                "allowed_connectors": allowed_connectors,
            },
        }

        if deny_reason is not None:
            decision_payload["deny_reason"] = deny_reason

        if allow:
            decision_payload["max_tokens_override"] = 256

        return decision_payload

    def _schema_as_json(self) -> dict[str, Any]:
        import json

        parsed = json.loads(self._schema)
        return cast(dict[str, Any], parsed)
