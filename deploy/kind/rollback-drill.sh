#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-srg-rollback}"
NAMESPACE="${NAMESPACE:-srg-system}"
RELEASE_NAME="${RELEASE_NAME:-srg}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:-ghcr.io/ogulcanaydogan/sovereign-rag-gateway}"
PREVIOUS_STABLE_TAG="${PREVIOUS_STABLE_TAG:-v0.6.0}"
CURRENT_TAG="${CURRENT_TAG:-v0.7.0}"
REPORT_DIR="${REPORT_DIR:-artifacts/rollback-drill}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_JSON="$REPORT_DIR/rollback-$TS.json"
REPORT_MD="$REPORT_DIR/rollback-$TS.md"

for tool in kind kubectl helm curl python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "$tool is required"
    exit 1
  fi
done

mkdir -p "$REPORT_DIR"

if ! kind get clusters | grep -qx "$CLUSTER_NAME"; then
  CLUSTER_NAME="$CLUSTER_NAME" "$ROOT_DIR/deploy/kind/kind-up.sh"
fi

smoke_check() {
  local stage="$1"
  local port="$2"
  kubectl -n "$NAMESPACE" port-forward svc/"$RELEASE_NAME"-sovereign-rag-gateway "$port":80 >/tmp/srg-rollback-port-forward.log 2>&1 &
  local pf_pid=$!
  trap 'kill $pf_pid >/dev/null 2>&1 || true' RETURN
  sleep 6

  curl -sf "http://127.0.0.1:$port/healthz" >/dev/null
  curl -sf "http://127.0.0.1:$port/readyz" >/dev/null
  curl -sf "http://127.0.0.1:$port/v1/models" \
    -H 'Authorization: Bearer test-key' \
    -H 'x-srg-tenant-id: tenant-a' \
    -H 'x-srg-user-id: user-1' \
    -H 'x-srg-classification: public' >/dev/null

  kill "$pf_pid" >/dev/null 2>&1 || true
  trap - RETURN
  echo "smoke check passed for stage=$stage"
}

chart_path="$ROOT_DIR/charts/sovereign-rag-gateway"

start_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

helm upgrade --install "$RELEASE_NAME" "$chart_path" \
  --namespace "$NAMESPACE" \
  --create-namespace \
  --set image.repository="$IMAGE_REPOSITORY" \
  --set image.tag="$PREVIOUS_STABLE_TAG" \
  --set image.pullPolicy=IfNotPresent \
  --set env.apiKeys[0]=test-key
kubectl -n "$NAMESPACE" rollout status deployment/"$RELEASE_NAME"-sovereign-rag-gateway --timeout=240s
smoke_check "revision-1" 18081

revision_1="$(helm -n "$NAMESPACE" history "$RELEASE_NAME" -o json | python3 -c 'import json,sys; h=json.load(sys.stdin); print(h[-1]["revision"])')"

helm upgrade "$RELEASE_NAME" "$chart_path" \
  --namespace "$NAMESPACE" \
  --set image.repository="$IMAGE_REPOSITORY" \
  --set image.tag="$CURRENT_TAG" \
  --set image.pullPolicy=IfNotPresent \
  --set env.apiKeys[0]=test-key
kubectl -n "$NAMESPACE" rollout status deployment/"$RELEASE_NAME"-sovereign-rag-gateway --timeout=240s
smoke_check "revision-2" 18082

revision_2="$(helm -n "$NAMESPACE" history "$RELEASE_NAME" -o json | python3 -c 'import json,sys; h=json.load(sys.stdin); print(h[-1]["revision"])')"

helm rollback "$RELEASE_NAME" "$revision_1" -n "$NAMESPACE"
kubectl -n "$NAMESPACE" rollout status deployment/"$RELEASE_NAME"-sovereign-rag-gateway --timeout=240s
smoke_check "rollback" 18083

active_image="$(kubectl -n "$NAMESPACE" get deployment "$RELEASE_NAME"-sovereign-rag-gateway -o jsonpath='{.spec.template.spec.containers[0].image}')"
if [[ "$active_image" != *":$PREVIOUS_STABLE_TAG" ]]; then
  echo "rollback image mismatch: expected tag $PREVIOUS_STABLE_TAG, got $active_image"
  exit 1
fi

end_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 - <<PY
import json
from pathlib import Path

report = {
    "timestamp": "$TS",
    "cluster_name": "$CLUSTER_NAME",
    "namespace": "$NAMESPACE",
    "release_name": "$RELEASE_NAME",
    "image_repository": "$IMAGE_REPOSITORY",
    "previous_stable_tag": "$PREVIOUS_STABLE_TAG",
    "current_tag": "$CURRENT_TAG",
    "start_utc": "$start_utc",
    "end_utc": "$end_utc",
    "revision_1": "$revision_1",
    "revision_2": "$revision_2",
    "active_image_after_rollback": "$active_image",
    "result": "pass",
    "checks": {
        "revision_1_deploy": "pass",
        "revision_2_upgrade": "pass",
        "rollback": "pass",
        "endpoint_smoke": "pass",
        "image_reverted": "pass",
    },
}
Path("$REPORT_JSON").write_text(json.dumps(report, indent=2) + "\\n", encoding="utf-8")
PY

cat >"$REPORT_MD" <<MD
# Rollback Drill Report - $TS

- Cluster: \`$CLUSTER_NAME\`
- Namespace: \`$NAMESPACE\`
- Release: \`$RELEASE_NAME\`
- Repository: \`$IMAGE_REPOSITORY\`
- Previous stable tag: \`$PREVIOUS_STABLE_TAG\`
- Current tag tested: \`$CURRENT_TAG\`
- Helm revisions: \`$revision_1 -> $revision_2 -> rollback to $revision_1\`
- Active image after rollback: \`$active_image\`
- Result: \`pass\`

## Validation

- Revision-1 deploy passed.
- Revision-2 upgrade passed.
- Rollback command passed.
- Endpoint smoke checks passed after each stage.
- Deployment image reverted to previous stable tag.
MD

echo "rollback drill report json: $REPORT_JSON"
echo "rollback drill report md: $REPORT_MD"
