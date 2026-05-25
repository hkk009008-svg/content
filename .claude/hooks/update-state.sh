#!/usr/bin/env bash
# .claude/hooks/update-state.sh
# PostToolUse hook: regenerates STATE.md after a new git commit lands.
# Folds into the triggering commit via git commit --amend --no-edit.
#
# Failure modes handled:
# - Skips if HEAD hasn't changed since last hook run (marker file).
# - Skips if STATE.md is already staged (amend-loop precaution).
# - Skips if not in a git repo (defensive).
# - Tolerates missing origin/main (e.g., fresh clone, detached HEAD).
#
# IMPORTANT (per REPLY C2): This hook amends the just-made commit via
# `git commit --amend --no-edit`. That changes the commit SHA. Reviewers
# and briefs that cite SHAs from chat output may see a different SHA when
# they `git show` after the hook fires. Historical commits are NEVER
# touched; only the just-made one.
#
# KNOWN LIMITATION (v2.1): STATE.md's HEAD field is one SHA stale
# immediately after a commit. The script captures HEAD_SHA BEFORE the
# amend, writes STATE.md with that SHA, then amends — which changes
# HEAD. STATE.md inside the new commit therefore references the
# pre-amend SHA. Cold-starters should verify with `git rev-parse HEAD`
# if the exact SHA matters; the other fields (smoke / pytest / mailbox)
# are post-amend-accurate because they're computed from commit BODY
# content + mailbox file state, which don't depend on the amend.
# Fixing this cleanly requires double-amend (gen → amend → regen with
# new SHA → amend again) which costs an extra amend per commit; we
# accept the stale-by-one for simplicity.
#
# This hook is configured to fire on PostToolUse:Bash via
# .claude/settings.local.json. Because that matcher fires on EVERY Bash
# tool call (not only git commits), the script's first responsibility is
# to detect whether a new commit actually landed since its last run. The
# marker file `.claude/hooks/.last-state-head` (gitignored) holds the
# last-processed HEAD SHA.

set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

MARKER=".claude/hooks/.last-state-head"
CURRENT=$(git rev-parse HEAD 2>/dev/null || exit 0)
LAST=$(cat "$MARKER" 2>/dev/null || echo "")

# Skip if HEAD hasn't moved since our last run (no new commit to process)
if [ "$CURRENT" = "$LAST" ]; then
  exit 0
fi

# Skip if STATE.md is already in the staged set (we're in the amend loop)
if git diff --cached --name-only 2>/dev/null | grep -qx 'STATE.md'; then
  exit 0
fi

# B-002 fix: only amend on real commit operations.
# Without this gate, the marker-vs-HEAD mismatch fires on ANY HEAD-moving
# operation (reset, checkout, rebase, pull --rebase, ...) and the hook
# re-amends an already-pushed commit, rewriting its SHA and producing
# non-fast-forward divergence on the next push attempt. Inspect git
# reflog's most recent action and proceed only when HEAD moved BECAUSE
# of a commit. Marker is silently updated on non-commit moves so
# subsequent Bash calls exit early via the CURRENT == LAST gate above.
REFLOG_SUBJECT=$(git reflog -1 --format='%gs' 2>/dev/null || echo "")
case "$REFLOG_SUBJECT" in
  "commit:"*|"commit ("*)
    # Real commit landed: commit / commit (initial) / commit (amend) /
    # commit (merge) / commit (cherry-pick). Fall through to STATE.md
    # regen + amend below.
    ;;
  *)
    # HEAD moved for a non-commit reason. Re-anchor marker; exit clean.
    git rev-parse HEAD > "$MARKER"
    exit 0
    ;;
esac

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

# Smoke (per REPLY R1: extracted from latest commit body; not re-run)
# Trade-off: hook stays ~100ms (vs ~3s if smoke ran). Cold-starter
# re-runs scripts/ci_smoke.py manually if STATE.md says "unknown" or
# the commit-body smoke line is stale relative to current code.
SMOKE_LINE=$(git log -1 --format='%B' HEAD | grep -E "ci_smoke\.py" -A1 | tail -1 || true)
if echo "$SMOKE_LINE" | grep -q "OK"; then
  SMOKE_RESULT="OK (per commit body)"
elif echo "$SMOKE_LINE" | grep -qE "FAIL|error"; then
  SMOKE_RESULT="FAIL (per commit body)"
else
  SMOKE_RESULT="unknown (not in commit body; re-run manually)"
fi

# Pytest count from latest commit body (regex).
# v2.1 fix: original regex required "Z failed" in the match, but pytest
# omits "0 failed" in the success case (e.g., "636 passed, 3 skipped,
# 11 warnings, 10 subtests passed"). Made the failed-count match
# optional. Still tolerates the historical "X passed, Y skipped, Z failed"
# format.
PYTEST_LINE=$(git log -1 --format='%B' HEAD | grep -Eo '[0-9]+ passed, [0-9]+ skipped(, [0-9]+ failed)?' | head -1 || true)
[ -z "$PYTEST_LINE" ] && PYTEST_LINE="(not in commit body; re-run manually for ground truth)"

# Mailbox unread counts
UNREAD_DIR=0
UNREAD_OP=0
if [ -d "coordination/mailbox/sent" ]; then
  if [ -f "coordination/mailbox/seen/director.txt" ]; then
    UNREAD_DIR=$(find coordination/mailbox/sent -type f -name '*.md' -newer coordination/mailbox/seen/director.txt 2>/dev/null | wc -l | tr -d ' ')
  fi
  if [ -f "coordination/mailbox/seen/operator.txt" ]; then
    UNREAD_OP=$(find coordination/mailbox/sent -type f -name '*.md' -newer coordination/mailbox/seen/operator.txt 2>/dev/null | wc -l | tr -d ' ')
  fi
fi

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

cat > STATE.md <<EOF
<!-- AUTO-GENERATED by .claude/hooks/update-state.sh — DO NOT HAND-EDIT -->
# Repository State Snapshot

- **HEAD:** \`${HEAD_SHA}\` (${HEAD_SUBJECT})
- **Branch:** ${BRANCH}, ${AHEAD} ahead / ${BEHIND} behind \`origin/${BRANCH}\`
- **Working tree:** ${WT_STATE}
- **Smoke:** ${SMOKE_RESULT} (last run ${TIMESTAMP})
- **Pytest:** ${PYTEST_LINE}
- **Unread mailbox:** director=${UNREAD_DIR}, operator=${UNREAD_OP}
- **Updated:** ${TIMESTAMP} (after commit \`${HEAD_SHA}\`)
EOF

# Fold into the just-made commit (no new commit appears in log).
# DELIBERATE (per REPLY C4): ONLY STATE.md is staged. Never use `git add -A`
# or `git add .` — counter-bumps in AGENTS.md/CLAUDE.md must remain in working
# tree per Rule #6 (operator territory; fold-and-surface, not auto-absorb).
git add STATE.md
git commit --amend --no-edit --no-verify

# Record the post-amend HEAD so subsequent hook invocations skip until a
# new commit lands.
git rev-parse HEAD > "$MARKER"
