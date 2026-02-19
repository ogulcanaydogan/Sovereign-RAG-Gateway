#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-srg-demo}"
NAMESPACE="${NAMESPACE:-srg-system}"
RELEASE_NAME="${RELEASE_NAME:-srg}"
LOCAL_IMAGE="${LOCAL_IMAGE:-srg-gateway:kind}"

for tool in kind kubectl helm docker curl python3; do
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

WEBHOOK_ENDPOINTS='[{"url":"http://127.0.0.1:1/unreachable","secret":"local-smoke","event_types":["policy_denied","budget_exceeded","redaction_hit","provider_fallback","provider_error"]}]'
VALUES_FILE="$(mktemp)"
cat >"$VALUES_FILE" <<EOF
env:
  webhookEndpoints: '$WEBHOOK_ENDPOINTS'
EOF
trap 'rm -f "$VALUES_FILE"' EXIT

helm upgrade --install "$RELEASE_NAME" "$ROOT_DIR/charts/sovereign-rag-gateway" \
  --namespace "$NAMESPACE" \
  --create-namespace \
  -f "$VALUES_FILE" \
  --set image.repository="${LOCAL_IMAGE%:*}" \
  --set image.tag="${LOCAL_IMAGE##*:}" \
  --set image.pullPolicy=IfNotPresent \
  --set env.apiKeys[0]=test-key \
  --set env.budgetEnabled=true \
  --set env.budgetDefaultCeiling=20 \
  --set env.budgetWindowSeconds=3600 \
  --set env.webhookEnabled=true \
  --set env.webhookMaxRetries=1 \
  --set env.tracingEnabled=true \
  --set env.tracingMaxTraces=200

kubectl -n "$NAMESPACE" rollout status deployment/"$RELEASE_NAME"-sovereign-rag-gateway --timeout=180s
kubectl -n "$NAMESPACE" get pods -o wide

POD_NAME="$(kubectl -n "$NAMESPACE" get pod -l app.kubernetes.io/instance="$RELEASE_NAME" -o jsonpath='{.items[0].metadata.name}')"

kubectl -n "$NAMESPACE" port-forward svc/"$RELEASE_NAME"-sovereign-rag-gateway 18080:80 >/tmp/srg-port-forward.log 2>&1 &
PF_PID=$!
trap 'kill $PF_PID >/dev/null 2>&1 || true; rm -f "$VALUES_FILE"' EXIT
sleep 6

curl -sf http://127.0.0.1:18080/healthz >/dev/null
curl -sf http://127.0.0.1:18080/readyz >/dev/null

HEADER_FILE="$(mktemp)"
BODY_FILE="$(mktemp)"
HTTP_CODE="$(curl -sS -D "$HEADER_FILE" -o "$BODY_FILE" -w '%{http_code}' \
  -X POST http://127.0.0.1:18080/v1/chat/completions \
  -H 'Authorization: Bearer test-key' \
  -H 'x-srg-tenant-id: tenant-a' \
  -H 'x-srg-user-id: user-1' \
  -H 'x-srg-classification: phi' \
  -H 'content-type: application/json' \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Patient DOB 01/01/1990 follow-up"}],"max_tokens":8}')"

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "Unexpected status for redaction/tracing request: $HTTP_CODE"
  cat "$BODY_FILE"
  exit 1
fi

REQUEST_ID="$(awk -F': ' 'tolower($1)=="x-request-id" {gsub(/\r/,"",$2); print $2}' "$HEADER_FILE" | tail -n1)"
if [[ -z "$REQUEST_ID" ]]; then
  echo "Missing x-request-id in response headers"
  exit 1
fi

TRACE_FILE="$(mktemp)"
curl -sS "http://127.0.0.1:18080/v1/traces/$REQUEST_ID" \
  -H 'Authorization: Bearer test-key' \
  -H 'x-srg-tenant-id: tenant-a' \
  -H 'x-srg-user-id: user-1' \
  -H 'x-srg-classification: public' >"$TRACE_FILE"

python3 - "$TRACE_FILE" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
spans = payload.get("spans", [])
ops = {span.get("operation") for span in spans if isinstance(span, dict)}
required = {"gateway.request", "policy.evaluate", "redaction.scan", "provider.call", "audit.persist"}
missing = sorted(required - ops)
if missing:
    raise SystemExit(f"missing required spans: {missing}")
PY

BUDGET_BODY="$(mktemp)"
BUDGET_CODE="$(curl -sS -o "$BUDGET_BODY" -w '%{http_code}' \
  -X POST http://127.0.0.1:18080/v1/chat/completions \
  -H 'Authorization: Bearer test-key' \
  -H 'x-srg-tenant-id: tenant-a' \
  -H 'x-srg-user-id: user-1' \
  -H 'x-srg-classification: public' \
  -H 'content-type: application/json' \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello budget guard"}],"max_tokens":512}')"

if [[ "$BUDGET_CODE" != "429" ]]; then
  echo "Expected 429 budget_exceeded, got $BUDGET_CODE"
  cat "$BUDGET_BODY"
  exit 1
fi

python3 - "$BUDGET_BODY" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
error = payload.get("error", {})
if error.get("code") != "budget_exceeded":
    raise SystemExit(f"expected budget_exceeded code, got: {error}")
PY

sleep 2
DLQ_LINES="$(kubectl -n "$NAMESPACE" exec "$POD_NAME" -- sh -c 'if [ -f /tmp/audit/webhook_dead_letter.jsonl ]; then wc -l < /tmp/audit/webhook_dead_letter.jsonl; else echo 0; fi' | tr -d '[:space:]')"
if [[ "${DLQ_LINES:-0}" -lt 1 ]]; then
  echo "Expected webhook dead-letter entries, found $DLQ_LINES"
  kubectl -n "$NAMESPACE" logs "$POD_NAME" --tail=200 || true
  exit 1
fi

echo "runtime-controls kind smoke checks passed"
