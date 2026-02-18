# Secrets Rotation Runbook

This runbook covers secret lifecycle management for the Sovereign RAG Gateway using External Secrets Operator (ESO) with AWS Secrets Manager.

## Architecture

```
AWS Secrets Manager          ESO Controller          Kubernetes Secret          Gateway Pod
┌──────────────┐     sync    ┌──────────┐    create   ┌──────────┐    mount    ┌──────────┐
│ srg/api-keys │───────────>│ External │──────────>│  K8s     │──────────>│  SRG     │
│ srg/provider │  (1h poll)  │ Secret   │  (owner)  │  Secret  │  (envFrom)│  Process │
└──────────────┘             └──────────┘            └──────────┘            └──────────┘
```

ESO polls AWS Secrets Manager at the `refreshInterval` (default: 1 hour). When a secret value changes upstream, ESO updates the corresponding Kubernetes Secret. Pods consuming the secret via `envFrom` require a restart to pick up new values.

## Managed Secrets

| ExternalSecret | Remote Key | Target K8s Secret | Contents |
|---|---|---|---|
| `srg-api-keys` | `srg/api-keys` | `sovereign-rag-gateway-auth` | Comma-separated gateway API keys |
| `srg-provider-credentials` | `srg/provider-config` | `sovereign-rag-gateway-provider-credentials` | Provider config JSON (API keys, base URLs) |

## Rotation Procedures

### Rotate Gateway API Keys

1. **Add the new key to AWS Secrets Manager** (append, do not remove the old key yet):
   ```bash
   aws secretsmanager update-secret \
     --secret-id srg/api-keys \
     --secret-string '{"keys": "new-key-1,old-key-1"}'
   ```

2. **Wait for ESO sync** (up to `refreshInterval`, default 1 hour) or force immediate sync:
   ```bash
   kubectl annotate externalsecret srg-api-keys \
     -n srg-system \
     force-sync=$(date +%s) --overwrite
   ```

3. **Verify the Kubernetes secret was updated:**
   ```bash
   kubectl get secret sovereign-rag-gateway-auth \
     -n srg-system \
     -o jsonpath='{.data.api-keys}' | base64 -d
   ```

4. **Restart gateway pods** to pick up the new secret:
   ```bash
   kubectl rollout restart deployment/sovereign-rag-gateway -n srg-system
   kubectl rollout status deployment/sovereign-rag-gateway -n srg-system
   ```

5. **Verify the new key works:**
   ```bash
   curl -s -o /dev/null -w '%{http_code}' \
     -H 'Authorization: Bearer new-key-1' \
     -H 'x-srg-tenant-id: test' \
     -H 'x-srg-user-id: test' \
     -H 'x-srg-classification: internal' \
     http://sovereign-rag-gateway.srg-system.svc:80/healthz
   ```

6. **Remove the old key from AWS Secrets Manager:**
   ```bash
   aws secretsmanager update-secret \
     --secret-id srg/api-keys \
     --secret-string '{"keys": "new-key-1"}'
   ```

7. **Repeat steps 2-4** to propagate the removal.

### Rotate Provider API Keys

1. **Update the provider config in AWS Secrets Manager:**
   ```bash
   aws secretsmanager update-secret \
     --secret-id srg/provider-config \
     --secret-string '{"config": "[{\"name\":\"openai\",\"base_url\":\"https://api.openai.com/v1\",\"api_key\":\"sk-new-key\",\"priority\":10}]"}'
   ```

2. **Force sync and restart** (same as steps 2-4 above for `srg-provider-credentials`).

3. **Verify provider connectivity** by sending a test request through the gateway.

## Emergency Revocation

If a key is compromised, revoke immediately without waiting for the sync cycle:

1. **Rotate the secret in AWS Secrets Manager** (remove compromised key).

2. **Force immediate sync:**
   ```bash
   kubectl annotate externalsecret srg-api-keys \
     -n srg-system \
     force-sync=$(date +%s) --overwrite
   ```

3. **Force restart all pods immediately:**
   ```bash
   kubectl rollout restart deployment/sovereign-rag-gateway -n srg-system
   ```

4. **Verify the compromised key is rejected:**
   ```bash
   curl -s -o /dev/null -w '%{http_code}' \
     -H 'Authorization: Bearer COMPROMISED_KEY' \
     -H 'x-srg-tenant-id: test' \
     -H 'x-srg-user-id: test' \
     -H 'x-srg-classification: internal' \
     http://sovereign-rag-gateway.srg-system.svc:80/healthz
   # Expected: 401
   ```

## Monitoring Secret Sync

Monitor ESO sync health using these indicators:

**Check ExternalSecret status:**
```bash
kubectl get externalsecret -n srg-system
```

Expected output shows `SecretSynced` condition as `True`:
```
NAME                      STORE                      REFRESH   STATUS
srg-api-keys             srg-aws-secretsmanager      1h        SecretSynced
srg-provider-credentials srg-aws-secretsmanager      1h        SecretSynced
```

**Check for sync failures:**
```bash
kubectl get events -n srg-system --field-selector reason=UpdateFailed
```

**Prometheus alerts** (if ESO metrics are scraped):
```promql
# Alert if any ExternalSecret has not synced in 2x refresh interval
externalsecret_status_condition{condition="SecretSynced",status="False"} == 1
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| ExternalSecret shows `SecretSyncedError` | IAM permissions missing | Check IRSA role trust policy and SM permissions |
| Secret not updating after rotation | Refresh interval not elapsed | Force sync with annotation or reduce `refreshInterval` |
| Pods still use old secret after sync | Pods need restart | `kubectl rollout restart` the deployment |
| `SecretStore` shows unhealthy | AWS connectivity issue | Check ESO pod logs and VPC/endpoint configuration |
