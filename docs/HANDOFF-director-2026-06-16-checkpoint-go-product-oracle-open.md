# Director Handoff - Checkpoint GO, Product Oracle Open

READ FIRST AS director. Trust git, live mailbox state, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Wrap

Timestamp: `2026-06-15T19:49:12Z`
(`2026-06-16T04:49:12+0900` Asia/Seoul).

Seat: `director`

HEAD at final evidence capture:

```text
da538a90 docs(handoff): operator2 checkpoint go handoff
c3811d52 coord(verify): operator2 checkpoint GO
dcd5de19 coord(verify): add checkpoint docs addendum
578c064b docs(checkpoint): sync resume repair inventory
d6228bbc coord(verify): request checkpoint cluster Lane V
```

Branch state from director status:

```text
main vs origin/main: 4 ahead, 0 behind
```

## Director Mail State

Director mail is current:

```text
seat_status.py director --wave 2
cursor before consuming latest GO report: 2026-06-15T19:34:17Z
UNREAD before consume: 1
unread file: 2026-06-15T19-46-45Z-operator2-to-all-verification-report.md
```

Important standing rule from the user-principal: active seats should actively
monitor mail received at all times, not just at start/end. For this handoff,
director already consumed standby/status mail through
`2026-06-15T19:34:17Z` in commit:

```text
4e81bf49 coord(cursor): director consume standby mail
```

After reading the operator2 GO report, director consumed through
`2026-06-15T19:46:45Z`; that cursor update should be part of this handoff commit.

## Current Board

| seat | unread/cursor | state |
|---|---:|---|
| director | `0` after consume, cursor `2026-06-15T19:46:45Z` | active monitor only |
| director2 | `1`, cursor `2026-06-15T19:34:17Z` | has operator2 GO report unread |
| operator | `3`, cursor `2026-06-15T19:29:46Z` | Pair-A standby; has stale all-scope status mail |
| operator2 | `0`, cursor `2026-06-15T19:46:45Z` | issued checkpoint Lane V GO and handoff |

All peer heartbeats were ONLINE in the final seat refresh.

## What Just Landed

Pair-B checkpoint cluster moved from implementation through Lane V:

- `5fa2695e fix(checkpoint): preserve routed resume state`
  - Production/test/doc files include `cinema/checkpoint.py`,
    `cinema_pipeline.py`, `tests/unit/test_discovery_checkpoint_xfail.py`,
    `ARCHITECTURE.md`, `docs/PROGRAM-MANUAL.md`, and
    `docs/BRIEF-director2-2026-06-16-checkpoint-cluster.md`.
- `d6228bbc coord(verify): request checkpoint cluster Lane V`
  - Adds direct `director2 -> operator2` verify request for rows
    `ckpt-sceneidx-dead`, `ckpt-shotaudio-loss`, and
    `ckpt-projectid-nocrosscheck`.
- `578c064b docs(checkpoint): sync resume repair inventory`
  - Lands the previously dirty inventory/manual sync for the checkpoint repair.
- `dcd5de19 coord(verify): add checkpoint docs addendum`
  - Adds direct verify addendum asking operator2 to include `578c064b` in Lane V.
- `c3811d52 coord(verify): operator2 checkpoint GO`
  - Adds operator2 GO verification report for `5fa2695e`, `578c064b`, and
    `dcd5de19`.
- `da538a90 docs(handoff): operator2 checkpoint go handoff`
  - Adds operator2's post-GO handoff and advances operator2 cursor through its
    own all-scope GO report.

Director read the direct verify-request/addendum for handoff awareness, then read
the all-scope operator2 GO report. The GO is binding operator evidence; director
must not re-verify or replace it.

## Gate State

Wave 2 remains UNMET even after operator2 GO; the three checkpoint rows still
appear as `fixed` in the gate until coordinator/inventory reconciliation lands:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 20, 'open': 7, 'fixed': 3}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

Product-oracle artifact remains absent:

```text
$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

Locks:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep
```

Smoke:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
WARNING: coordination ADVISORY [unknown_kind] mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md - kind 'verify-addendum' not in KNOWN_KINDS
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

The advisory is about mailbox kind taxonomy for the addendum, not a failed smoke.

Operator2 GO report:

```text
$ nl -ba coordination/mailbox/sent/2026-06-15T19-46-45Z-operator2-to-all-verification-report.md
VERDICT: GO
Commits reviewed: 5fa2695e, d6228bbc, 578c064b, dcd5de19
Focused checkpoint regressions: 3 passed in 0.02s
Full checkpoint --runxfail file: 3 failed, 3 passed in 1.64s
Cross-controller/spent-usd suite: 41 passed in 2.50s
Wave 2 gate remained UNMET counts={'verified': 20, 'open': 7, 'fixed': 3}
```

## Working Tree / Index Warning

Ordinary shared status before writing this handoff showed the director cursor
consume plus untracked peer handoff drafts:

```text
$ env -u GIT_INDEX_FILE git diff --cached --name-status
# no output

$ env -u GIT_INDEX_FILE git status --short
 M coordination/mailbox/seen/director.txt
M  coordination/mailbox/seen/director2.txt
MM coordination/mailbox/seen/operator2.txt
D  docs/HANDOFF-operator2-2026-06-16-checkpoint-go-wait-reconcile.md
?? docs/HANDOFF-coordinator-2026-06-16-checkpoint-go-pending-reconcile.md
?? docs/HANDOFF-director-2026-06-16-checkpoint-go-product-oracle-open.md
?? docs/HANDOFF-director2-2026-06-16-checkpoint-go-product-oracle-open.md
?? docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
?? docs/HANDOFF-operator2-2026-06-16-checkpoint-go-wait-reconcile.md
```

Commit only `coordination/mailbox/seen/director.txt` and this director handoff
from this seat. Do not fold peer handoff drafts into the director commit. Also
note that peer/coordinator handoff drafts are unowned by this director handoff;
trust git and live mailbox state over those drafts if they diverge.

## Next Director Action

On resume as director:

1. Run `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2`.
2. Read any new director/all mail immediately; consume only after reading if
   operating as the live director seat.
3. Do not duplicate Pair-B checkpoint verification. Operator2 already issued GO
   for `5fa2695e` plus `578c064b`/`dcd5de19`.
4. Stay active for director-owned triggers only:
   product-oracle identity/ArcFace review, Tier-A co-sign request, explicit
   Pair-A work, or coordinator-directed support.
5. Next protocol action is coordinator/inventory reconciliation of the operator2
   GO if the user asks for coordinator/cycle work; director should not silently
   mutate inventory from this handoff.
6. No push, lock-claim, pod spend, or paid API spend is authorized by this
   handoff.
