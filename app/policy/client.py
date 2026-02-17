from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast
from uuid import uuid4

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

    def evaluate(self, payload: dict[str, Any]) -> PolicyDecision:
        if self._settings.opa_simulate_timeout:
            raise PolicyTimeoutError("OPA timed out")

        requested_model = str(payload.get("requested_model", ""))
        classification = str(payload.get("classification", "public"))

        allow = not requested_model.startswith("forbidden")
        deny_reason = None if allow else "model_not_allowed"

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
        }

        if deny_reason is not None:
            decision_payload["deny_reason"] = deny_reason

        if allow:
            decision_payload["max_tokens_override"] = 256

        try:
            validate(instance=decision_payload, schema=self._schema_as_json())
        except ValidationError as exc:
            raise PolicyValidationError(str(exc)) from exc

        return PolicyDecision.from_dict(decision_payload)

    def _schema_as_json(self) -> dict[str, Any]:
        import json

        parsed = json.loads(self._schema)
        return cast(dict[str, Any], parsed)
