#!/usr/bin/env bash
# SessionStart: R-START §15 smoke tripwire. Runs scripts/ci_smoke.py and reports
# PASS/FAIL as session context so a stale ARCHITECTURE.md / broken tree is
# caught before any non-trivial work.
#
# FAIL-OPEN: always exits 0 — this NEVER blocks a session from starting. A
# `timeout` caps the import latency (torch/deepface). DeepFace model weights are
# expected to be cached locally already (~/.deepface/weights); if not, the first
# run is slow but bounded by the timeout.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-/Users/hyungkoookkim/Content}"
cd "$ROOT" 2>/dev/null || exit 0

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

# `timeout` is GNU coreutils; macOS ships it as `gtimeout` (or not at all).
if command -v timeout >/dev/null 2>&1; then
  TO=(timeout 180)
elif command -v gtimeout >/dev/null 2>&1; then
  TO=(gtimeout 180)
else
  TO=()
fi

if out="$("${TO[@]}" "$PY" scripts/ci_smoke.py 2>&1)"; then
  echo "✅ §15 smoke OK — ARCHITECTURE.md runtime invariants hold (R-START tripwire)."
else
  echo "⚠️  §15 smoke FAILED or timed out — ARCHITECTURE.md may be stale OR the working tree is broken."
  echo "    Fix one before non-trivial work (R-START). Tail:"
  echo "$out" | tail -6 | sed 's/^/      /'
fi
exit 0
