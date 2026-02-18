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

## Kubernetes (Helm + kind)
```bash
make helm-lint
make helm-template
make demo-up
```

Manual Helm install:
```bash
helm upgrade --install srg charts/sovereign-rag-gateway \
  --namespace srg-system \
  --create-namespace \
  --set env.apiKeys[0]=dev-key
```

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

```bash
curl -s http://127.0.0.1:8000/v1/models \
  -H 'Authorization: Bearer dev-key' \
  -H 'x-srg-tenant-id: tenant-a' \
  -H 'x-srg-user-id: user-1' \
  -H 'x-srg-classification: public'
```

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer dev-key' \
  -H 'x-srg-tenant-id: tenant-a' \
  -H 'x-srg-user-id: user-1' \
  -H 'x-srg-classification: phi' \
  -H 'content-type: application/json' \
  -d '{
    "model":"gpt-4o-mini",
    "messages":[{"role":"user","content":"give triage policy summary"}],
    "rag":{"enabled":true,"connector":"filesystem","top_k":2}
  }'
```

## RAG Ingestion
```bash
python3 scripts/generate_synthetic_healthcare_corpus.py --output-dir benchmarks/data/synthetic_corpus
python3 scripts/rag_ingest.py --input-dir benchmarks/data/synthetic_corpus --output artifacts/rag/filesystem_index.jsonl
```

```bash
python3 scripts/rag_ingest.py \
  --connector postgres \
  --input-dir benchmarks/data/synthetic_corpus \
  --postgres-dsn postgresql://postgres:postgres@localhost:5432/srg_test \
  --postgres-table rag_chunks
```

```bash
python3 scripts/rag_ingest.py \
  --connector postgres \
  --input-dir benchmarks/data/synthetic_corpus \
  --postgres-dsn postgresql://postgres:postgres@localhost:5432/srg_test \
  --postgres-table rag_chunks \
  --embedding-source http \
  --embedding-endpoint http://127.0.0.1:8000/v1/embeddings \
  --embedding-model text-embedding-3-small \
  --embedding-api-key dev-key \
  --embedding-tenant-id tenant-a \
  --embedding-user-id ingest-bot \
  --embedding-classification phi
```

## Citation Eval Gate
```bash
python3 scripts/eval_citations.py \
  --dataset benchmarks/data/citation_eval.jsonl \
  --output-json artifacts/benchmarks/citation_eval.json \
  --output-markdown docs/benchmarks/reports/citations-latest.md \
  --threshold 0.95
```

## PGVector Ranking Eval Gate
```bash
python3 scripts/eval_pgvector_ranking.py \
  --dataset benchmarks/data/pgvector_ranking_eval.jsonl \
  --postgres-dsn postgresql://postgres:postgres@localhost:5432/srg_test \
  --postgres-table rag_chunks \
  --output-json artifacts/benchmarks/pgvector_ranking_eval.json \
  --output-markdown docs/benchmarks/reports/pgvector-ranking-latest.md \
  --threshold 0.8
```

## Migration Check (v0.2.0-rc1)
```bash
python3 scripts/check_migration_v020rc1.py
```

## Compose Smoke
```bash
./scripts/compose_smoke.sh
```

## Release Automation
- Tag push matching `v*` triggers:
  - container build and push to GHCR
  - keyless cosign signing
  - SPDX SBOM generation
  - provenance attestation
  - GitHub release notes sourced from `CHANGELOG.md`

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
1. Add GitOps manifests (Argo CD) for declarative promotion.
2. Add external secrets integration and rotation runbook.
3. Add baseline Grafana dashboards for request/policy/cost telemetry.
