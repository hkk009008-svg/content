#!/usr/bin/env bash
# Codex PostToolUse wrapper for the shared STATE.md + heartbeat updater.
#
# The legacy implementation resolves the active seat through CLAUDE_SEAT. Codex
# launches should set CODEX_SEAT; this wrapper bridges that name without editing
# the Claude source hook.
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$ROOT" ]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)" || exit 0
fi
[ -n "$ROOT" ] || exit 0

if [ -z "${CLAUDE_SEAT:-}" ] && [ -n "${CODEX_SEAT:-}" ]; then
  export CLAUDE_SEAT="$CODEX_SEAT"
fi

exec bash "$ROOT/.claude/hooks/update-state.sh"
