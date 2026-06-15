# HANDOFF - operator2 - 2026-06-16 lipsync precheck standby

READ FIRST AS `operator2`. Trust git, live mailbox state, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Handoff

Timestamp: `2026-06-15T20:11:20Z` (`2026-06-16T05:11:20+0900`
Asia/Seoul).

Current HEAD at evidence refresh:

```text
a43f6e40 coord(status): director no-op after reconcile route
f3754d7a coord(status): operator2 standby after reconcile route
5a7ef77b coord(cursor): operator consume reconcile no-op status
aa371016 coord(status): operator no-op after reconcile route
940e26d7 coord(cursor): operator2 consume coordinator route
7743da64 coord(reconcile): verify checkpoint rows
f2044ec2 coord(cursor): operator consume self status mail
3e5159a9 coord(status): operator standby after checkpoint mail
```

Branch relation from live `operator2` status:

```text
branch main
a43f6e40 coord(status): director no-op after reconcile route
vs origin/main: 16 ahead, 0 behind
```

Operator2 live mailbox before this handoff:

```text
cursor: 2026-06-15T19:59:27Z
UNREAD: 3
- 2026-06-15T20-01-25Z-director-to-all-status.md
- 2026-06-15T20-04-00Z-operator-to-all-status.md
- 2026-06-15T20-04-46Z-operator2-to-all-status.md
```

All three unread events were read. This handoff consumes `operator2`
through `2026-06-15T20:04:46Z` in the same commit as this file. No new
verification verdict is sent by this handoff.

## Current Operator2 Decision

Operator2 is standby, not actively verifying.

- Checkpoint Lane V is complete and reconciled:
  - `coordination/mailbox/sent/2026-06-15T19-46-45Z-operator2-to-all-verification-report.md`
  - `7743da64 coord(reconcile): verify checkpoint rows`
- Latest committed mailbox route still assigns operator2 to Pair-B Lane V
  standby for director2's next no-lock row:
  `lipsync-precheck-cascade-gap`.
- No committed director2 implementation commit or verify-request exists for
  `lipsync-precheck-cascade-gap` at this handoff.
- Do not re-run checkpoint Lane V unless a real drift or amended verify request
  appears.

Next operator2 action: after director2 commits the scoped implementation and
sends a verify-request, run Lane V against the exact commit(s), files, tests,
and residual risks named in that request, then send GO/NITS/FAIL as a mailbox
`verification-report`.

## Live Seat Board

- `director`: committed no-op at `a43f6e40`; active monitor for Pair-A,
  product-oracle identity/ArcFace review, Tier-A co-signs, or explicit Pair-A
  work.
- `operator`: committed no-op/cursor updates through `5a7ef77b`; Pair-A
  verifier standby. The old untracked operator handoff draft remains unrelated
  residue.
- `director2`: currently owns `lipsync-precheck-cascade-gap` WIP. The shared
  index has staged implementation/doc/test changes, but there is no committed
  fix and no operator2 verify-request yet.
- `operator2`: standby for the eventual `director2` verify-request.

## Director2 WIP Caveat

Current staged scope belongs to `director2`, not `operator2`:

```text
M  cinema/shots/controller.py
M  coordination/mailbox/seen/director2.txt
A  docs/BRIEF-director2-2026-06-16-lipsync-precheck-cascade-gap.md
M  docs/PROGRAM-MANUAL.md
M  docs/REMEDIATION-INVENTORY.md
M  tests/unit/test_budget_pre_spend_gate.py
M  tests/unit/test_dialogue_routing.py
M  tests/unit/test_discovery_cost_xfail.py
M  tests/unit/test_f1b_dialogue_lipsync.py
```

There is also untracked non-operator2 residue:

```text
?? docs/HANDOFF-director2-2026-06-16-lipsync-precheck-wip.md
?? docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
```

Important distinction: `HEAD:docs/REMEDIATION-INVENTORY.md` still has
`lipsync-precheck-cascade-gap` as `open` / `test-infeasible`; the staged
director2 inventory change marks it `fixed` pending operator2 GO. Do not treat
that row as fixed or verified until the director2 commit lands and operator2
GO exists.

## Gate / Smoke / Locks

Smoke:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
WARNING: coordination ADVISORY [unknown_kind] mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md - kind 'verify-addendum' not in KNOWN_KINDS
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Wave 2 gate:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 23, 'open': 6, 'fixed': 1}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

Locks and product-oracle artifact:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

No push, lock claim, pod spend, paid API spend, production code edit, inventory
edit, or verification verdict was performed by operator2 during this handoff.

## Resume Checklist

1. Refresh live state:
   `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator2 --wave 2`
   and `env -u GIT_INDEX_FILE git log --oneline -5`.
2. Read any unread mailbox bodies before deciding whether Lane V is active.
3. If director2 has not committed and sent a verify-request, remain standby.
4. If a verify-request exists for `lipsync-precheck-cascade-gap`, read the
   landed diff yourself, run the named tests plus any necessary focused checks,
   and issue GO/NITS/FAIL via mailbox artifact.
5. Preserve the staged director2 WIP and unrelated operator handoff draft unless
   the user explicitly changes ownership.
