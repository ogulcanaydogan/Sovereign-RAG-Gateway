#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-srg-demo}"
NAMESPACE="${NAMESPACE:-srg-system}"
RELEASE_NAME="${RELEASE_NAME:-srg}"
LOCAL_IMAGE="${LOCAL_IMAGE:-srg-gateway:kind}"

for tool in kind kubectl helm docker curl; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "$tool is required"
    exit 1
  fi
done

if ! kind get clusters | grep -qx "$CLUSTER_NAME"; then
  "$ROOT_DIR/deploy/kind/kind-up.sh"
fi

cd "$ROOT_DIR"
docker build -t "$LOCAL_IMAGE" .
kind load docker-image --name "$CLUSTER_NAME" "$LOCAL_IMAGE"

helm upgrade --install "$RELEASE_NAME" "$ROOT_DIR/charts/sovereign-rag-gateway" \
  --namespace "$NAMESPACE" \
  --create-namespace \
  --set image.repository="${LOCAL_IMAGE%:*}" \
  --set image.tag="${LOCAL_IMAGE##*:}" \
  --set image.pullPolicy=IfNotPresent \
  --set env.apiKeys[0]=test-key

kubectl -n "$NAMESPACE" rollout status deployment/"$RELEASE_NAME"-sovereign-rag-gateway --timeout=180s
kubectl -n "$NAMESPACE" get pods -o wide

kubectl -n "$NAMESPACE" port-forward svc/"$RELEASE_NAME"-sovereign-rag-gateway 18080:80 >/tmp/srg-port-forward.log 2>&1 &
PF_PID=$!
trap 'kill $PF_PID >/dev/null 2>&1 || true' EXIT
sleep 5

curl -sf http://127.0.0.1:18080/healthz >/dev/null
curl -sf http://127.0.0.1:18080/readyz >/dev/null
curl -sf http://127.0.0.1:18080/v1/models \
  -H 'Authorization: Bearer test-key' \
  -H 'x-srg-tenant-id: tenant-a' \
  -H 'x-srg-user-id: user-1' \
  -H 'x-srg-classification: public' >/dev/null

echo "kind smoke checks passed"
