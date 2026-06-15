# Director Handoff - Pair-B Lane V Monitor

READ FIRST AS `director`. Trust git, live mailbox state, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Handoff

Timestamp: `2026-06-15T21:55:30Z` (`2026-06-16T06:55:30+0900`
Asia/Seoul).

Seat: `director`

Current HEAD:

```text
af993382 docs(handoff): refresh operator2 Lane V handoff
306c680e docs(handoff): director2 lipsync Lane V pending
69848473 docs(handoff): refresh operator pair-b lanev standby
73102c03 coord(status): operator standby after pair-b route
5641731c coord(verify): request lipsync precheck Lane V
349dac78 fix(money): precheck mandatory lipsync spend
3342b746 docs(handoff): refresh director reconcile handoff
fd49f9bd docs(handoff): coordinator lipsync precheck wip
```

Branch relation from live director status:

```text
main vs origin/main: 27 ahead, 0 behind
```

## Director Mail

Live director status before mailbox consumption:

```text
cursor: 2026-06-15T20:04:46Z
UNREAD: 1
- 2026-06-15T21-34-51Z-operator-to-all-status.md
```

I read the unread operator status. It reports Pair-A standby only and says the
new landed fix is Pair-B, explicitly routed to `operator2`:

```text
349dac78 fix(money): precheck mandatory lipsync spend
5641731c coord(verify): request lipsync precheck Lane V
```

Director cursor was advanced to the operator status event:

```text
cursor: 2026-06-15T21:34:51Z
UNREAD: 0
```

Operational note: the first `coordination/bin/consume-events director` attempt
hit `.git/index-codex-director.lock` permission while still updating the working
cursor file; the approved rerun reported:

```text
cursor director: already at 2026-06-15T21:34:51Z (no-op)
```

The handoff commit should include only the director cursor update and this
handoff file. The director seat index had no cached staged scope after the
rerun.

## Current Route

The active Pair-B implementation route has moved forward:

- implementation commit: `349dac78 fix(money): precheck mandatory lipsync spend`
- verify-request commit: `5641731c coord(verify): request lipsync precheck Lane V`
- operator handoff commit:
  `69848473 docs(handoff): refresh operator pair-b lanev standby`
- director2 handoff commit:
  `306c680e docs(handoff): director2 lipsync Lane V pending`
- operator2 handoff commit:
  `af993382 docs(handoff): refresh operator2 Lane V handoff`
- verify request:
  `coordination/mailbox/sent/2026-06-15T21-29-51Z-director2-to-operator2-verify-request.md`

`operator2` owns Lane V for `lipsync-precheck-cascade-gap`. Director must not
duplicate or preempt this verification. The operator handoff at `69848473`
confirms the Pair-A operator is standby and should not take the Pair-B Lane V.
The operator2 handoff at `af993382` confirms operator2 did not consume mail or
start Lane V during that handoff; the verify request remains pending for the
next operator2 turn.

Current director decision remains no-op / active monitor:

- no Pair-A implementation target is routed to director;
- no Pair-A Lane V target is routed to operator/director;
- no Tier-A co-sign request is pending for director;
- no product-oracle artifact exists under `logs/product-oracle-*.json`;
- no lock is held beyond `coordination/locks/.gitkeep`;
- push, lock-claim/push side effects, pod spend, and paid API spend remain
  unauthorized.

## Seat Board

Fresh live seat snapshots before writing this handoff:

```text
director:  cursor 2026-06-15T21:34:51Z, unread 0, online
director2: cursor 2026-06-15T21:34:51Z, unread 0, online
operator:  cursor 2026-06-15T21:34:51Z, unread 0, online
operator2: cursor 2026-06-15T20:04:46Z, unread 2, online
```

Interpretation:

- `director`: no-op / active monitor for Pair-A, product-oracle identity/ArcFace
  review, Tier-A co-signs, or coordinator-directed support.
- `director2`: Pair-B implementation commit and verify-request are landed;
  director2 cursor is current after its pending-Lane-V handoff.
- `operator`: Pair-A verifier standby; no active Pair-A target.
- `operator2`: Pair-B Lane V target is active; unread mail includes the
  director2 verify-request for `349dac78` and operator standby status.

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
$ .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 23, 'open': 6, 'fixed': 1}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

The fixed row is `lipsync-precheck-cascade-gap`, pending operator2 Lane V GO.
Remaining open rows include `lipsync-veto` and the HTTP/web-server cluster.

Locks and product-oracle artifact:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

## Workspace Hygiene

Shared worktree residue exists and is not director-owned:

```text
M  .agents/skills/four-seat-protocol/SKILL.md
M  docs/protocol/codex/continuation.md
M  scripts/continuation_readiness.py
M  tests/unit/test_codex_protocol_artifacts.py
M  tests/unit/test_continuation_readiness.py
?? docs/HANDOFF-coordinator-2026-06-16-automated-handoff-tool-transplant.md
?? docs/HANDOFF-director2-2026-06-16-lipsync-precheck-wip.md
?? docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
?? scripts/draft_handoff.py
?? tests/unit/test_draft_handoff.py
```

Do not stage, delete, or "clean up" those files from the director seat without
an explicit ownership change.

## Next Director

1. Start with:
   `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2`
   and `env -u GIT_INDEX_FILE git log --oneline -5`.
2. Read any new director/all mail before making a routing, handoff, or status
   claim. Consume only if intentionally advancing live director state.
3. Do not verify `349dac78`; it is routed to `operator2`.
4. Stay available for product-oracle identity/ArcFace review, Tier-A co-signs,
   explicit Pair-A work, or coordinator-directed support.
5. Do not claim locks, push, use pods, or trigger paid APIs without explicit
   user-principal authorization.
