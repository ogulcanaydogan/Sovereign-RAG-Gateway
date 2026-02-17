# Sovereign RAG Gateway Killer Demo Stories

## Demo 1: PHI Scrub and Continue
### Setup
- Input prompt contains synthetic patient name, DOB, and MRN.
- Policy requires redaction for `x-srg-classification=phi`.

### What to show
- Raw incoming payload has PHI.
- Policy allows request only with transform + redaction.
- Provider receives redacted payload.
- Audit event contains `policy_hash`, `transforms_applied`, and `redaction_count`.

### Win condition
- Response succeeds with sensitive content masked and complete evidence trail.

## Demo 2: Cross-Tenant Exfiltration Block
### Setup
- User in tenant `A` asks retrieval from connector scoped to tenant `B`.

### What to show
- OPA decision deny with machine-readable reason.
- API returns deterministic `403` schema.
- Audit log and trace capture deny path.

### Win condition
- Unauthorized retrieval never reaches connector/provider.

## Demo 3: Budget Shock Absorber
### Setup
- Tenant monthly spend threshold is nearly exhausted.

### What to show
- Routing decision denies expensive model or overrides to approved lower-cost model.
- Response includes deterministic error or transformed model selection.
- Cost counters update and alert threshold is visible.

### Win condition
- Budget policy is enforceable at runtime without app code changes.

## Demo 4: Grounded Answer Under Source Policy
### Setup
- RAG enabled with mixed authorized and unauthorized sources.

### What to show
- Retrieval excludes unauthorized chunks.
- Response includes `citations[]` from permitted connector/doc IDs only.
- Retrieval latency metric and policy decision span are visible.

### Win condition
- Answer is grounded and policy-scoped, not just text completion.

## Demo 5: 90-Second Forensics Replay
### Setup
- Choose one request that triggered transform + redaction + routing decision.

### What to show
- Query by `request_id` reconstructs full path.
- Correlate logs, spans, and audit row chain.
- Show hash-chain verification for tamper evidence.

### Win condition
- Security/SRE reviewer can answer who/what/why/how from one request record.
