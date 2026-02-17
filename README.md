# Sovereign RAG Gateway

Policy-first, OpenAI-compatible gateway for regulated AI workloads.

## Quick Start
1. Install `uv` and Python 3.12.
2. Run `make dev`.
3. Test health endpoints:
   - `GET /healthz`
   - `GET /readyz`
4. Run tests and checks:
   - `make lint`
   - `make typecheck`
   - `make test`

## API Example
```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer dev-key' \
  -H 'x-srg-tenant-id: tenant-a' \
  -H 'x-srg-user-id: user-1' \
  -H 'x-srg-classification: phi' \
  -H 'content-type: application/json' \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello DOB 01/01/1990"}]}'
```

```bash
curl -s http://127.0.0.1:8000/v1/embeddings \
  -H 'Authorization: Bearer dev-key' \
  -H 'x-srg-tenant-id: tenant-a' \
  -H 'x-srg-user-id: user-1' \
  -H 'x-srg-classification: phi' \
  -H 'content-type: application/json' \
  -d '{"model":"text-embedding-3-small","input":["hello","world"]}'
```

## Compose Smoke
```bash
./scripts/compose_smoke.sh
```

## Differentiation Artifacts
- `docs/strategy/differentiation-strategy.md`
- `docs/strategy/why-this-exists-security-sre.md`
- `docs/strategy/killer-demo-stories.md`
- `docs/benchmarks/governance-yield-vs-performance-overhead.md`
- `docs/benchmarks/output-schema.md`
- `docs/contracts/v1/policy-decision.schema.json`
- `docs/contracts/v1/audit-event.schema.json`
- `docs/contracts/v1/citations-extension.schema.json`
- `docs/research/landscape-sources.md`

## Positioning Snapshot
- Audience: security leaders, platform teams, SREs in regulated domains.
- Core claim: governance is enforced in-path (not post-hoc), with auditable provenance.
- Wedge: policy + redaction + audit chain + constrained RAG in one deployable control plane.

## Immediate Next Steps
1. Convert demo stories into `examples/` runnable scripts.
2. Expand benchmark harness to run all scenarios in `docs/benchmarks/output-schema.md`.
3. Publish first baseline benchmark report under `docs/benchmarks/reports/`.
