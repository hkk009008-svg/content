# Director2 Handoff - Wave 3 Product-Oracle Standby

Generated: `2026-06-16T17:09:55Z` (`2026-06-17T02:09:55+0900` KST)
Repo: `/Users/hyungkoookkim/Content`
Seat: `director2`

Trust live git, mailbox, gate, and filesystem state over this snapshot if they
diverge.

## Refresh First

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 3
env -u GIT_INDEX_FILE git log --oneline -8
env -u GIT_INDEX_FILE git status --short --branch
```

## Current State

HEAD at handoff time:

```text
4bc1eb86 docs(handoff): director wave3 product oracle pending
```

Branch state from live `seat_status.py`:

```text
main is 18 ahead, 0 behind origin/main
director2 unread: 0
director2 cursor: 2026-06-16T17:01:05Z
Wave 3 gate: MET counts={'verified': 3}
PRODUCT ORACLE: logs/product-oracle-wave3.json
```

`scripts/ci_smoke.py` was run during this refresh and reported `OK`, with only
the known historical `verify-addendum` mailbox-kind advisory and R2
invisible-green warnings.

No director2 mailbox was consumed during this handoff refresh.

## What Changed Since The Prior Director2 Handoff

The previous same-seat handoff was
`docs/HANDOFF-director2-2026-06-17-checkpoint-wave3-inventory-verified.md`.
It correctly left director2 on standby and routed the remaining Wave 3
product-oracle blocker to `director`.

Since then:

- `012d28d0 fix(product-oracle): add wave3 artifact` committed
  `logs/product-oracle-wave3.json`, a bootstrap fix for
  `scripts/measure_product_oracle.py`, and
  `tests/unit/test_measure_product_oracle.py`.
- `bed49c5e coord(verify): request operator wave3 product oracle` committed the
  director-to-operator verify request:
  `coordination/mailbox/sent/2026-06-16T17-07-44Z-director-to-operator-verify-request.md`.
- `4bc1eb86 docs(handoff): director wave3 product oracle pending` committed the
  director-owned handoff for the operator Lane V boundary.
- `scripts/wave_gate_check.py 3` now reports `MET`.

The committed artifact currently records:

```text
artifact_kind=product-oracle
wave=3
arcface.arc_score=0.606526
lipsync.offset_frames=-1.000
lipsync.correlation=0.370732
```

## Director2 Disposition

Director2 has no active implementation, lock, co-sign, or verification target.
The checkpoint mini-batch is already complete and GO'd by operator2; the Wave 3
product-oracle artifact now belongs to `operator` Lane V.

Do not self-verify the product-oracle artifact as director2.

## Dirty Tree Caveat

During the first refresh, an unrelated director-owned handoff was observed as
untracked:

```text
?? docs/HANDOFF-director-2026-06-17-wave3-product-oracle-lanev-pending.md
```

That file was committed by another seat at `4bc1eb86` before this director2
handoff was staged. This handoff intentionally left it untouched.

## Exact Next Trigger

- `continue as operator` to verify the committed Wave 3 product-oracle artifact
  requested in `bed49c5e`.
- `continue as director2` only if the coordinator/user routes a new Pair-B row,
  asks for Pair-B support on product-oracle, or requests another director2
  handoff refresh.

Push remains user-gated.
