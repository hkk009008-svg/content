# Operator2 handoff - standby after Codex protocol-rule codification

**Seat:** `operator2`  
**When:** 2026-06-16 KST  
**HEAD:** `9b56d399 docs(handoff): director protocol codified`  
**Branch state:** `main` is `36 ahead, 0 behind` vs `origin/main`

## Mailbox First

Live operator2 mailbox was read before this handoff:

```text
$ CODEX_SEAT=operator2 GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-codex-operator2" .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator2 --wave 2
cursor: 2026-06-15T18:58:49Z
UNREAD: 0
```

No operator2 mailbox consumption was needed in this handoff turn.

## Current Assignment

The latest binding route remains
`coordination/mailbox/sent/2026-06-15T18-58-49Z-coordinator-to-all-coordination.md`.

Operator2 task from that route:

- stand by for Pair-B Lane V on director2's next checkpoint-cluster repair;
- verify only after director2 lands a scoped commit and sends a verify-request;
- check that any repair does not mask remaining deferred checkpoint pins or the
  product-oracle blocker;
- if no committed fix/verify-request exists, return no-op evidence rather than
  inventing Lane V.

No new Pair-B implementation commit or verify-request is currently available for
operator2.

## Seat Board

Current live recompute:

- `director`: unread `0`; standby for Pair-A / cross-lane review triggers.
- `operator`: unread `3`; should consume stale all-scope route/GO mail before
  deciding Pair-A standby/no-op.
- `director2`: unread `0`; owns the next Pair-B implementation lane: the
  lock-free checkpoint cluster (`ckpt-sceneidx-dead`, `ckpt-shotaudio-loss`,
  `ckpt-projectid-nocrosscheck`).
- `operator2`: unread `0`; Pair-B Lane V standby, no current target.

## Gate / Locks / Spend

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected — every relied-on green is backed by execution.
OK

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 20, 'open': 10}
PRODUCT ORACLE BLOCKER: missing committed logs/product-oracle-*.json artifact
PYTEST tail: 15 failed, 57 passed

$ env -u GIT_INDEX_FILE find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ env -u GIT_INDEX_FILE find logs -maxdepth 1 -name 'product-oracle-*.json' -print | sort
# no output
```

No lock is held. Product-oracle artifact is still absent. Push, pod spend, paid
API spend, and lock-claim side effects remain unauthorized unless the
user-principal explicitly authorizes them.

## Recent Commits

```text
$ env -u GIT_INDEX_FILE git log --oneline -8
9b56d399 docs(handoff): director protocol codified
4d077c9c coord(protocol): document codex mailbox index guard
fa11b793 coord(protocol): clarify mail consumption rule
ab8beb4c coord(protocol): codify codex live rules
e6205050 coord(route): notify wave2 seat tasks
8da10dc2 coord(handoff): verify mode-b budget gate
38e892e3 coord(verify): operator2 go mode-b budget gate
9128d90d docs(handoff): operator route mode-b lanev
```

The newest commits are protocol/handoff artifacts and do not create a new
operator2 Lane V target.

## Worktree / Index Caveat

The shared worktree is dirty with unrelated WIP and stale index-looking
`D/??` mailbox pairs. Preserve it. Do not broad-stage. For operator2 cursor-only
work, refresh `index-codex-operator2` to `HEAD`, stage only
`coordination/mailbox/seen/operator2.txt`, and confirm the staged scope is
exactly that cursor file.

Current operator2 seat-local index still has only the cursor staged from the
prior consume:

```text
$ CODEX_SEAT=operator2 GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-codex-operator2" git diff --cached --name-status
M	coordination/mailbox/seen/operator2.txt
```

## Next Operator2 Action

Stay idle/standby until one of these arrives:

- director2 sends a verify-request for the checkpoint-cluster fix;
- a coordinator route changes operator2's task;
- product-oracle evidence lands and a Lane V / review-support request names
  operator2.

Then re-run `seat_status.py operator2 --wave 2`, read any unread mail bodies,
consume intentionally if needed, read the actual diff, and issue the binding
mailbox `verification-report` only after executed evidence.
