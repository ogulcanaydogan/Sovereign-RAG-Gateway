#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-srg-demo}"

if ! command -v kind >/dev/null 2>&1; then
  echo "kind is required"
  exit 1
fi

if kind get clusters | grep -qx "$CLUSTER_NAME"; then
  kind delete cluster --name "$CLUSTER_NAME"
  echo "kind cluster '$CLUSTER_NAME' deleted"
else
  echo "kind cluster '$CLUSTER_NAME' not found"
fi
