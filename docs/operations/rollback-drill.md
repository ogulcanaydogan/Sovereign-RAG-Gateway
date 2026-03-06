# Rollback Drill (Kind)

This drill validates one-command rollback behavior for the Helm deployment path:

- Upgrade target: `v0.7.0`
- Rollback target: previous stable `v0.6.0`

## Local Run

```bash
CLUSTER_NAME=srg-rollback \
NAMESPACE=srg-system \
RELEASE_NAME=srg \
IMAGE_REPOSITORY=ghcr.io/ogulcanaydogan/sovereign-rag-gateway \
CURRENT_TAG=v0.7.0 \
PREVIOUS_STABLE_TAG=v0.6.0 \
REPORT_DIR=artifacts/rollback-drill \
./deploy/kind/rollback-drill.sh
```

## CI Run

Use workflow: `.github/workflows/rollback-drill.yml`

- `workflow_dispatch`: on-demand rollback verification.
- `schedule`: weekly automated validation.

## What Is Validated

1. Revision-1 deploy succeeds at `v0.6.0`.
2. Revision-2 upgrade succeeds at `v0.7.0`.
3. `helm rollback` returns to revision-1.
4. Health/ready/models endpoint smoke checks pass after each stage.
5. Active deployment image tag after rollback matches `v0.6.0`.

## Reports

Artifacts are written to `artifacts/rollback-drill/`:

- `rollback-<timestamp>.json`
- `rollback-<timestamp>.md`

JSON report fields include:

- Cluster/namespace/release metadata
- Previous/current tags
- Helm revisions
- Active image after rollback
- Result and per-check statuses

## Failure Diagnostics

When the workflow fails, it uploads:

- Kind exported logs
- Deployment describe output
- Gateway deployment logs
- Port-forward log file
