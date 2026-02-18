# Confluence Connector (Read-Only)

This connector enables policy-scoped retrieval from Confluence Cloud pages.

## Scope
- Read-only retrieval for RAG (`search` and `fetch`).
- Compatible with existing connector authorization controls via `connector_constraints.allowed_connectors`.
- No write/update/delete operations.

## Required Environment Variables

```bash
SRG_RAG_CONFLUENCE_BASE_URL="https://<tenant>.atlassian.net"
SRG_RAG_CONFLUENCE_EMAIL="bot-user@company.com"
SRG_RAG_CONFLUENCE_API_TOKEN="<token>"
```

## Optional Environment Variables

```bash
SRG_RAG_CONFLUENCE_SPACES="OPS,ENG"
SRG_RAG_CONFLUENCE_CACHE_TTL_SECONDS="60"
```

## Enable Connector

Allow connector in gateway policy/runtime config:

```bash
SRG_RAG_ALLOWED_CONNECTORS="filesystem,postgres,s3,confluence"
```

## Example Request

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer dev-key' \
  -H 'x-srg-tenant-id: tenant-a' \
  -H 'x-srg-user-id: user-1' \
  -H 'x-srg-classification: phi' \
  -H 'content-type: application/json' \
  -d '{
    "model":"gpt-4o-mini",
    "messages":[{"role":"user","content":"incident runbook summary"}],
    "rag":{"enabled":true,"connector":"confluence","top_k":3,"filters":{"space":"OPS"}}
  }'
```

## Notes
- Connector uses Confluence search pagination and merges results before ranking.
- Ranking is lexical overlap based and should be treated as baseline retrieval quality.
- For strict least-privilege, scope API token permissions and restrict spaces with `SRG_RAG_CONFLUENCE_SPACES`.
