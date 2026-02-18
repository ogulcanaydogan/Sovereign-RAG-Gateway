# Incident Replay Runbook

## Purpose
Reconstruct a single request execution path into a portable evidence bundle.

## Inputs
- `request_id`
- audit log path (default: `artifacts/audit/events.jsonl`)

## Generate Evidence Bundle

```bash
python scripts/audit_replay_bundle.py \
  --request-id <request_id> \
  --audit-log artifacts/audit/events.jsonl \
  --out-dir artifacts/evidence \
  --include-chain-verify
```

Outputs:
- `bundle.json`
- `bundle.sha256`
- `bundle.md`

## Generate Signed Evidence Bundle

```bash
openssl genrsa -out artifacts/evidence-private.pem 2048
openssl rsa -in artifacts/evidence-private.pem -pubout -out artifacts/evidence-public.pem

python scripts/audit_replay_bundle.py \
  --request-id <request_id> \
  --audit-log artifacts/audit/events.jsonl \
  --out-dir artifacts/evidence \
  --include-chain-verify \
  --sign-private-key artifacts/evidence-private.pem \
  --verify-public-key artifacts/evidence-public.pem
```

Additional output:
- `bundle.sig`

Expected terminal output includes `signature_verified: True`.

## Interpretation
- `integrity.chain_verified=true`: hash chain is intact for selected scope.
- `policy.*`: decision identity and mode at runtime.
- `redaction.*`: before/after payload fingerprints and redaction count.
- `provider.*`: provider route, fallback chain, and egress hashes.
- `retrieval.citations[]`: source traceability for RAG paths.

## Operational Notes
- Preserve the public key used for verification with the evidence package.
- Never publish private signing keys.
