from dataclasses import dataclass
from typing import Any


@dataclass
class TransformAction:
    type: str
    args: dict[str, Any]


@dataclass
class PolicyDecision:
    decision_id: str
    allow: bool
    deny_reason: str | None
    policy_hash: str
    evaluated_at: str
    transforms: list[TransformAction]
    provider_constraints: dict[str, Any] | None = None
    max_tokens_override: int | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PolicyDecision":
        transforms = [
            TransformAction(type=item["type"], args=item.get("args", {}))
            for item in payload.get("transforms", [])
        ]
        return cls(
            decision_id=payload["decision_id"],
            allow=payload["allow"],
            deny_reason=payload.get("deny_reason"),
            policy_hash=payload["policy_hash"],
            evaluated_at=payload["evaluated_at"],
            transforms=transforms,
            provider_constraints=payload.get("provider_constraints"),
            max_tokens_override=payload.get("max_tokens_override"),
        )
