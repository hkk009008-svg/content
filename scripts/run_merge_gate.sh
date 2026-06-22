#!/usr/bin/env bash
# Standing merge-gate daemon (threeway scope-b sub-project 1).
# Writes the protected TEST ref refs/threeway/test-main (NEVER real production main; ADR-056 DD-1).
# Relies on ADR-055 sys.path self-bootstrap in run_merge_gate.py (no import-path env export; DD-2).
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python scripts/run_merge_gate.py \
    --registry-dir coordination/threeway/keys \
    --main-ref refs/threeway/test-main \
    --remote origin \
    "$@"
