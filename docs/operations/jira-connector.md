# Jira Connector (Read-Only)

This connector enables policy-scoped retrieval from Jira Cloud issues.

## Scope
- Read-only retrieval (`search` and `fetch`) via Jira REST API.
- Works with connector authorization using `connector_constraints.allowed_connectors`.
- No ticket mutation operations.

## Required Environment Variables

```bash
SRG_RAG_JIRA_BASE_URL="https://<tenant>.atlassian.net"
SRG_RAG_JIRA_EMAIL="bot-user@company.com"
SRG_RAG_JIRA_API_TOKEN="<token>"
```

## Optional Environment Variables

```bash
SRG_RAG_JIRA_PROJECT_KEYS="OPS,ENG"
SRG_RAG_JIRA_CACHE_TTL_SECONDS="60"
```

## Enable Connector

```bash
SRG_RAG_ALLOWED_CONNECTORS="filesystem,postgres,s3,confluence,jira"
```

## Example Request

```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer dev-key' \
  -H 'x-srg-tenant-id: tenant-a' \
  -H 'x-srg-user-id: user-1' \
  -H 'x-srg-classification: public' \
  -H 'content-type: application/json' \
  -d '{
    "model":"gpt-4o-mini",
    "messages":[{"role":"user","content":"open incident summary"}],
    "rag":{"enabled":true,"connector":"jira","top_k":3,"filters":{"project":"OPS"}}
  }'
```

## Notes
- Uses Jira search pagination and lexical overlap scoring as baseline ranking.
- For least privilege, scope API token permissions and constrain projects with `SRG_RAG_JIRA_PROJECT_KEYS`.
