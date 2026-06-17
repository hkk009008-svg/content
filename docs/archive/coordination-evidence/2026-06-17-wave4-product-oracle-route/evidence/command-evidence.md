# Command Evidence

These are the coordinator-side checks used for the Wave 4 product-oracle route
snapshot.

## Mailbox Monitor

Command:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once
```

Output:

```text
latest coordinator broadcast: 2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
receipt split: consumed=0 unread=4 unknown=0
director   unread=1 latest=2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
director2  unread=1 latest=2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
operator   unread=1 latest=2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
operator2  unread=1 latest=2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
ALERTS: unread mail present for all four seats; coordinator broadcast unconsumed by all four seats.
```

## Capacity Board

Command:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 4
```

Output:

```text
# Protocol Capacity Board
wave: 4
valid: true

ACTORS
coordinator packets=wave4-product-oracle-coordinator-route status=active
director    packets=wave4-product-oracle-director-artifact status=ready
director2   packets=wave4-product-oracle-director2-standby status=blocked
operator    packets=wave4-product-oracle-operator-lanev status=blocked
operator2   packets=wave4-product-oracle-operator2-standby status=blocked

BLOCKING ISSUES
- none
```

## Route Validation

Command:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 4 --validate-route coordination/mailbox/sent/2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
```

Output:

```text
# Protocol Capacity Route Validation
route: coordination/mailbox/sent/2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
route valid: true

BLOCKING ISSUES
- none
```

## Wave Gate

Command:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 4
```

Output:

```text
Wave 4 gate: UNMET  counts={'verified': 1}
  gate rows: 0; executable selectors: 0
  PRODUCT ORACLE BLOCKER: Wave 4 requires a committed logs/product-oracle-*.json artifact with artifact_kind=product-oracle, wave=4, finite arcface.arc_score, and finite lipsync.offset_frames; invalid artifacts: /Users/hyungkoookkim/Content/logs/product-oracle-wave2.json: wave is not 4; /Users/hyungkoookkim/Content/logs/product-oracle-wave3.json: wave is not 4
```

## Coordination Check

Command:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py --docs-root docs
```

Output:

```text
INFO unread mailbox/seen/director.txt - director: 1 unread event(s)
INFO unread mailbox/seen/director2.txt - director2: 1 unread event(s)
INFO unread mailbox/seen/operator.txt - operator: 1 unread event(s)
INFO unread mailbox/seen/operator2.txt - operator2: 1 unread event(s)
OK - coordination clean (4 INFO)
```

## Inventory Anchor Check

Command:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py docs/REMEDIATION-INVENTORY.md
```

Output:

```text
All anchors checked - no drift.
```

## Smoke

Command:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Output:

```text
R1 xfail-strictness ....... PASS  0 xfail markers; all strict=True+reason
R2 invisible-green ........ WARN
     tests/unit/test_lane_silent_gate_siblings_xfail.py:64: importorskip('cv2') - dep present (latent invisible-green risk)
R3 gate-executes-pins ..... PASS  wave_gate_check.py executes the pins
R4 ci-runs-runxfail ....... PASS  a CI workflow runs --runxfail
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

## Independent Helper Finding

Read-only coordinator helper `019ed491-dbf5-7b52-b526-273835c90da3` confirmed:
the reverify rows have GO and consumed evidence, Wave 4 must not close without
`logs/product-oracle-wave4.json`, and the right coordinator action is inventory
reconciliation plus one consolidated product-oracle route.
