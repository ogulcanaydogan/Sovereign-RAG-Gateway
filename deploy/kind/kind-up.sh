#!/usr/bin/env bash
set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-srg-demo}"
CONFIG_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/kind-config.yaml"

if ! command -v kind >/dev/null 2>&1; then
  echo "kind is required"
  exit 1
fi

if kind get clusters | grep -qx "$CLUSTER_NAME"; then
  echo "kind cluster '$CLUSTER_NAME' already exists"
  exit 0
fi

kind create cluster --name "$CLUSTER_NAME" --config "$CONFIG_FILE"
echo "kind cluster '$CLUSTER_NAME' is ready"
