#!/usr/bin/env bash
# SessionStart: R-START §15 smoke tripwire. Runs scripts/ci_smoke.py and reports
# PASS/FAIL as session context so a stale ARCHITECTURE.md / broken tree is caught
# before any non-trivial work.
#
# FAIL-OPEN: always exits 0 — NEVER blocks a session from starting. The 180s
# bound is enforced inside Python's subprocess.run(timeout=...) so it is portable
# (no dependency on GNU `timeout`/`gtimeout`, which macOS does not ship) and
# cannot leave the session hanging. DeepFace weights are expected cached locally
# (~/.deepface/weights); a cold download would be bounded by the timeout.
set -uo pipefail

# Derive the repo root from this script's own location (.codex/hooks/ -> root),
# independent of cwd or machine. Fail-open if unresolvable.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)" || exit 0
[ -n "$ROOT" ] && cd "$ROOT" 2>/dev/null || exit 0

PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "⚠️  §15 smoke SKIPPED — project venv missing at .venv/bin/python."
  echo "    Bootstrap with: /opt/homebrew/bin/python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 0
fi

# Run the smoke under a hard 180s bound enforced by Python itself.
if out="$("$PY" - "$PY" 2>&1 <<'PYWRAP'
import subprocess, sys
try:
    r = subprocess.run([sys.argv[1], "scripts/ci_smoke.py"], timeout=180)
    sys.exit(r.returncode)
except subprocess.TimeoutExpired:
    sys.stderr.write("ci_smoke.py exceeded 180s — aborted\n")
    sys.exit(124)
except Exception as exc:
    sys.stderr.write("session-smoke wrapper error: %s\n" % exc)
    sys.exit(125)
PYWRAP
)"; then
  echo "✅ §15 smoke OK — ARCHITECTURE.md runtime invariants hold (R-START tripwire)."
else
  echo "⚠️  §15 smoke FAILED or timed out — ARCHITECTURE.md may be stale OR the working tree is broken."
  echo "    Fix one before non-trivial work (R-START). Tail:"
  echo "$out" | tail -6 | sed 's/^/      /'
fi
exit 0
