# Handoff - operator - 2026-06-17 Wave 4 product-oracle GO standby

READ FIRST AS `operator`. Current git, mailbox bodies, and live gate evidence
override this prose if they diverge.

Generated: `2026-06-17T08:05:45Z` (`2026-06-17T17:05:45+0900`)
Seat: `operator`
Repo: `/Users/hyungkoookkim/Content`

## Refresh First

```bash
env -u GIT_INDEX_FILE .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 4
env -u GIT_INDEX_FILE git log --oneline -12
env -u GIT_INDEX_FILE git status --short
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 4
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Use `env -u GIT_INDEX_FILE` for ordinary git and pytest. The active
`GIT_INDEX_FILE=/Users/hyungkoookkim/Content/.git/index-codex-operator` was
stale during this turn; default-index commands with `env -u GIT_INDEX_FILE`
were the reliable view.

## Current Durable State

Latest refreshed HEAD before this handoff:

```text
ea448b9c operator(verify): GO wave4 product oracle
6fa3f75a director2(mail): consume wave4 product oracle route
465b34b1 docs(handoff): refresh director oracle handoff caveats
5c1b62ab docs(handoff): director wave4 oracle Lane V pending
41fd0869 operator2(mail): consume wave4 product oracle route
1e32a4f8 director(verify): request wave4 oracle Lane V
7a11c32d coord(route): archive wave4 product-oracle packets
a4f44dc2 director(product-oracle): add wave4 oracle artifact
c6b0924f docs(handoff): director wave4 identity GO standby
e1f2fb8c docs(handoff): operator identity embselect standby
90866e88 docs(director2): refresh mailbox kind GO handoff
54ac94ba docs(director2): handoff mailbox kind GO
```

Operator status after the GO commit:

```text
branch main
ea448b9c operator(verify): GO wave4 product oracle
vs origin/main: 5 ahead, 0 behind
operator cursor: 2026-06-17T07:58:23Z
operator UNREAD: 0
Wave 4 gate: MET counts={'verified': 1}
PRODUCT ORACLE: logs/product-oracle-wave4.json
```

## Operator Work Completed

Consumed and verified these operator-addressed mailbox events:

```text
coordination/mailbox/sent/2026-06-17T07-54-34Z-coordinator-to-all-coordination.md
coordination/mailbox/sent/2026-06-17T07-58-23Z-director-to-operator-verify-request.md
```

Verified request:

```text
coordination/mailbox/sent/2026-06-17T07-58-23Z-director-to-operator-verify-request.md
Commit verified: a4f44dc2 director(product-oracle): add wave4 oracle artifact
Artifact: logs/product-oracle-wave4.json
Row: identity-arcface-embselect
```

Operator issued GO and folded the cursor in the same commit:

```text
ea448b9c operator(verify): GO wave4 product oracle
coordination/mailbox/sent/2026-06-17T08-04-43Z-operator-to-director-verification-report.md
coordination/mailbox/seen/operator.txt -> 2026-06-17T07:58:23Z
```

## Verification Evidence

Diff scope:

```text
env -u GIT_INDEX_FILE git diff-tree --no-commit-id --name-status -r a4f44dc2
-> M coordination/mailbox/seen/director.txt
-> A logs/product-oracle-wave4.json
```

Artifact contract and input hashes:

```text
jq -r '[.artifact_kind, (.wave|tostring), .instrument, (.arcface.arc_score|tostring), (.lipsync.offset_frames|tostring), .inputs.video.path, .inputs.video.sha256, .inputs.reference_image.path, .inputs.reference_image.sha256] | @tsv' logs/product-oracle-wave4.json
-> product-oracle 4 scripts/measure_product_oracle.py 0.606526 -1.0 logs/lipsync_gen_v2studio.mp4 aad6aa4fdf13da0a5e61427542f532930f447cf95b8da0d24042685cf37a1827 logs/ref_lighting.jpg 1640b178e8f7591d85f726a8d72c6da07f33465ddd6279590f5885cc804c21ef

shasum -a 256 logs/lipsync_gen_v2studio.mp4 logs/ref_lighting.jpg
-> aad6aa4fdf13da0a5e61427542f532930f447cf95b8da0d24042685cf37a1827  logs/lipsync_gen_v2studio.mp4
-> 1640b178e8f7591d85f726a8d72c6da07f33465ddd6279590f5885cc804c21ef  logs/ref_lighting.jpg
```

Measurement reproduction:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/measure_product_oracle.py --wave 4 --video logs/lipsync_gen_v2studio.mp4 --reference-image logs/ref_lighting.jpg --output /private/tmp/product-oracle-wave4-operator.json
-> wrote /private/tmp/product-oracle-wave4-operator.json
-> arcface.arc_score=0.606526 lipsync.offset_frames=-1.000 lipsync.correlation=0.370732
```

Focused tests and gates:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_measure_product_oracle.py -q
-> 4 passed in 2.02s

env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 4
-> Wave 4 gate: MET counts={'verified': 1}
-> PRODUCT ORACLE: logs/product-oracle-wave4.json

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> RESULT: no ceremony detected - every relied-on green is backed by execution.
-> OK
-> known R2 invisible-green warning only: tests/unit/test_lane_silent_gate_siblings_xfail.py:64 importorskip('cv2') - dep present.
```

Independent read-only `lane-v-verifier` helper also returned GO with no NITS or
FAIL reasons.

## Dirty Tree Caveat

At handoff time, the default index also had unrelated director-owned staged
changes:

```text
env -u GIT_INDEX_FILE git status --short
-> M  coordination/mailbox/seen/director.txt
-> A  docs/HANDOFF-director-2026-06-17-wave4-oracle-go-consumed.md

env -u GIT_INDEX_FILE git diff -- coordination/mailbox/seen/director.txt
-> 2026-06-17T07:54:34Z -> 2026-06-17T08:04:43Z
```

These are director cursor/handoff updates, not operator-owned work. Do not
revert them from the operator seat.

## Current Boundary

Operator has no unread mail and no remaining Lane V action after `ea448b9c`.
No lock release applies. No push was authorized or attempted.

Wave 4 executable gate is now `MET`, but coordinator owns the cross-seat
closeout/reconciliation after reading all-scope mail and current inventory.

## Exact Next Trigger

```text
continue as coordinator
```

Coordinator should reread all-scope mailbox bodies, refresh the Wave 4 capacity
board and route validation, rerun Wave 4 gate and smoke, preserve the dirty
director cursor state, then close out or reroute.
