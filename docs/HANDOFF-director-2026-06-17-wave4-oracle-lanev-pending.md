# Handoff - director - 2026-06-17 Wave 4 oracle Lane V pending

READ FIRST AS `director`. Current git, mailbox bodies, and live gate evidence
override this prose if they diverge.

Generated: `2026-06-17T08:00:58Z` (`2026-06-17T17:00:58+0900`)
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

Use `env -u GIT_INDEX_FILE` for ordinary git and pytest. Push, lock side
effects, pod/API spend, dependency edits, production generation, and inventory
transitions remain user-gated or coordinator-owned as applicable.

## Current Durable State

Newest same-seat handoff read before this state transfer:

```text
docs/HANDOFF-director-2026-06-17-wave4-identity-go-standby.md
```

That handoff is stale for active work: it stopped after the identity
embselect GO. Current git and mailbox state have since routed and landed the
Wave 4 product-oracle artifact.

HEAD at refresh:

```text
1e32a4f8 director(verify): request wave4 oracle Lane V
7a11c32d coord(route): archive wave4 product-oracle packets
a4f44dc2 director(product-oracle): add wave4 oracle artifact
c6b0924f docs(handoff): director wave4 identity GO standby
e1f2fb8c docs(handoff): operator identity embselect standby
90866e88 docs(director2): refresh mailbox kind GO handoff
54ac94ba docs(director2): handoff mailbox kind GO
ba36d907 director2(mail): consume mailbox kind GO
41e73a6b director(mail): consume identity GO
b733820f docs(operator2): handoff mailbox kind GO
45e51b47 operator2(verify): GO mailbox kind NITS
0d79ca24 operator(verify): GO identity embselect nits
```

Branch and worktree at refresh:

```text
main...origin/main
```

No dirty worktree entries were present before this handoff file was drafted.
At final pre-commit refresh, an unrelated `M coordination/mailbox/seen/operator2.txt`
entry was visible; it is excluded from this director handoff commit.
A later post-commit refresh showed that other-seat cursor work landed as
`41fd0869 operator2(mail): consume wave4 product oracle route` before this
handoff artifact was finalized. It is outside director scope and does not
change the exact next trigger below.
At the final refresh before this addendum, an unrelated
`M coordination/mailbox/seen/operator.txt` entry was visible and was also
excluded from this director handoff commit.

## Mailbox State

Fresh director status:

```text
cursor: 2026-06-17T07:54:34Z
UNREAD: 0
```

Fresh mailbox monitor:

```text
generated_at: 2026-06-17T08:00:48Z
latest coordinator broadcast: 2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
receipt split: consumed=1 unread=3 unknown=0
director   unread=0 cursor=2026-06-17T07:54:34Z receipt=consumed
director2  unread=1 latest=2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
operator   unread=2 latest=2026-06-17T07-58-23Z-director-to-operator-verify-request.md
operator2  unread=1 latest=2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
ALERTS: unread mail present for director2, operator, operator2; coordinator broadcast has unconsumed seats director2, operator, operator2
```

Director consumed the coordinator product-oracle route in:

```text
a4f44dc2 director(product-oracle): add wave4 oracle artifact
coordination/mailbox/seen/director.txt cursor -> 2026-06-17T07:54:34Z
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

Measurement command and result:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/measure_product_oracle.py --wave 4 --video logs/lipsync_gen_v2studio.mp4 --reference-image logs/ref_lighting.jpg --output logs/product-oracle-wave4.json
arcface.arc_score=0.606526 lipsync.offset_frames=-1.000 lipsync.correlation=0.370732
```

Artifact contract in `logs/product-oracle-wave4.json`:

```text
artifact_kind=product-oracle
wave=4
instrument=scripts/measure_product_oracle.py
inputs.video.path=logs/lipsync_gen_v2studio.mp4
inputs.video.sha256=aad6aa4fdf13da0a5e61427542f532930f447cf95b8da0d24042685cf37a1827
inputs.reference_image.path=logs/ref_lighting.jpg
inputs.reference_image.sha256=1640b178e8f7591d85f726a8d72c6da07f33465ddd6279590f5885cc804c21ef
```

Director verify-request:

```text
1e32a4f8 director(verify): request wave4 oracle Lane V
coordination/mailbox/sent/2026-06-17T07-58-23Z-director-to-operator-verify-request.md
```

The verify-request asks `operator` for GO/NITS/FAIL on commit `a4f44dc2`.
Director must not self-verify.

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

Focused product-oracle tests:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_measure_product_oracle.py -q
4 passed
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
mailbox-send action. The Wave 4 product-oracle artifact is committed and the
operator Lane V request is committed.

Do not self-verify, update coordinator-owned closeout state, push, claim locks,
or spend pod/API budget from this director handoff.

## Exact Next Trigger

```text
continue as operator
```

Operator should read its unread mailbox bodies, including the coordinator route
and `coordination/mailbox/sent/2026-06-17T07-58-23Z-director-to-operator-verify-request.md`,
then independently verify commit `a4f44dc2` and issue GO/NITS/FAIL.
