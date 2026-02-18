# Helm + kind Runbook

## Local Smoke Path

```bash
make kind-up
make demo-up
```

What `make demo-up` does:
1. Builds local image (`srg-gateway:kind`).
2. Loads image into kind cluster.
3. Installs Helm chart in `srg-system` namespace.
4. Runs endpoint smoke checks (`/healthz`, `/readyz`, `/v1/models`).

## Helm Chart Validation

```bash
make helm-lint
make helm-template
```

## CI Deploy Smoke

Workflow: `.github/workflows/deploy-smoke.yml`

Validates on push/PR:
1. kind cluster bootstrap.
2. Helm lint/template.
3. Chart install + rollout.
4. Endpoint smoke checks.

## Troubleshooting

Check deployment:

```bash
kubectl -n srg-system get pods -o wide
kubectl -n srg-system describe deployment srg-sovereign-rag-gateway
kubectl -n srg-system logs deployment/srg-sovereign-rag-gateway --tail=200
```

## Teardown

```bash
make kind-down
```
