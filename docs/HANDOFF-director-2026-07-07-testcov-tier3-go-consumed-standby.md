# Handoff - director - 2026-07-07 testcov Tier-3 GO consumed standby

READ FIRST AS `director` (Pair-A). Current git, mailbox bodies, ref-bus
cursor, gate output, and capacity packets override this prose if they diverge.

Generated: `2026-07-07T09:13:38Z`
Seat: `director`
Repo: `/Users/hyungkoookkim/Content`

## Refresh First

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 5
env -u GIT_INDEX_FILE git log --oneline -12
env -u GIT_INDEX_FILE git status --short --branch
env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_doctor.py --wave 5
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Use `env -u GIT_INDEX_FILE` for ordinary git/pytest. Push, lock claims/releases,
pod/API spend, dependency edits, production generation, and inventory
transitions remain user-gated.

## Current Director State

Coordinator routed the test-coverage closure here:

```text
coordination/mailbox/sent/2026-06-26T23-10-00Z-coordinator-to-all-coordination.md
```

Pair-A Tier-1 is already closed and handed off by operator:

```text
docs/HANDOFF-operator-2026-06-27-testcov-tier1-go-standby.md
f3f85b1f operator(verify): GO Pair-A Tier-1 web test batch -> director [testcov T1]
dcc3b807 operator(handoff): testcov Tier-1 GO standby [Pair-A]
```

Director completed the Pair-A Tier-3 orchestration slice:

```text
b6609198 director(testcov): add Pair-A Tier-3 apply-correction coverage
c90dc3c3 director(verify-request): Pair-A Tier-3 apply-correction -> operator Lane-V
coordination/mailbox/sent/2026-06-27T02-34-15Z-director-to-operator-verify-request.md
```

Operator returned GO:

```text
cb3e467c operator(verify): GO Pair-A Tier-3 apply-correction Lane-V -> director [testcov T3]
coordination/mailbox/sent/2026-06-27T03-13-08Z-operator-to-director-verification-report.md
VERDICT: GO
```

Live churn while this director handoff was being written advanced Pair-B:

```text
26bbe885 operator2(handoff): Tier-3 audio DSP NITS standby
c4d65dd8 director2(test): cover FFmpeg missing-output fallback [testcov T3]
b25dc8d3 director2(verify-request): route audio DSP NITS fix to operator2
coordination/mailbox/sent/2026-07-07T09-12-52Z-director2-to-operator2-verify-request.md
```

## Mailbox And Gate State

Fresh director status:

```text
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 5
-> HEAD b25dc8d3 director2(verify-request): route audio DSP NITS fix to operator2
-> vs origin/main: 22 ahead, 0 behind
-> director unread: 0 / ref-bus
-> Wave 5 gate: MET counts={}
```

Mailbox monitor:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once
-> generated_at: 2026-07-07T09:13:38Z
-> director/director2/operator/operator2/coordinator/coordinator2 unread=0
-> latest coordinator broadcast: 2026-06-26T23-10-00Z
-> alerts: stale heartbeats only
```

Protocol gate evidence:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_doctor.py --wave 5
-> coordination clean; capacity board valid; inner protocol tests 115 passed; ci_smoke OK
-> PROTOCOL DOCTOR: PASS

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> RESULT: no ceremony detected; OK
```

Known smoke caveat only:

```text
R2 invisible-green WARN: tests/unit/test_lane_silent_gate_siblings_xfail.py:64 importorskip('cv2') - dep present.
```

## Pair-A Tier-3 Verification Evidence

Operator Lane-V verdict was GO with three non-blocking notes only:

```text
1. MINOR: _mutate_shot persistence boundary is unit-level, not full end-to-end persistence.
2. MINOR: characters_present fallback arm is not directly covered.
3. INFORMATIONAL: the char-precedence assertion currently depends on the broad production exception handler.
```

Current-HEAD focused rerun:

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_shot_controller_apply_correction.py -q
-> 3 passed in 3.07s
```

Scope remains test-only and lane-only:

```text
b6609198 changed:
docs/superpowers/briefs/2026-06-27-testcov-paira-tier3-apply-correction.md
tests/unit/test_shot_controller_apply_correction.py
```

No lock was claimed for the Pair-A testcov Tier-3 slice, so no lock release
applies.

## Dirty-Tree Caveat

The shared worktree has unrelated dirty/untracked state. Preserve it unless the
user explicitly routes work there:

```text
 M .claude/settings.json
?? .coverage
?? codex-plugin-cc-main/
?? coverage.xml
?? transfer/
```

This director handoff should include only:

```text
docs/HANDOFF-director-2026-07-07-testcov-tier3-go-consumed-standby.md
```

## Current Boundary

Director has no remaining owned implementation, verification-request,
mailbox-consume, cursor, lock, or push action for Pair-A testcov Tier-1/Tier-3.

Do not self-verify, update coordinator-owned closeout state, push, claim locks,
release locks, or spend pod/API budget from this director handoff.

## Exact Next Trigger

No `director` work is currently owed.

Next lawful protocol action is outside Pair-A:

```text
continue as operator2
```

Operator2 should verify the fresh Pair-B Tier-3 Audio DSP NITS fix route:

```text
b25dc8d3 director2(verify-request): route audio DSP NITS fix to operator2
coordination/mailbox/sent/2026-07-07T09-12-52Z-director2-to-operator2-verify-request.md
```

Coordinator closeout should wait until operator2 returns GO on that NITS fix or
reroutes a remaining issue.
