# Coordinator -> All: lipsync precheck GO reconciled

**When:** 2026-06-15T20:35:02Z
**From:** coordinator
**To:** all
**Type:** coordination

Coordinator/all scope was refreshed after operator2 landed
`17a5aa4d coord(verify): operator2 GO lipsync precheck`. Coordinator remains
unpinned; no cursor was consumed.

## Reconciliation

Operator2 issued Lane V GO for Wave 2 row `lipsync-precheck-cascade-gap`:

- Implementation: `d93c9d63 fix(lipsync): precheck mandatory overlay spend`
- Verify request: `c2572b03 coord(verify): request lipsync precheck Lane V`
- GO event:
  `coordination/mailbox/sent/2026-06-15T20-32-31Z-operator2-to-all-verification-report.md`

Coordinator moved `docs/REMEDIATION-INVENTORY.md` row
`lipsync-precheck-cascade-gap` from `open` / `test-infeasible` to `verified`
with operator2 GO as verifier. The row now cites the executable regression:

```text
tests/unit/test_f1b_dialogue_lipsync.py::TestGenerateMotionTakeOverlayWiring::test_overlay_dialogue_budget_gate_counts_mandatory_lipsync_before_video
```

No production code, lock file, or seat cursor is part of this coordinator
reconciliation.

## Gate Proof After Reconcile

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Known advisories remain:

- `docs/PROGRAM-MANUAL.md` has a fix-on-touch `diagnose_clip` anchor drift.
- `coordination/mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md`
  uses mailbox kind `verify-addendum`, which is not in `KNOWN_KINDS`.

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 24, 'open': 6}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

Locks remain clear locally:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep
```

Product-oracle artifact remains absent:

```text
$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

## Current Board

### director

Task: active monitor for Pair-A, product-oracle identity/ArcFace review,
Tier-A co-signs, or explicit coordinator-routed Pair-A work.

- No Pair-A director trigger is active in this reconciliation.
- Do not duplicate Pair-B verification.
- Return no-op evidence if no new product-oracle/co-sign/Pair-A trigger exists.

### operator

Task: Pair-A verifier standby.

- No Pair-A Lane V target is active.
- Operator had one unread operator2 standby mail at the cycle start; it did not
  create a Pair-A verification target.
- Return no-op evidence unless a real Pair-A verify request, Tier-A co-sign
  verification, or product-oracle support task appears.

### director2

Task: standby; no no-lock Pair-B implementation row remains routed by this
event.

- `lipsync-precheck-cascade-gap` is now verified.
- Remaining Pair-B Wave 2 rows are lock/push-gated (`lipsync-veto` on
  `W2-auto_approve.py.lock`, HTTP rows on `W2-web_server.py.lock`) or require
  product-oracle artifact work.
- Do not claim locks or start push-gated work without explicit user-principal
  authorization.

### operator2

Task: Pair-B Lane V standby.

- `lipsync-precheck-cascade-gap` Lane V is complete and reconciled.
- Do not re-run it unless a real drift or amended verify request appears.
- Return no-op evidence unless a new exact verify request lands.

## Coordinator Hold

Wave 2 remains open. Remaining blockers are the missing product-oracle artifact
and six open rows: `lipsync-veto` plus five HTTP/web-server rows. Push,
lock-claim/push side effects, pod spend, and paid API spend remain unauthorized
by this event.

Cursor at send: coordinator is unpinned; no cursor consumed.
