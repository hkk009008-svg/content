#!/usr/bin/env bash
# .claude/hooks/update-state.sh
# PostToolUse hook: regenerates STATE.md on HEAD moves + stamps presence.
#
# B-003 Option E (cycle 8, 2026-05-26) replaced this script's prior
# "amend STATE.md into the just-made commit" model with the much simpler
# "STATE.md is gitignored, regenerate it on disk only" model. The historical
# rationale for amending — making commit history reflect repository state —
# was already leaky (B-002 stale-by-one: STATE.md inside any commit was one
# SHA behind because it was generated pre-amend) AND produced B-003 (compound
# `git commit && git push` left local diverged from origin because the hook
# fired after the push). Option E retires both failure modes by accepting
# that STATE.md is purely-local informational state; it never enters commits
# again. See `docs/B-003-design-exploration.md` for the full analysis.
#
# Behavior:
# - Runs on every PostToolUse: Bash|Write|Edit tool call.
# - Presence auto-freshness (v5.7 M1): stamps the seat's presence file
#   (head_at_write + updated) on EVERY call, before the skip-perf gate, so
#   liveness updates during non-committing work. Seat resolution: CLAUDE_SEAT
#   env (preferred) ELSE a per-session marker `.claude/presence-seat.<session-id>`
#   (hardening 2026-06-06) so a session launched without CLAUDE_SEAT still
#   stamps presence instead of silently no-opping. The hook NEVER writes
#   `current_task` or `status` (those are agent-owned per Rule #19).
# - Skip-perf gate: exits early if HEAD hasn't moved since last run AND
#   STATE.md still exists on disk. Marker stored at
#   `.claude/hooks/.last-state-head` (gitignored).
# - On a HEAD move (commit, reset, checkout, rebase, etc.), regenerates
#   STATE.md from current git state + mailbox cursors.
# - STATE.md is gitignored; this hook never touches git history.
#
# This hook is configured via `.claude/settings.local.json`'s
# PostToolUse: Bash|Write|Edit matcher.

set -euo pipefail
export LC_ALL=C

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# Presence auto-freshness (v5.7 M1): stamp this seat's presence file every
# Bash/Write/Edit call (NOT HEAD-gated — liveness must update during
# non-committing work). The agent owns `status` + `current_task` (Rule #19);
# the hook only bumps `head_at_write` + `updated`.
# Wrapped in `{ … } || true` (Lane V M1, 2026-05-30): a presence-write hiccup
# (mkdir/mktemp/sed/mv/printf) must NEVER abort the hook under `set -e` before
# the STATE.md regen below — presence is best-effort, STATE.md is the priority.
{
# Resolve the seat. CLAUDE_SEAT (per-launch env — the documented D-a path,
# coordination/README.md §"Per-seat launch") wins. FALLBACK (hardening
# 2026-06-06): if the session was launched WITHOUT CLAUDE_SEAT, read a
# per-session marker the agent writes at start —
# `.claude/presence-seat.<session-id>`, keyed by CLAUDE_CODE_SESSION_ID (which
# the hook inherits) so two concurrent seats can NEVER collide on one file.
# Root cause this closes: a forgotten CLAUDE_SEAT made presence stamping
# silently no-op for a whole session, so both seats mis-read each other's
# liveness (the exact Rule #19/#20 failure observed 2026-06-06).
_SEAT="${CLAUDE_SEAT:-}"
if [ -z "$_SEAT" ] && [ -n "${CLAUDE_CODE_SESSION_ID:-}" ]; then
  _SEAT=$(cat ".claude/presence-seat.${CLAUDE_CODE_SESSION_ID}" 2>/dev/null || true)
fi
if [ -n "$_SEAT" ]; then
  mkdir -p coordination/presence
  _PF="coordination/presence/${_SEAT}.md"
  _NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  _H=$(git rev-parse --short HEAD 2>/dev/null || echo "?")
  if [ -f "$_PF" ]; then
    _t=$(mktemp)
    sed -e "s|^head_at_write:.*|head_at_write: ${_H}|" \
        -e "s|^updated:.*|updated: ${_NOW}|" "$_PF" > "$_t" && mv "$_t" "$_PF"
  else
    printf 'seat: %s\nstatus: active\ncurrent_task: (set me when your focus changes)\nhead_at_write: %s\nupdated: %s\n' \
      "$_SEAT" "$_H" "$_NOW" > "$_PF"
  fi
fi
} || true

# v5.8 — per-seat index auto-refresh (D-a). The peer's commits move shared
# HEAD but NOT this seat's GIT_INDEX_FILE index; the stale index then shows
# phantom mass-deletions in `git status`. Fast-forward the index to HEAD
# when — and ONLY when — the seat has no deliberate staged work to lose.
# Marker: .claude/hooks/.last-index-sync-<basename of GIT_INDEX_FILE>
# (CANNOT reuse .last-state-head: it is shared; the committing seat's hook
# advances it first, which would skip this sync exactly when needed).
# Decision table ($1 = current HEAD sha):
#   A. index tree == HEAD tree              -> record marker=HEAD (own commit / already synced)
#   B. HEAD == marker, index diverged       -> deliberate `git add` since sync — NEVER touch
#   C1. HEAD != marker, index == marker tree -> pure peer-commit staleness -> read-tree; marker=HEAD
#   C2. HEAD != marker, index != marker tree -> mixed (staged work + peer commit) -> leave for manual read-tree -m
#   D. no marker baseline                    -> converge only via A; never guess
# Safety: read-tree fires ONLY in C1, where the index byte-equals a tree
# containing no user work — the staged-WIP-loss class is excluded by construction.
_sync_seat_index() {
  local head="$1" mark last
  [ -n "${GIT_INDEX_FILE:-}" ] || return 0
  [ -f "$GIT_INDEX_FILE" ] || return 0
  mark=".claude/hooks/.last-index-sync-$(basename "$GIT_INDEX_FILE")"
  last=$(cat "$mark" 2>/dev/null || echo "")
  [ "$head" = "$last" ] && return 0
  if git diff-index --cached --quiet "$head" 2>/dev/null; then
    printf '%s\n' "$head" > "$mark"
  elif [ -n "$last" ] \
       && git rev-parse -q --verify "${last}^{commit}" >/dev/null 2>&1 \
       && git diff-index --cached --quiet "$last" 2>/dev/null; then
    git read-tree "$head" && printf '%s\n' "$head" > "$mark"
  fi
  return 0
}

MARKER=".claude/hooks/.last-state-head"
CURRENT=$(git rev-parse HEAD 2>/dev/null || exit 0)
LAST=$(cat "$MARKER" 2>/dev/null || echo "")

# v5.8: sync the per-seat index BEFORE the shared skip-perf gate (see
# _sync_seat_index comment for why the shared marker cannot gate this).
_sync_seat_index "$CURRENT" || true

# Perf: skip regen if HEAD hasn't moved AND STATE.md exists on disk.
# Mid-session mailbox writes won't refresh STATE.md until the next HEAD
# move, but mailbox surfacing is mostly used at session-start (Rule #8
# awareness gate), which always reads the file fresh after a fresh HEAD.
if [ "$CURRENT" = "$LAST" ] && [ -f STATE.md ]; then
  exit 0
fi

HEAD_SHA="$CURRENT"
HEAD_SUBJECT=$(git log -1 --format='%s' HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
AHEAD=$(git rev-list --count "origin/${BRANCH}..HEAD" 2>/dev/null || echo "?")
BEHIND=$(git rev-list --count "HEAD..origin/${BRANCH}" 2>/dev/null || echo "?")

WT_LINES=$(git status --porcelain 2>/dev/null | head -5)
if [ -z "$WT_LINES" ]; then
  WT_STATE="clean"
else
  WT_STATE=$(printf "dirty:\n%s" "$WT_LINES")
fi

# Smoke + pytest from latest commit body (cheaper than re-running, and the
# commit body is the truth at commit time; if the working tree has drifted
# since, both fields explicitly suggest manual re-run).
SMOKE_LINE=$(git log -1 --format='%B' HEAD | grep -E "ci_smoke\.py" -A1 | tail -1 || true)
if echo "$SMOKE_LINE" | grep -q "OK"; then
  SMOKE_RESULT="OK (per commit body)"
elif echo "$SMOKE_LINE" | grep -qE "FAIL|error"; then
  SMOKE_RESULT="FAIL (per commit body)"
else
  SMOKE_RESULT="unknown (not in commit body; re-run manually)"
fi

PYTEST_LINE=$(git log -1 --format='%B' HEAD | grep -Eo '[0-9]+ passed, [0-9]+ skipped(, [0-9]+ failed)?' | head -1 || true)
[ -z "$PYTEST_LINE" ] && PYTEST_LINE="(not in commit body; re-run manually for ground truth)"

# Mailbox unread counts (v5.7 M2): count events ADDRESSED to <role> whose
# filename-timestamp is strictly newer than the role cursor's CONTENT timestamp.
# Replaces the prior `find -newer <cursor-mtime>` which (a) counted BOTH
# directions (no to: filter) and (b) compared file mtime, not the cursor's ISO
# content. Filenames are `<UTC-ISO>-<from>-to-<to>-<kind>.md` (README convention);
# the leading token is a fixed-width 20-char `YYYY-MM-DDTHH-MM-SSZ`.
# LC_ALL=C is exported at top of script for byte-order string comparison.
_unread_for() {                       # $1 = role (director|operator)
  local role="$1" cf cur curkey count=0 f ts
  cf="coordination/mailbox/seen/${role}.txt"
  [ -f "$cf" ] || { echo 0; return; }
  cur=$(tr -d '[:space:]' < "$cf")            # 2026-05-30T00:37:53Z
  curkey=$(printf '%s' "$cur" | tr ':' '-')   # -> 2026-05-30T00-37-53Z (match filename token form)
  for f in coordination/mailbox/sent/*-to-"${role}"-*.md; do
    [ -e "$f" ] || continue
    ts=$(basename "$f"); ts=${ts:0:20}
    # Byte-order compare of fixed-width ISO == chronological (LC_ALL=C exported above).
    [[ "$ts" > "$curkey" ]] && count=$((count+1))
  done
  echo "$count"
}
UNREAD_DIR=0; UNREAD_OP=0
if [ -d "coordination/mailbox/sent" ]; then
  UNREAD_DIR=$(_unread_for director)
  UNREAD_OP=$(_unread_for operator)
fi

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

cat > STATE.md <<EOF
<!-- AUTO-GENERATED by .claude/hooks/update-state.sh — DO NOT HAND-EDIT.
     File is gitignored (B-003 Option E, cycle 8). Purely-local
     informational artifact; regenerated on each HEAD move. -->
# Repository State Snapshot

- **HEAD:** \`${HEAD_SHA}\` (${HEAD_SUBJECT})
- **Branch:** ${BRANCH}, ${AHEAD} ahead / ${BEHIND} behind \`origin/${BRANCH}\`
- **Working tree:** ${WT_STATE}
- **Smoke:** ${SMOKE_RESULT} (last run ${TIMESTAMP})
- **Pytest:** ${PYTEST_LINE}
- **Unread mailbox:** director=${UNREAD_DIR}, operator=${UNREAD_OP}
- **Updated:** ${TIMESTAMP} (after HEAD \`${HEAD_SHA}\`)
EOF

# Record HEAD so subsequent Bash calls skip regen unless HEAD moves again.
git rev-parse HEAD > "$MARKER"
