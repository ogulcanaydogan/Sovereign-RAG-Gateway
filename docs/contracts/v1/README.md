# Contracts v1 (Sovereign RAG Gateway)

Versioned public interface contracts for governance and traceability.

## Schemas
- `policy-decision.schema.json`: output contract for policy engine decisions.
- `audit-event.schema.json`: immutable audit event payload contract including policy explainability fields (`policy_decision_id`, `policy_evaluated_at`, `policy_mode`).
- `citations-extension.schema.json`: response extension for RAG citations.

## Compatibility Policy
- Minor, backward-compatible additions are allowed within `v1`.
- Breaking changes require a new version folder (`v2`).
- Every contract change must include fixture updates and compatibility tests.
