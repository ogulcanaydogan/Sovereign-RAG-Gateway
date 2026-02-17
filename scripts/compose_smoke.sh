#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

docker compose up -d --build
trap 'docker compose down -v' EXIT

for _ in {1..40}; do
  if curl -sf "http://127.0.0.1:8000/healthz" >/dev/null; then
    break
  fi
  sleep 1
done

curl -sf "http://127.0.0.1:8000/readyz" | jq .

curl -sf "http://127.0.0.1:8000/v1/chat/completions" \
  -H "Authorization: Bearer dev-key" \
  -H "x-srg-tenant-id: tenant-a" \
  -H "x-srg-user-id: user-1" \
  -H "x-srg-classification: phi" \
  -H "content-type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello DOB 01/01/1990"}]}' | jq .

curl -sf "http://127.0.0.1:8000/v1/embeddings" \
  -H "Authorization: Bearer dev-key" \
  -H "x-srg-tenant-id: tenant-a" \
  -H "x-srg-user-id: user-1" \
  -H "x-srg-classification: phi" \
  -H "content-type: application/json" \
  -d '{"model":"text-embedding-3-small","input":["hello","world"]}' | jq .
