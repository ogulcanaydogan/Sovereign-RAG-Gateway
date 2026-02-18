#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHART_DIR="${ROOT_DIR}/charts/sovereign-rag-gateway"
VALUES_FILE="${ROOT_DIR}/deploy/eks/values.example.yaml"
RENDERED_FILE="${ROOT_DIR}/artifacts/eks/rendered.yaml"

mkdir -p "$(dirname "${RENDERED_FILE}")"

helm lint "${CHART_DIR}"
helm template srg "${CHART_DIR}" -f "${VALUES_FILE}" >"${RENDERED_FILE}"
kubectl apply --dry-run=client -f "${RENDERED_FILE}" >/dev/null

echo "EKS reference validation passed"
