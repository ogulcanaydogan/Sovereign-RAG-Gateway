from dataclasses import dataclass
from typing import Any


@dataclass
class TransformAction:
    type: str
    args: dict[str, Any]


@dataclass
class ConnectorConstraints:
    allowed_connectors: list[str] | None = None


@dataclass
class PolicyDecision:
    decision_id: str
    allow: bool
    deny_reason: str | None
    policy_hash: str
    evaluated_at: str
    transforms: list[TransformAction]
    provider_constraints: dict[str, Any] | None = None
    connector_constraints: ConnectorConstraints | None = None
    max_tokens_override: int | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PolicyDecision":
        transforms = [
            TransformAction(type=item["type"], args=item.get("args", {}))
            for item in payload.get("transforms", [])
        ]
        connector_constraints = None
        raw_connector_constraints = payload.get("connector_constraints")
        if isinstance(raw_connector_constraints, dict):
            raw_allowed = raw_connector_constraints.get("allowed_connectors")
            allowed_connectors: list[str] | None
            if isinstance(raw_allowed, list):
                allowed_connectors = [str(item) for item in raw_allowed]
            else:
                allowed_connectors = None
            connector_constraints = ConnectorConstraints(
                allowed_connectors=allowed_connectors
            )

        return cls(
            decision_id=payload["decision_id"],
            allow=payload["allow"],
            deny_reason=payload.get("deny_reason"),
            policy_hash=payload["policy_hash"],
            evaluated_at=payload["evaluated_at"],
            transforms=transforms,
            provider_constraints=payload.get("provider_constraints"),
            connector_constraints=connector_constraints,
            max_tokens_override=payload.get("max_tokens_override"),
        )
