# B-003 Design Exploration: Compound `commit && push` Hook Divergence

**Status:** Exploration only — no implementation. Requires user buy-in for any
architectural shift before proceeding.
**Drafted:** 2026-05-26 cycle 8
**Backlog row:** see `docs/BACKLOG.md` B-003

---

## Problem recap

The PostToolUse Bash hook (`.claude/hooks/update-state.sh`) fires AFTER the
entire Bash tool call completes — NOT between individual commands in a
`&&` chain. So when the call is `git commit && git push`:

1. `git commit` runs → HEAD = `SHA_initial`
2. `git push` runs (still inside the same Bash call) → origin = `SHA_initial`
3. Bash tool call ends → PostToolUse hook fires
4. Hook sees commit reflog → regens STATE.md → amends → HEAD = `SHA_amended`
5. **Local diverges from origin: ahead=1 (the amended commit) / behind=1 (the pre-amend commit on origin)**

Recovery: `git push --force-with-lease`. Cycle-8 hit this twice (S16 part-6
commit + my own B-002 commit body wrongly claiming "compound is safe").

**Current workaround:** separate `git commit` and `git push` into different
Bash tool calls. The hook then fires after the commit call, amends locally,
and the subsequent push call pushes the amended SHA cleanly. Functional but
adds Bash-call overhead to every commit-then-push pair.

---

## Solution space (5 options)

### Option A — PreToolUse blocker on Bash

Add a `PreToolUse` hook on Bash that scans the command for
`git commit ... && git push` patterns and aborts with a guidance message
("separate into two Bash calls per B-003 workaround").

**Pros:**
- Prevents the problem at the source — user cannot accidentally trigger it
- Education built-in (error message explains why)
- Easy to disable per-command if a false positive surfaces (env flag override)

**Cons:**
- False positives possible: a legitimate `commit && push` workflow inside a
  script being invoked from Bash would also be blocked
- Requires a new hook script + settings.local.json change
- Adds tool-call overhead to every Bash call (the check has to read + scan)
- Implementation risk: PreToolUse hook complexity, output format must match
  Claude's expected interface
- Doesn't help with `git commit; git push` (semicolon) or other variants
  unless the pattern matcher is exhaustive

**Implementation cost:** ~30 min + testing.
**Effort to rollout:** medium (needs the hook script + .claude/settings.local.json edit).
**Reversibility:** easy (revert the settings change + script).

### Option B — PreToolUse warner (non-blocking)

Same as A but emits a warning instead of blocking. User can ignore and
proceed.

**Pros:**
- Lower friction than A
- Educational

**Cons:**
- Doesn't actually fix the bug — just warns about it
- The whole point of B-003 is automated avoidance; warning still requires
  the user to react

**Implementation cost:** ~20 min.
**Verdict:** lighter version of A; same downsides; not recommended.

### Option C — Auto-recovery PostToolUse extension

Extend the existing PostToolUse hook: after amending HEAD, detect if the
pre-amend SHA was just pushed to origin (e.g., compare last reflog action's
content to remote/main). If so, auto-trigger `git push --force-with-lease`
to push the amended SHA.

**Pros:**
- Fully automatic — user never sees divergence
- No changes to existing user workflows

**Cons:**
- Hook makes network calls (slow + potentially fragile)
- Auto-pushing is surprising — violates "never push without explicit user intent"
  per CLAUDE.md "Executing actions with care"
- Force-with-lease can FAIL (e.g., concurrent operator-seat push) → user sees
  cryptic error
- Increases hook complexity significantly
- Conflicts with v5 §Sh "push is director-seat-default" — auto-push removes
  the seat boundary

**Implementation cost:** ~1h + significant testing.
**Verdict:** high power, high risk. Not recommended.

### Option D — Double-amend approach (cycle-7 v2.1 deferral)

Make the hook do TWO amends: first amend with the pre-amend HEAD_SHA in
STATE.md, then regenerate STATE.md with the post-amend SHA, then amend
again. STATE.md inside the final commit references the final commit's SHA.

**Pros:**
- Closes the stale-by-one issue (separate B-002 cosmetic)
- Doesn't change the compound-commit failure mode at all

**Cons:**
- **Does NOT solve B-003.** The compound-call issue is about timing relative
  to `git push`, not about how many amends happen. Push still goes out before
  EITHER amend, in the compound case.
- Costs 2 amends per commit (slow + history-clutter on amend-amend reflog)

**Implementation cost:** ~30 min.
**Verdict:** addresses a DIFFERENT problem (stale-by-one), not B-003. Not
recommended as a B-003 fix; may be worth doing independently if stale-by-one
becomes annoying.

### Option E — Gitignore STATE.md, remove the amend logic

**The architectural shift option.** Make STATE.md a purely-local artifact:
add to .gitignore, remove the `git add STATE.md && git commit --amend`
logic from the hook. STATE.md is regenerated locally on each Bash call;
never committed.

**Pros:**
- **Eliminates B-003 entirely.** No amend → no SHA change → no divergence.
- **Eliminates stale-by-one** (B-002 cosmetic).
- Simplifies the hook by ~50% (no amend logic, no marker-file gymnastics
  needed for the loop-prevention case).
- STATE.md is always fresh post-Bash, never lags
- No more "compound-call workaround" — `git commit && git push` works fine.

**Cons:**
- STATE.md no longer travels with commit history. Anyone cloning the repo
  doesn't see it until they run a Bash command + the hook regenerates.
- Existing STATE.md history in past commits is now disconnected from the new
  local-only model (purely cosmetic; the historic snapshots are still
  readable via `git show`).
- Loses the (mostly-theoretical) property of "commit history reflects state
  at commit time." In practice STATE.md was always one SHA stale anyway.
- Requires updating CLAUDE.md / STATE.md cold-start instructions if any docs
  reference STATE.md as something you can find in git.

**Implementation cost:** ~30 min total:
- ~5 min: add STATE.md to .gitignore
- ~10 min: simplify `.claude/hooks/update-state.sh` (remove marker file +
  staged-set check + reflog gate + amend logic)
- ~5 min: leave existing STATE.md tracked in git for history; new changes
  ignored (via `.gitignore` + `git rm --cached STATE.md`)
- ~10 min: doc updates referencing STATE.md as "committed snapshot"

**Verdict (my recommendation):** ✅ This is the cleanest solution. It treats
STATE.md as what it actually is — a local informational artifact — and
removes the architectural gymnastics that produced both B-002 (stale-by-one)
and B-003 (compound-call divergence).

---

## Recommendation

**Option E (gitignore STATE.md, remove amend) is the cleanest.**

The current architecture optimized for "commit history reflects STATE.md
at commit time," but that property is already broken in two ways:
1. STATE.md is one SHA stale by design (B-002 cosmetic — accepted in v2.1)
2. Compound commit+push produces SHA divergence (B-003 — this exploration)

Both stem from trying to embed auto-generated state into commit history.
Option E accepts that STATE.md is purely informational and removes the
embedding. The cost is "anyone reading commits in isolation doesn't see
STATE.md," but in practice nobody does that — STATE.md is read at session
start from working-tree, not from git history.

Option A (PreToolUse blocker) is the second choice if the user wants to
preserve commit-embedded STATE.md for some reason. It adds friction but
prevents the problem at the source.

Options B, C, D are not recommended.

---

## Decision required

This is an architectural shift that warrants user-principal sign-off
before implementation. The choice:

1. **Ship Option E** — accept that STATE.md becomes purely local; both
   B-002 stale-by-one and B-003 divergence go away.
2. **Ship Option A** — PreToolUse blocker; preserves commit-embedded STATE.md
   property; adds friction to compound `commit && push` workflows.
3. **Stay with the current workaround** — keep the separate-Bash-call
   discipline; close B-003 as "won't fix; documented workaround acceptable."

Director-seat lean: Option E. The current model's "feature" (commit-embedded
STATE.md) is already so leaky (stale-by-one + divergence) that the
informational value isn't worth the architectural cost.

---

## If Option E is chosen — implementation plan

```
# 1. Stop tracking STATE.md going forward
git rm --cached STATE.md
echo "" >> .gitignore
echo "# Auto-generated by .claude/hooks/update-state.sh — local only" >> .gitignore
echo "STATE.md" >> .gitignore

# 2. Simplify update-state.sh — remove ~half the script
#    - Drop: MARKER file logic + reflog gate + staged-set check
#    - Drop: git add STATE.md + git commit --amend lines
#    - Keep: HEAD_SHA / branch / pytest / smoke / mailbox-count extraction
#    - Keep: the heredoc that writes STATE.md
#    Net change: ~127 LoC → ~70 LoC

# 3. Update doc references
#    - CLAUDE.md "Hook script's stale-by-one" note → remove (no longer applies)
#    - docs/BACKLOG.md B-002 + B-003 → move to "Recently resolved by E"
#    - Any handoff docs that cite STATE.md as a commit artifact

# 4. Verify
#    - Make a test commit: STATE.md should NOT appear in git status as staged
#    - Compound `git commit && git push` should work cleanly
#    - Hook should still regenerate STATE.md on each Bash call
```

Estimated total: ~45 min execution + ~15 min testing across various
Bash-call scenarios (commit alone, push alone, compound, no-op Bash).

---

*Drafted for user-principal review. No implementation work has been done.
The BACKLOG.md B-003 row continues to track this; once the user picks a
direction, an implementation pass updates the row + ships the chosen
option.*
