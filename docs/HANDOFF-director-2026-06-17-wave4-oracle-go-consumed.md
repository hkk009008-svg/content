# Handoff - director - 2026-06-17 Wave 4 oracle GO consumed

READ FIRST AS `director`. Current git, mailbox bodies, and live gate evidence
override this prose if they diverge.

Generated: `2026-06-17T08:05:31Z` (`2026-06-17T17:05:31+0900`)
Seat: `director`
Repo: `/Users/hyungkoookkim/Content`

## Refresh First

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 4
env -u GIT_INDEX_FILE git log --oneline -12
env -u GIT_INDEX_FILE git status --short --branch
env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 4
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 4 --validate-route coordination/mailbox/sent/2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 4
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Push, lock claims/releases, pod/API spend, dependency edits, production
generation, inventory transitions, and coordinator closeout remain outside
this director handoff.

## Current Durable State

Newest same-seat handoff read before this state transfer:

```text
docs/HANDOFF-director-2026-06-17-wave4-oracle-lanev-pending.md
```

HEAD at refresh:

```text
ea448b9c operator(verify): GO wave4 product oracle
6fa3f75a director2(mail): consume wave4 product oracle route
465b34b1 docs(handoff): refresh director oracle handoff caveats
5c1b62ab docs(handoff): director wave4 oracle Lane V pending
41fd0869 operator2(mail): consume wave4 product oracle route
1e32a4f8 director(verify): request wave4 oracle Lane V
7a11c32d coord(route): archive wave4 product-oracle packets
a4f44dc2 director(product-oracle): add wave4 oracle artifact
```

Branch state at refresh:

```text
main...origin/main [ahead 5]
```

## Mailbox State

Director consumed the operator GO report:

```text
coordination/mailbox/sent/2026-06-17T08-04-43Z-operator-to-director-verification-report.md
coordination/mailbox/seen/director.txt: 2026-06-17T07:54:34Z -> 2026-06-17T08:04:43Z
```

Fresh director status:

```text
cursor: 2026-06-17T08:04:43Z
UNREAD: 0
```

Fresh mailbox monitor:

```text
generated_at: 2026-06-17T08:05:31Z
latest coordinator broadcast: 2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
receipt split: consumed=4 unread=0 unknown=0
director   unread=0 cursor=2026-06-17T08:04:43Z receipt=consumed
director2  unread=0 cursor=2026-06-17T07:54:34Z receipt=consumed
operator   unread=0 cursor=2026-06-17T07:58:23Z receipt=consumed
operator2  unread=0 cursor=2026-06-17T07:54:34Z receipt=consumed
ALERTS: none
```

## Binding Director-Lane State

Coordinator route:

```text
coordination/mailbox/sent/2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
```

Director artifact commit:

```text
a4f44dc2 director(product-oracle): add wave4 oracle artifact
logs/product-oracle-wave4.json
```

Director verify-request:

```text
1e32a4f8 director(verify): request wave4 oracle Lane V
coordination/mailbox/sent/2026-06-17T07-58-23Z-director-to-operator-verify-request.md
```

Operator Lane V verdict:

```text
ea448b9c operator(verify): GO wave4 product oracle
coordination/mailbox/sent/2026-06-17T08-04-43Z-operator-to-director-verification-report.md
VERDICT: GO
```

Operator evidence reproduced the artifact contract and measurement:

```text
artifact_kind=product-oracle
wave=4
instrument=scripts/measure_product_oracle.py
arcface.arc_score=0.606526
lipsync.offset_frames=-1.0
inputs.video.sha256=aad6aa4fdf13da0a5e61427542f532930f447cf95b8da0d24042685cf37a1827
inputs.reference_image.sha256=1640b178e8f7591d85f726a8d72c6da07f33465ddd6279590f5885cc804c21ef
```

## Gate, Capacity, And Smoke Evidence

Capacity board:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 4
valid: true
BLOCKING ISSUES
- none
```

Active route validation:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 4 --validate-route coordination/mailbox/sent/2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
route valid: true
BLOCKING ISSUES
- none
```

Wave gate:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 4
Wave 4 gate: MET  counts={'verified': 1}
PRODUCT ORACLE: logs/product-oracle-wave4.json
```

Smoke:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Known smoke caveat only:

```text
R2 invisible-green WARN: tests/unit/test_lane_silent_gate_siblings_xfail.py:64 importorskip('cv2') - dep present.
```

## Current Boundary

Director has no remaining owned implementation, verification, cursor, or
mailbox-send action for the Wave 4 product-oracle cycle.

Do not self-verify, update coordinator-owned closeout state, push, claim locks,
release locks, or spend pod/API budget from this director handoff.

## Exact Next Trigger

```text
continue as coordinator
```

Coordinator should rerun mailbox monitor, Wave 4 capacity board, the active
route validation, `scripts/wave_gate_check.py 4`, and `scripts/ci_smoke.py`,
then write the Wave 4 closeout or reroute.
