#!/usr/bin/env bash
set -euo pipefail

KIND_VERSION="${KIND_VERSION:-v0.31.0}"
KIND_OS="${KIND_OS:-linux}"
KIND_ARCH="${KIND_ARCH:-amd64}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
MAX_RETRIES="${MAX_RETRIES:-3}"
BACKOFF_BASE_SECONDS="${BACKOFF_BASE_SECONDS:-2}"

mkdir -p "$INSTALL_DIR"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

binary_url="https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-${KIND_OS}-${KIND_ARCH}"
checksum_url="${binary_url}.sha256sum"
binary_path="${tmp_dir}/kind-${KIND_OS}-${KIND_ARCH}"
checksum_path="${tmp_dir}/kind.sha256sum"

attempt=1
while (( attempt <= MAX_RETRIES )); do
  echo "Installing kind ${KIND_VERSION} (attempt ${attempt}/${MAX_RETRIES})"
  curl -fsSL "$binary_url" -o "$binary_path"
  curl -fsSL "$checksum_url" -o "$checksum_path"

  expected="$(awk '{print $1}' "$checksum_path" | head -n1 | tr -d '[:space:]')"
  actual="$(sha256sum "$binary_path" | awk '{print $1}' | tr -d '[:space:]')"

  if [[ -n "$expected" && "$expected" == "$actual" ]]; then
    chmod +x "$binary_path"
    mv "$binary_path" "${INSTALL_DIR}/kind"
    if [[ -n "${GITHUB_PATH:-}" ]]; then
      echo "$INSTALL_DIR" >>"$GITHUB_PATH"
    fi
    "${INSTALL_DIR}/kind" version
    echo "kind install and checksum verification succeeded"
    exit 0
  fi

  echo "kind checksum mismatch (expected=${expected} actual=${actual})"
  if (( attempt == MAX_RETRIES )); then
    break
  fi
  sleep $(( BACKOFF_BASE_SECONDS * attempt ))
  attempt=$(( attempt + 1 ))
done

echo "Failed to install kind ${KIND_VERSION} after ${MAX_RETRIES} attempts"
exit 1
