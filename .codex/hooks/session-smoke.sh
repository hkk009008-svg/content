#!/usr/bin/env bash
# Codex SessionStart wrapper for the existing R-START smoke tripwire.
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$ROOT" ]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)" || exit 0
fi
[ -n "$ROOT" ] || exit 0

exec bash "$ROOT/.claude/hooks/session-smoke.sh"
