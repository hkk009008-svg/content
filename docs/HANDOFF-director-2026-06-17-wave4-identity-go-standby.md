# Handoff - director - 2026-06-17 Wave 4 identity GO standby

READ FIRST AS `director`. Current git, mailbox bodies, and live gate evidence
override this prose if they diverge.

Generated: `2026-06-17T07:54:23Z` (`2026-06-17T16:54:23+0900`)
Seat: `director`
Repo: `/Users/hyungkoookkim/Content`

## Refresh First

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 4
env -u GIT_INDEX_FILE git log --oneline -12
env -u GIT_INDEX_FILE git status --short --branch
.venv/bin/python scripts/mailbox_monitor.py --once
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 4
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 4 --validate-route coordination/mailbox/sent/2026-06-17T06-53-23Z-coordinator-to-all-coordination.md
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 4
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Use `env -u GIT_INDEX_FILE` for ordinary git and pytest. Push, lock side
effects, pod/API spend, dependency edits, production generation, and inventory
transitions remain user-gated or coordinator-owned as applicable.

## Current Durable State

Newest same-seat handoff read before this state transfer:

```text
docs/HANDOFF-director-2026-06-17-wave3-harness-closeout-standby.md
```

That handoff is stale for active work: it closed Wave 3 harness-bestversion
standby. Current git and mailbox state have since opened and worked Wave 4.

HEAD at refresh:

```text
e1f2fb8c docs(handoff): operator identity embselect standby
90866e88 docs(director2): refresh mailbox kind GO handoff
54ac94ba docs(director2): handoff mailbox kind GO
ba36d907 director2(mail): consume mailbox kind GO
41e73a6b director(mail): consume identity GO
b733820f docs(operator2): handoff mailbox kind GO
45e51b47 operator2(verify): GO mailbox kind NITS
0d79ca24 operator(verify): GO identity embselect nits
5c1b0888 docs(handoff): coordinator wave4 reverify pending
78aab7cc codex(protocol): default seats to bounded subagent consideration
37ed0e9b director(verify): request identity NITS recheck
b41528b2 director2(verify): request mailbox kind nit reread
```

Branch and worktree at refresh:

```text
main...origin/main [ahead 24]
```

At final refresh, the only dirty worktree entry was this untracked handoff file:

```text
?? docs/HANDOFF-director-2026-06-17-wave4-identity-go-standby.md
```

## Mailbox State

Fresh director status:

```text
cursor: 2026-06-17T07:49:37Z
UNREAD: 0
```

Fresh mailbox monitor:

```text
generated_at: 2026-06-17T07:54:23Z
latest coordinator broadcast: 2026-06-17T06-53-23Z-coordinator-to-all-coordination.md
receipt split: consumed=4 unread=0 unknown=0
director   unread=0 cursor=2026-06-17T07:49:37Z
director2  unread=0 cursor=2026-06-17T07:49:57Z
operator   unread=0 cursor=2026-06-17T07:46:41Z
operator2  unread=0 cursor=2026-06-17T07:46:40Z
ALERTS: none
```

Director consumed the Wave 4 identity GO report:

```text
coordination/mailbox/sent/2026-06-17T07-49-37Z-operator-to-director-verification-report.md
41e73a6b director(mail): consume identity GO
```

## Binding Director-Lane State

Pair-A row:

```text
identity-arcface-embselect
wave4-bug-error-director-identity-embselect
```

Relevant commits and mailbox evidence:

```text
6e7de9fe fix(identity): select largest ok reference embedding
efd88583 director(verify): request identity embselect Lane V
aa474e2b operator(verify): NITS identity embselect
a072b1da docs(identity): fix embselect Lane V nits
37ed0e9b director(verify): request identity NITS recheck
0d79ca24 operator(verify): GO identity embselect nits
41e73a6b director(mail): consume identity GO
```

Operator GO summary:

```text
coordination/mailbox/sent/2026-06-17T07-49-37Z-operator-to-director-verification-report.md
VERDICT: GO
Commit verified: a072b1da9f363f7585502333c55881407bd10535
Row: identity-arcface-embselect
```

The operator report says the NITS-fix diff is documentation/cursor only, the
stale brief and manual anchors are closed, focused identity regression passed,
doc anchors are clean, and smoke is OK with the known R2 warning.

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
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 4 --validate-route coordination/mailbox/sent/2026-06-17T06-53-23Z-coordinator-to-all-coordination.md
route valid: true
BLOCKING ISSUES
- none
```

Wave gate:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 4
Wave 4 gate: UNMET  counts={'implemented': 1}
PRODUCT ORACLE BLOCKER: Wave 4 requires a committed logs/product-oracle-*.json artifact with artifact_kind=product-oracle, wave=4, finite arcface.arc_score, and finite lipsync.offset_frames.
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
mailbox-send action. Do not self-verify or update coordinator-owned closeout
state from the director seat.

`docs/REMEDIATION-INVENTORY.md` still has `identity-arcface-embselect` as
`implemented | pending operator Lane V` at the time this handoff was drafted,
even though the operator GO is now durable. Coordinator reconciliation should
record the verified state if current evidence still matches.

Wave 4 gate remains unmet because the required Wave 4 product-oracle artifact
is not committed yet. That closeout belongs to coordinator/capacity-max
reconciliation, not this director handoff.

## Exact Next Trigger

```text
continue as coordinator
```

Coordinator should reread all-scope mailbox bodies, rerun the Wave 4 board,
route validation, Wave 4 gate, and smoke, then reconcile the two Wave 4 GO
reports plus the product-oracle blocker into a closeout or reroute.
