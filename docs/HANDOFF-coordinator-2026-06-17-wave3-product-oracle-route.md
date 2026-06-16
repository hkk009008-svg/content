# Coordinator Handoff - Wave 3 Product-Oracle Route

Generated: `2026-06-16T17:02:18Z` (`2026-06-17T02:02:18+0900 KST`)
Repo: `/Users/hyungkoookkim/Content`

This is a narrow coordinator state-transfer handoff. Trust live git, mailbox,
gate, and filesystem state over this snapshot if they diverge.

## Refresh First

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 3
env -u GIT_INDEX_FILE git log --oneline -8
env -u GIT_INDEX_FILE git status --short
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 3
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once
```

Do not consume coordinator mail. Push, lock side effects, pod spend, and paid
API spend remain user-gated.

## What Landed

- Coordinator commit: `f7564d77 coord(route): reconcile wave3 checkpoint GO`.
- Files in that commit:
  - `docs/REMEDIATION-INVENTORY.md`
  - `coordination/mailbox/sent/2026-06-16T17-01-05Z-coordinator-to-all-coordination.md`
- The three Wave 3 checkpoint rows were transitioned to `verified`:
  - `ckpt-nan-json-token`
  - `ckpt-stage-notrestored`
  - `ckpt-sceneclips-dead`
- Evidence source: operator2 Lane V GO
  `coordination/mailbox/sent/2026-06-16T16-44-41Z-operator2-to-director2-verification-report.md`
  on `d613ca8e fix(checkpoint): close wave3 resume pins`.

## Gate And Smoke Truth

`env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py docs/REMEDIATION-INVENTORY.md`
returned:

```text
All anchors checked -- no drift.
```

`env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 3`
returned:

```text
Wave 3 gate: UNMET  counts={'verified': 3}
PRODUCT ORACLE BLOCKER: Wave 3 requires a committed logs/product-oracle-*.json artifact with artifact_kind=product-oracle, wave=3, finite arcface.arc_score, and finite lipsync.offset_frames; invalid artifacts: /Users/hyungkoookkim/Content/logs/product-oracle-wave2.json: wave is not 3
```

`env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` returned `OK`
with only the known historical `verify-addendum` advisory and R2
invisible-green warnings.

## Mailbox State

Latest coordinator route:

- `coordination/mailbox/sent/2026-06-16T17-01-05Z-coordinator-to-all-coordination.md`

`env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once`
after `f7564d77` reported:

```text
latest coordinator broadcast: 2026-06-16T17-01-05Z-coordinator-to-all-coordination.md
receipt split: consumed=0 unread=4 unknown=0
director unread=1
director2 unread=1
operator unread=1
operator2 unread=1
```

All four seats must read the route; the next seat-owned action is for
`director`.

## Current Route Board

- `director`: produce a committed `logs/product-oracle-wave3.json` only if it
  can be measured from already-available local source media/reference inputs
  without pod/API spend. If fresh generation, pod runtime, paid API spend, or
  missing source inputs are required, report the exact blocker instead of
  spending.
- `operator`: stand by to verify a landed Wave 3 product-oracle artifact.
- `director2`: checkpoint mini-batch is complete and GO'd; no current action.
- `operator2`: checkpoint Lane V is complete; no current action.

## Dirty Tree Caveat

The shared tree still has non-coordinator seat artifacts that this coordinator
did not consume, stage, revert, or commit:

```text
M  coordination/mailbox/seen/director2.txt
AM docs/HANDOFF-director2-2026-06-17-checkpoint-wave3-inventory-verified.md
?? docs/HANDOFF-director-2026-06-17-checkpoint-go-reconcile-standby.md
```

Those paths appear seat-owned and should be handled by the owning live seat.

## Exact Next Trigger

```text
continue as director
```

Director should read the `2026-06-16T17-01-05Z` coordinator route and either
land a valid Wave 3 product-oracle artifact from existing local inputs or
report the missing input/spend authorization blocker.
