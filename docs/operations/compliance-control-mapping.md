# Compliance Control Mapping (Technical)

This mapping links control objectives to concrete enforcement points and exported evidence fields.

| Control Objective | Enforcement Point | Audit Field(s) | Evidence Command |
|---|---|---|---|
| Access control and request attribution | Auth middleware + required tenant/user headers | `tenant_id`, `user_id`, `request_id` | `python scripts/audit_replay_bundle.py --request-id <id>` |
| Policy-before-egress enforcement | OPA evaluation in request path (fail-closed in enforce mode) | `policy_decision_id`, `policy_hash`, `policy_mode`, `policy_allow`, `deny_reason` | same as above |
| Data minimization before provider call | Redaction engine in-path | `redaction_count`, `request_payload_hash`, `redacted_payload_hash` | same as above |
| Retrieval authorization and source traceability | Connector allow-list checks + retrieval orchestrator | `connector_constraints`, `retrieval_citations[]` | same as above |
| Provider egress accountability | Provider routing + fallback instrumentation | `provider`, `selected_model`, `provider_attempts`, `fallback_chain`, `provider_request_hash`, `provider_response_hash` | same as above |
| Tamper-evident audit trail | Hash-chained audit writer | `prev_hash`, `payload_hash` | `python scripts/audit_replay_bundle.py --request-id <id> --include-chain-verify` |

## Notes
- This is a technical control map; it does not replace legal/compliance interpretation.
- Controls are only as strong as policy test coverage and operational hygiene.
