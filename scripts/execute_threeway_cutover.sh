#!/usr/bin/env bash
set -euo pipefail

# Three-Way Protocol cutover driver: provision keys (idempotent) + run the IRREVERSIBLE
# legacy->signed-bus cutover. Both this script AND threeway.cutover refuse the irreversible
# step without an explicit --yes (double-gated; DECISIONS.md ADR-045).

REGISTRY_DIR="coordination/threeway/keys"
KEYSTORE_DIR="${THREEWAY_KEYSTORE:-$HOME/.threeway/keys}"
PY="${PYTHON:-.venv/bin/python}"

if [ "${1:-}" != "--yes" ]; then
  echo "REFUSING: the legacy->signed-bus cutover is IRREVERSIBLE (DECISIONS.md ADR-045)."
  echo "Re-run to confirm:   $0 --yes"
  exit 2
fi

echo "=== Three-Way Protocol Cutover ==="

# [1/2] Provision keys ONLY if the registry is empty. Re-keying an existing registry would
#       invalidate the committed trust root and every signature made under it.
if ls "$REGISTRY_DIR"/*.pub >/dev/null 2>&1; then
  echo "[1/2] Keys already provisioned in $REGISTRY_DIR — skipping bootstrap (re-key would invalidate the trust root)."
else
  echo "[1/2] Provisioning keys..."
  mkdir -p "$REGISTRY_DIR" "$KEYSTORE_DIR"
  "$PY" -m threeway.keys_bootstrap --registry "$REGISTRY_DIR" --keystore "$KEYSTORE_DIR"
  echo "Public keys -> $REGISTRY_DIR ; private keys -> $KEYSTORE_DIR (NEVER commit private keys)."
fi

# [2/2] Execute the cutover. The CLI also requires --yes (double-gated).
echo "[2/2] Executing Slice 2.5 cutover (IRREVERSIBLE)..."
"$PY" -m threeway.cutover --repo . --coord-root . --yes

echo "=== Cutover complete: the signed bus is now the live coordination substrate. ==="
