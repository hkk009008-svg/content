# Director2 Handoff - Standby After Env-U Repair Route

Generated: `2026-06-16T20:36:59Z` (`2026-06-17T05:36:59+0900` KST)
Repo: `/Users/hyungkoookkim/Content`
Seat: `director2`

Trust live git, mailbox, gate, and filesystem state over this snapshot if they
diverge.

## Refresh First

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 3
env -u GIT_INDEX_FILE git log --oneline -12
env -u GIT_INDEX_FILE git status --short --branch
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Use `env -u GIT_INDEX_FILE` for ordinary git/pytest commands. Push, lock
claim/release, pod/API spend, dependency edits, production generation, and
inventory transitions remain user-gated.

## Live State At Handoff

Latest refreshed director2 status before this handoff:

```text
HEAD: 80ed3704 coord(director): request env-u repair Lane V
branch: main
vs origin/main: 38 ahead, 0 behind
director2 cursor: 2026-06-16T20:28:41Z
director2 unread: 0
Wave 3 gate: MET counts={'verified': 3}
PRODUCT ORACLE: logs/product-oracle-wave3.json
```

Recent history at refresh:

```text
80ed3704 coord(director): request env-u repair Lane V
421fc358 fix(codex): block env-u segment bypass
2d98f279 docs(handoff): operator2 NITS reread pending
79ebaf4a docs(handoff): operator hook repair standby
281170aa coord(route): reroute harness bestversion repairs
a76908da docs(handoff): director2 standby after route
63887c81 docs(handoff): director2 consume repair route
06a20f97 director2(coord): resolve mailbox cli NITS scope
7b44def6 docs(handoff): director harness bestversion fail pending
9c9b1fac docs(handoff): operator2 mailbox cli NITS standby
3d141d5c operator(verify): FAIL git-index guard quote-aware
5412cb65 operator2(verify): NITS mailbox cli Lane V
```

Director2 has no unread mailbox, so no cursor consume is owed for this handoff.

## Current Route Read

Binding coordinator route remains:

```text
coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md
281170aa coord(route): reroute harness bestversion repairs
```

Director2 packet:

```text
wave3-harness-bestversion-director2-standby-after-nits-response
status: blocked
allowed_paths: []
acceptance:
- stand by after the committed NITS-resolution response
- act only if operator2 returns NITS or FAIL on the process resolution
```

Current capacity board:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
# Protocol Capacity Board
wave: 3
valid: true

ACTORS
coordinator packets=wave3-harness-bestversion-repair-coordinator-route status=active
director    packets=wave3-harness-bestversion-director-hook-env-bypass-repair status=active
director2   packets=wave3-harness-bestversion-director2-standby-after-nits-response status=blocked
operator    packets=wave3-harness-bestversion-operator-hook-repair-lanev status=blocked
operator2   packets=wave3-harness-bestversion-operator2-mailbox-cli-nits-reread status=active

BLOCKING ISSUES
- none
```

Route validation:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md
# Protocol Capacity Route Validation
route: coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md
route valid: true

BLOCKING ISSUES
- none
```

## Pair-B State

Director2 already resolved the Task 2 NITS as a process/metadata issue:

```text
06a20f97 director2(coord): resolve mailbox cli NITS scope
coordination/mailbox/sent/2026-06-16T20-25-32Z-director2-to-operator2-coordination.md
```

Operator2 has not issued the final reread verdict yet. The latest operator2
artifact remains a pending handoff:

```text
2d98f279 docs(handoff): operator2 NITS reread pending
docs/HANDOFF-operator2-2026-06-17-nits-resolution-reread-pending.md
```

Director2 should not self-verify or re-route this. Act only if operator2 returns
NITS or FAIL against the `06a20f97` process resolution.

## Peer State Since Prior Director2 Handoff

The Pair-A repair lane has advanced independently:

```text
421fc358 fix(codex): block env-u segment bypass
80ed3704 coord(director): request env-u repair Lane V
coordination/mailbox/sent/2026-06-16T20-34-59Z-director-to-operator-verify-request.md
```

That is director/operator work, not director2 work. Director2 should not consume,
verify, or route it unless a future durable event explicitly addresses
director2.

## Gate And Smoke Evidence

Wave 3 gate from live status:

```text
Wave 3 gate: MET counts={'verified': 3}
PRODUCT ORACLE: logs/product-oracle-wave3.json
```

Smoke:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
WARNING: coordination ADVISORY [unknown_kind] mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md -- kind 'verify-addendum' not in KNOWN_KINDS
CEREMONY CHECK -- forbid appearance-of-verification-without-substance (ADR-027 / ADR-028)
R1 xfail-strictness ....... PASS  0 xfail markers; all strict=True+reason
R2 invisible-green ........ WARN
     ~ tests/unit/test_discovery_identity_xfail.py:193: skip() in a pin file -- confirm it cannot hide the pinned defect
     ~ tests/unit/test_lane_silent_gate_siblings_xfail.py:64: importorskip('cv2') -- dep present (latent invisible-green risk)
R3 gate-executes-pins ..... PASS  wave_gate_check.py executes the pins
R4 ci-runs-runxfail ....... PASS  a CI workflow runs --runxfail

RESULT: no ceremony detected -- every relied-on green is backed by execution.
OK
```

## Dirty Tree Caveat

Before staging this handoff, shared-tree state included:

```text
 M coordination/mailbox/seen/operator.txt
?? docs/HANDOFF-coordinator-2026-06-17-handoff-traversal-fail.md
```

Do not commit, revert, or clean those from a director2 context. This handoff
should stage and commit only:

```text
docs/HANDOFF-director2-2026-06-17-standby-after-envu-repair-route.md
```

No push, lock claim, production edit, paid API spend, pod spend, dependency
edit, route event, cursor consume, verification verdict, or inventory transition
was opened by this handoff.

## Exact Next Trigger

- `continue as operator2` to run the narrow NITS-resolution reread against
  `06a20f97` and
  `coordination/mailbox/sent/2026-06-16T20-25-32Z-director2-to-operator2-coordination.md`,
  then issue GO, NITS, or FAIL for Task 2 process resolution.
- `continue as operator` to verify `421fc358` from the director verify-request
  in `coordination/mailbox/sent/2026-06-16T20-34-59Z-director-to-operator-verify-request.md`.
- `continue as director2` only if operator2 returns NITS or FAIL on the Task 2
  process resolution, or if a new coordinator/direct mailbox event explicitly
  addresses director2.
- `continue as coordinator` only after Pair-A and Pair-B verdicts are GO or
  resolved NITS, or if a seat emits FAIL/NITS that needs cross-seat routing.

Push remains user-gated.
