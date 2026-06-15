# HANDOFF - director2 - 2026-06-16 lipsync precheck reconciled

READ FIRST AS `director2`. Trust git, live mailbox state, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Handoff

Timestamp: `2026-06-15T22:18:46Z` (`2026-06-16T07:18:46+0900`
Asia/Seoul).

Current HEAD at evidence refresh:

```text
15c4ead4 coord(reconcile): verify lipsync precheck row
8c4ff795 coord(verify): operator2 go lipsync precheck
79c5af5b docs(handoff): refresh director pair-b lanev monitor
af993382 docs(handoff): refresh operator2 Lane V handoff
306c680e docs(handoff): director2 lipsync Lane V pending
69848473 docs(handoff): refresh operator pair-b lanev standby
73102c03 coord(status): operator standby after pair-b route
5641731c coord(verify): request lipsync precheck Lane V
349dac78 fix(money): precheck mandatory lipsync spend
3342b746 docs(handoff): refresh director reconcile handoff
fd49f9bd docs(handoff): coordinator lipsync precheck wip
1c63cd56 docs(handoff): director reconcile route handoff
```

Branch relation from `seat_status.py director2 --wave 2`:

```text
branch main
15c4ead4 coord(reconcile): verify lipsync precheck row
vs origin/main: 9 ahead, 8 behind
```

Director2 mailbox before processing this handoff:

```text
cursor: 2026-06-15T21:34:51Z
UNREAD: 2
  - 2026-06-15T22-10-55Z-operator2-to-all-verification-report.md
  - 2026-06-15T22-14-55Z-coordinator-to-all-coordination.md
```

Both unread bodies were read. Director2 cursor was then advanced:

```text
$ coordination/bin/consume-events director2
cursor director2: 2026-06-15T21:34:51Z -> 2026-06-15T22:14:55Z; unread now: 0

$ env -u GIT_INDEX_FILE git diff --cached --name-status
M	coordination/mailbox/seen/director2.txt
```

## What Changed Since The Prior Director2 Handoff

The Pair-B no-lock row `lipsync-precheck-cascade-gap` is now verified.

Durable chain:

- implementation: `349dac78 fix(money): precheck mandatory lipsync spend`
- director2 verify request:
  `coordination/mailbox/sent/2026-06-15T21-29-51Z-director2-to-operator2-verify-request.md`
- operator2 GO commit: `8c4ff795 coord(verify): operator2 go lipsync precheck`
- coordinator reconcile commit:
  `15c4ead4 coord(reconcile): verify lipsync precheck row`

The coordinator moved `lipsync-precheck-cascade-gap` in
`docs/REMEDIATION-INVENTORY.md` from `fixed` to `verified`, with operator2 GO
as verifier.

## Current Seat Board

Fresh seat snapshots at this handoff:

```text
director2: cursor 2026-06-15T21:34:51Z before consume, unread 2, online
director:  cursor 2026-06-15T21:34:51Z, unread 2, online
operator:  cursor 2026-06-15T21:34:51Z, unread 2, online
operator2: cursor 2026-06-15T22:10:55Z, unread 1, online
```

After this handoff consumes director2 mail, `director2` should be at cursor
`2026-06-15T22:14:55Z` with unread `0`.

Interpretation:

- `director2`: no no-lock Pair-B implementation row remains routed.
- `operator2`: Lane V for `349dac78` is complete; only the coordinator
  reconciliation event may remain unread for that seat.
- `director` and `operator`: still need to process the all-hands operator2 GO
  and coordinator reconciliation if they continue.
- All seats were ONLINE during the refresh.

## Gate / Locks / Smoke

Wave 2 remains open:

```text
$ .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 24, 'open': 6}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

Remaining blockers are outside the now-verified lipsync precheck row:

- missing committed `logs/product-oracle-*.json` artifact for Wave 2;
- `lipsync-veto`, which is Pair-B but cross-cutting and lock/push-gated via
  `W2-auto_approve.py.lock`;
- HTTP/web-server discovery rows, cross-cutting and lock/push-gated via
  `W2-web_server.py.lock`.

Local locks:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep
```

Product-oracle artifact check:

```text
$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

Smoke:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
WARNING: coordination ADVISORY [unknown_kind] mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md - kind 'verify-addendum' not in KNOWN_KINDS
R1 xfail-strictness ....... PASS  12 xfail markers; all strict=True+reason
R2 invisible-green ........ WARN
R3 gate-executes-pins ..... PASS  wave_gate_check.py executes the pins
R4 ci-runs-runxfail ....... PASS  a CI workflow runs --runxfail
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

## Workspace Hygiene

This director2 handoff should commit only:

```text
M  coordination/mailbox/seen/director2.txt
A  docs/HANDOFF-director2-2026-06-16-lipsync-precheck-reconciled.md
```

Unrelated shared-tree residue observed and intentionally left untouched:

```text
 M .agents/skills/four-seat-protocol/SKILL.md
 M docs/protocol/codex/continuation.md
 M scripts/continuation_readiness.py
 M tests/unit/test_codex_protocol_artifacts.py
 M tests/unit/test_continuation_readiness.py
?? docs/HANDOFF-coordinator-2026-06-16-automated-handoff-tool-transplant.md
?? docs/HANDOFF-director2-2026-06-16-lipsync-precheck-wip.md
?? docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
?? scripts/draft_handoff.py
?? tests/unit/test_draft_handoff.py
```

Do not stage, delete, or normalize those files from `director2` without an
explicit ownership change.

## Next Director2

1. Start with:
   `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 2`
   and `env -u GIT_INDEX_FILE git log --oneline -5`.
2. If still at `15c4ead4` plus this handoff commit, `director2` should have no
   no-lock Pair-B row to continue.
3. Do not start `lipsync-veto` or the HTTP rows without explicit
   lock/push authorization; those remaining Pair-B rows are cross-cutting.
4. Product-oracle work still needs coordinator/user routing and a committed
   `logs/product-oracle-*.json` artifact before Wave 2 can close.
5. Preserve the existing unrelated protocol-tooling worktree residue unless
   ownership is explicitly reassigned.
