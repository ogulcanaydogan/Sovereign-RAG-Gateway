# SharePoint Connector (Read-Only)

This connector enables policy-scoped retrieval from SharePoint documents via Microsoft Graph.

## Scope
- Read-only retrieval for RAG (`search` and `fetch`).
- Compatible with connector authorization controls via `connector_constraints.allowed_connectors`.
- No write/update/delete operations.

## Required Environment Variables

```bash
SRG_RAG_SHAREPOINT_SITE_ID="<site-id>"
SRG_RAG_SHAREPOINT_BEARER_TOKEN="<graph-api-token>"
```

## Optional Environment Variables

```bash
SRG_RAG_SHAREPOINT_BASE_URL="https://graph.microsoft.com/v1.0"
SRG_RAG_SHAREPOINT_DRIVE_ID="<drive-id>"
SRG_RAG_SHAREPOINT_ALLOWED_PATH_PREFIXES="/drives/<drive-id>/root:/Ops,/drives/<drive-id>/root:/Security"
SRG_RAG_SHAREPOINT_CACHE_TTL_SECONDS="60"
```

## Enable Connector

```bash
SRG_RAG_ALLOWED_CONNECTORS="filesystem,postgres,s3,confluence,jira,sharepoint"
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
    "messages":[{"role":"user","content":"summarize incident runbook updates"}],
    "rag":{"enabled":true,"connector":"sharepoint","top_k":3,"filters":{"path":"/drives/<drive-id>/root:/Ops"}}
  }'
```

## Notes
- Search ranking is lexical overlap over document names and parent paths.
- `fetch` reads page content from Graph download URLs and returns normalized plain text.
- For least privilege, scope Graph token permissions and constrain retrieval with `SRG_RAG_SHAREPOINT_ALLOWED_PATH_PREFIXES`.
