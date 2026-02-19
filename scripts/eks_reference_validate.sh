#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHART_DIR="${ROOT_DIR}/charts/sovereign-rag-gateway"
VALUES_FILE="${ROOT_DIR}/deploy/eks/values.example.yaml"
RENDERED_FILE="${ROOT_DIR}/artifacts/eks/rendered.yaml"

mkdir -p "$(dirname "${RENDERED_FILE}")"

helm lint "${CHART_DIR}"
helm template srg "${CHART_DIR}" -f "${VALUES_FILE}" >"${RENDERED_FILE}"

if [[ ! -s "${RENDERED_FILE}" ]]; then
  echo "Rendered manifest is empty: ${RENDERED_FILE}" >&2
  exit 1
fi

if ! grep -q "^apiVersion:" "${RENDERED_FILE}"; then
  echo "Rendered manifest missing apiVersion entries" >&2
  exit 1
fi

if ! grep -q "^kind: Deployment$" "${RENDERED_FILE}"; then
  echo "Rendered manifest missing Deployment kind" >&2
  exit 1
fi

if ! grep -q "^kind: Service$" "${RENDERED_FILE}"; then
  echo "Rendered manifest missing Service kind" >&2
  exit 1
fi

echo "EKS reference validation passed"
