# Director Handoff - Reconcile Route, Active Monitor

READ FIRST AS `director`. Trust git, live mailbox state, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Handoff

Timestamp: `2026-06-15T20:11:10Z` (`2026-06-16T05:11:10+0900` Asia/Seoul).

Seat: `director`

Current HEAD:

```text
fd49f9bd docs(handoff): coordinator lipsync precheck wip
c2338cb0 docs(handoff): operator reconcile route standby
130a5e23 docs(handoff): operator2 lipsync standby
a43f6e40 coord(status): director no-op after reconcile route
f3754d7a coord(status): operator2 standby after reconcile route
```

Branch relation from live status:

```text
main vs origin/main: 20 ahead, 0 behind
```

## Director Mail

Fresh director status before writing this handoff:

```text
cursor: 2026-06-15T20:04:46Z
UNREAD: 0
```

No director cursor was consumed for this handoff. The last director action is
already committed:

```text
a43f6e40 coord(status): director no-op after reconcile route
```

That status read the coordinator reconciliation route and later operator /
operator2 no-op events through `2026-06-15T20:04:46Z`, found no
director-owned trigger, and advanced the director cursor to that timestamp.

## Current Route

Latest coordinator route:

```text
coordination/mailbox/sent/2026-06-15T19-59-27Z-coordinator-to-all-coordination.md
```

Binding director task from that route:

- remain active monitor for product-oracle identity/ArcFace review, Tier-A
  co-signs, explicit Pair-A work, or coordinator-directed support;
- do not duplicate Pair-B checkpoint verification;
- return no-op evidence if no eligible trigger exists.

Current director decision remains no-op / active monitor:

- no `logs/product-oracle-*.json` artifact exists;
- no Tier-A co-sign request is pending for director;
- no explicit Pair-A implementation or verify target is routed to director;
- no lock is held beyond `coordination/locks/.gitkeep`;
- push, lock-claim/push side effects, pod spend, and paid API spend remain
  unauthorized.

## Seat Board

Fresh live seat snapshots before writing this handoff:

```text
director:  cursor 2026-06-15T20:04:46Z, unread 0, online
director2: cursor 2026-06-15T20:04:46Z, unread 0, online
operator:  cursor 2026-06-15T20:04:00Z, unread 1, online
operator2: cursor 2026-06-15T20:04:46Z, unread 0, online
```

Interpretation:

- `director`: no-op / active monitor only.
- `director2`: active Pair-B implementation lane for the no-lock
  `lipsync-precheck-cascade-gap` route.
- `operator`: Pair-A verifier standby; still has operator2 no-op mail unread.
- `operator2`: Pair-B Lane V standby for a future director2 verify request; its
  standby handoff is committed at `130a5e23`.

## Director2 WIP Observed

Shared index/worktree contains active director2 WIP. Do not revert or broad-stage
it from the director seat.

Director2 staged paths observed:

```text
M	cinema/shots/controller.py
M	coordination/mailbox/seen/director2.txt
A	docs/BRIEF-director2-2026-06-16-lipsync-precheck-cascade-gap.md
A	docs/HANDOFF-director2-2026-06-16-lipsync-precheck-wip.md
M	docs/PROGRAM-MANUAL.md
M	docs/REMEDIATION-INVENTORY.md
M	tests/unit/test_budget_pre_spend_gate.py
M	tests/unit/test_dialogue_routing.py
M	tests/unit/test_discovery_cost_xfail.py
M	tests/unit/test_f1b_dialogue_lipsync.py
```

Untracked residue also remains:

```text
docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
```

The visible director2 brief says `lipsync-precheck-cascade-gap` is lane-only,
no lock, scoped to `cinema/shots/controller.py` plus focused tests, and should
be verified by operator2 only after a committed fix and explicit verify request.

The visible director2 handoff says the user interrupted with `handoff` while the
implementation was staged but uncommitted; no operator2 verify-request has been
sent. The visible current operator handoff says operator is Pair-A standby and
should not verify director2's Pair-B WIP unless an appropriate committed fix and
verify-request land. The coordinator handoff is now committed at `fd49f9bd` and
says the same board shape: checkpoint reconciliation is done, director2 owns the
staged `lipsync-precheck-cascade-gap` WIP, and operator2 waits for a committed
fix plus verify-request before Lane V. Operator and operator2 standby handoffs
are committed at `c2338cb0` and `130a5e23`.

## Gate / Verification Snapshot

Smoke:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Known smoke advisories:

- `verify-addendum` mailbox kind is not in `KNOWN_KINDS`;
- `tests/unit/test_discovery_identity_xfail.py:193` has a `skip()` in a pin
  file;
- `tests/unit/test_lane_silent_gate_siblings_xfail.py:64` uses
  `importorskip('cv2')`, and the dependency is present.

Wave 2 gate:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 23, 'open': 6, 'fixed': 1}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

Remaining gate failures are still product-oracle, HTTP/web-server, and
postprocess/lip-sync related. The checkpoint rows were reconciled to verified in
`7743da64`.

Locks and product-oracle artifact:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

## Next Director

1. Start with:
   `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2`
   and `env -u GIT_INDEX_FILE git log --oneline -5`.
2. Read any new director/all mail before making a routing, handoff, or status
   claim. Consume only if intentionally advancing live director state.
3. Do not touch director2's staged `lipsync-precheck-cascade-gap` WIP.
4. Remain active for product-oracle identity/ArcFace review, Tier-A co-signs,
   explicit Pair-A work, or coordinator-directed support.
5. Do not claim locks, push, use pods, or trigger paid APIs without explicit
   user-principal authorization.
