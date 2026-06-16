#!/usr/bin/env bash
# .codex/hooks/update-state.sh
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
#   liveness updates during non-committing work. Seat resolution: CODEX_SEAT
#   env (preferred) ELSE a per-session marker `.codex/presence-seat.<session-id>`
#   so a session launched without CODEX_SEAT can still
#   stamps presence instead of silently no-opping. The hook NEVER writes
#   `current_task` or `status` (those are agent-owned per Rule #19).
# - Skip-perf gate: exits early if HEAD hasn't moved since last run AND
#   STATE.md still exists on disk. Marker stored at
#   `.codex/hooks/.last-state-head` (gitignored).
# - On a HEAD move (commit, reset, checkout, rebase, etc.), regenerates
#   STATE.md from current git state + mailbox cursors.
# - STATE.md is gitignored; this hook never touches git history.
#
# This hook is configured via `.codex/hooks.json`'s PostToolUse matcher.

set -euo pipefail
export LC_ALL=C

_repo_git() {
  env -u GIT_INDEX_FILE git "$@"
}

cd "$(_repo_git rev-parse --show-toplevel 2>/dev/null)" || exit 0

# Sweep stale index.lock files older than 5 minutes to prevent git contention livelocks
find .git/index.lock -mmin +5 -exec rm -f {} \; 2>/dev/null || true

# Presence heartbeat (v6.0 Tier 2, user-authorized 2026-06-11; replaces the
# v5.7 M1 sed-in-place stamp): the hook's liveness signal is a SINGLE-LINE
# atomic overwrite of coordination/presence/<seat>-heartbeat.ts —
# "<ISO-UTC> <short-head>". The hook NEVER touches the seat-owned
# coordination/presence/<seat>.md anymore (status/current_task/intent are
# wholly agent-owned per Rule #19). This kills two recorded failure classes:
# the read-modify-write livelock (hook sed racing a seat's Write tool between
# its read and write — workaround was Bash heredocs) and the stale-status
# split (hook-moved `updated:` under frozen prose → 2 misattribution
# incidents). Liveness = heartbeat freshness; intent = the .md file.
# Seat resolution for Codex: CODEX_SEAT env wins, else the per-session marker
# `.codex/presence-seat.<session-id>`.
# Best-effort: called with `|| true` — a presence hiccup must never abort
# the hook under `set -e` before the STATE.md regen below.
# Tests: tests/unit/test_presence_heartbeat_split.py (awk-slices this fn).
_stamp_presence() {
  local seat="${CODEX_SEAT:-}"
  if [ -z "$seat" ] && [ -n "${CODEX_SESSION_ID:-}" ]; then
    seat=$(cat ".codex/presence-seat.${CODEX_SESSION_ID}" 2>/dev/null || true)
  fi
  [ -n "$seat" ] || return 0
  mkdir -p coordination/presence
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$(_repo_git rev-parse --short HEAD 2>/dev/null || echo '?')" \
    > "coordination/presence/${seat}-heartbeat.ts"
  return 0
}
_stamp_presence || true

# v5.8 — per-seat index auto-refresh (D-a). The peer's commits move shared
# HEAD but NOT this seat's GIT_INDEX_FILE index; the stale index then shows
# phantom mass-deletions in `git status`. Fast-forward the index to HEAD
# when — and ONLY when — the seat has no deliberate staged work to lose.
# Marker: .codex/hooks/.last-index-sync-<basename of GIT_INDEX_FILE>
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
# Known residual (Lane V M-1): in C2/D the index stays stale by design, so
# STATE.md's working-tree field below still shows the phantom storm until
# the seat resolves manually (read-tree -m) or converges via A.
_sync_seat_index() {
  local head="$1" mark last
  [ -n "${GIT_INDEX_FILE:-}" ] || return 0
  [ -f "$GIT_INDEX_FILE" ] || return 0
  mark=".codex/hooks/.last-index-sync-$(basename "$GIT_INDEX_FILE")"
  last=$(cat "$mark" 2>/dev/null || echo "")
  [ "$head" = "$last" ] && return 0
  # Marker writes go via same-dir tmp + rename (Lane V M-2): a kill mid-write
  # would otherwise leave an empty marker (self-healing via A, but avoidable).
  if git diff-index --cached --quiet "$head" 2>/dev/null; then
    printf '%s\n' "$head" > "${mark}.tmp" && mv -f "${mark}.tmp" "$mark"
  elif [ -n "$last" ] \
       && git rev-parse -q --verify "${last}^{commit}" >/dev/null 2>&1 \
       && git diff-index --cached --quiet "$last" 2>/dev/null; then
    git read-tree "$head" && printf '%s\n' "$head" > "${mark}.tmp" && mv -f "${mark}.tmp" "$mark"
  fi
  return 0
}

# v5.9 — skip-worktree pollution auto-clear. Harness child processes
# (Workflow/subagent runs) have twice left skip-worktree bits in the active
# index (N=4; then N=767 of 844 tracked, 2026-06-10) — `git status` then
# hides this seat's OWN edits and add/rm fail with phantom "sparse-checkout"
# errors although no sparse checkout is configured. Trigger op still
# unreproduced (plain and worktree-isolated 1-agent probes both came back
# clean, 2026-06-11) — hence detect-and-clear here rather than a fix at the
# source, plus a log line per event to build the evidence trail.
# Safety: no legitimate skip-worktree use exists in this repo, so ANY flagged
# entry is pollution. `update-index --no-skip-worktree` flips ONLY the flag
# bit — staged content is untouched (pinned by test), unlike the manual
# wholesale `git read-tree HEAD` fix, which destroys staged work. Targets
# whatever index this process resolves (the per-seat GIT_INDEX_FILE under
# D-a, else the default) — exactly the index a polluting child inherits.
# Deliberately NOT gated on GIT_INDEX_FILE, and runs BEFORE the skip-perf
# gate: pollution arrives WITHOUT a HEAD move.
# Tests: tests/unit/test_skip_worktree_clear.py (awk-slices this function).
_clear_skip_worktree() {
  local -a _flagged=()
  local _e
  while IFS= read -r -d '' _e; do
    case "$_e" in 'S '*) _flagged+=("${_e#S }") ;; esac
  done < <(git ls-files -v -z 2>/dev/null)
  [ "${#_flagged[@]}" -gt 0 ] || return 0
  git update-index --no-skip-worktree -- "${_flagged[@]}" 2>/dev/null || return 0
  printf '%s cleared=%d index=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${#_flagged[@]}" \
    "$(basename "${GIT_INDEX_FILE:-default}")" \
    >> .codex/hooks/.skip-worktree-cleared.log 2>/dev/null || true
  return 0
}

MARKER=".codex/hooks/.last-state-head"
CURRENT=$(_repo_git rev-parse HEAD 2>/dev/null || exit 0)
LAST=$(cat "$MARKER" 2>/dev/null || echo "")

# v5.9: clear index pollution first (sane index before sync logic; both run
# before the shared skip-perf gate — see each function's comment).
_clear_skip_worktree || true

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
HEAD_SUBJECT=$(_repo_git log -1 --format='%s' HEAD)
BRANCH=$(_repo_git rev-parse --abbrev-ref HEAD)
AHEAD=$(_repo_git rev-list --count "origin/${BRANCH}..HEAD" 2>/dev/null || echo "?")
BEHIND=$(_repo_git rev-list --count "HEAD..origin/${BRANCH}" 2>/dev/null || echo "?")

WT_LINES=$(_repo_git status --porcelain 2>/dev/null)
if [ -z "$WT_LINES" ]; then
  WT_STATE="clean"
else
  NUM_DIRTY=$(echo "$WT_LINES" | grep -c '^' || true)
  WT_STATE=$(printf "DIRTY(%s):\n%s" "$NUM_DIRTY" "$(echo "$WT_LINES" | head -5)")
fi

# Smoke + pytest from latest commit body (cheaper than re-running, and the
# commit body is the truth at commit time; if the working tree has drifted
# since, both fields explicitly suggest manual re-run).
SMOKE_LINE=$(_repo_git log -1 --format='%B' HEAD | grep -E "ci_smoke\.py" -A1 | tail -1 || true)
if echo "$SMOKE_LINE" | grep -q "OK"; then
  SMOKE_RESULT="OK (per commit body)"
elif echo "$SMOKE_LINE" | grep -qE "FAIL|error"; then
  SMOKE_RESULT="FAIL (per commit body)"
else
  SMOKE_RESULT="unknown (not in commit body; re-run manually)"
fi

PYTEST_LINE=$(_repo_git log -1 --format='%B' HEAD | grep -Eo '[0-9]+ passed, [0-9]+ skipped(, [0-9]+ failed)?' | head -1 || true)
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
  for f in coordination/mailbox/sent/*-to-"${role}"-*.md coordination/mailbox/sent/*-to-all-*.md; do
    [ -e "$f" ] || continue
    ts=$(basename "$f"); ts=${ts:0:20}
    # Byte-order compare of fixed-width ISO == chronological (LC_ALL=C exported above).
    [[ "$ts" > "$curkey" ]] && count=$((count+1))
  done
  echo "$count"
}
UNREAD_DIR=0; UNREAD_OP=0; UNREAD_DIR2=0; UNREAD_OP2=0
if [ -d "coordination/mailbox/sent" ]; then
  UNREAD_DIR=$(_unread_for director)
  UNREAD_OP=$(_unread_for operator)
  UNREAD_DIR2=$(_unread_for director2)
  UNREAD_OP2=$(_unread_for operator2)
fi

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

cat > STATE.md <<EOF
<!-- AUTO-GENERATED by .codex/hooks/update-state.sh — DO NOT HAND-EDIT.
     File is gitignored (B-003 Option E, cycle 8). Purely-local
     informational artifact; regenerated on each HEAD move. -->
# Repository State Snapshot

- **HEAD:** \`${HEAD_SHA}\` (${HEAD_SUBJECT})
- **Branch:** ${BRANCH}, ${AHEAD} ahead / ${BEHIND} behind \`origin/${BRANCH}\`
- **Working tree:** ${WT_STATE}
- **Smoke:** ${SMOKE_RESULT} (last run ${TIMESTAMP})
- **Pytest:** ${PYTEST_LINE}
- **Unread mailbox:** director=${UNREAD_DIR}, operator=${UNREAD_OP}, director2=${UNREAD_DIR2}, operator2=${UNREAD_OP2}
- **Updated:** ${TIMESTAMP} (after HEAD \`${HEAD_SHA}\`)
EOF

# Record HEAD so subsequent Bash calls skip regen unless HEAD moves again.
_repo_git rev-parse HEAD > "$MARKER"
