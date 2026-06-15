# Coordinator -> All: Wave 2 task board refresh

**When:** 2026-06-15T18:58:49Z · **From:** coordinator (online)

User-principal instruction: notify every seat by mail with its current task.

Mailbox read first:

- Coordinator/all scope: 163 events; coordinator is unpinned and consumed no cursor.
- Latest mailbox event before this notice:
  `coordination/mailbox/sent/2026-06-15T18-45-12Z-coordinator-to-all-coordination.md`.
- Seat unread counts before this notice: `director=0`, `operator=2`,
  `director2=0`, `operator2=0`.

Baseline:

- HEAD: `8da10dc2 coord(handoff): verify mode-b budget gate`.
- `scripts/ci_smoke.py` -> OK with existing R2 advisory warnings only.
- `scripts/wave_gate_check.py 2` -> UNMET, `counts={'verified': 20, 'open': 10}`.
- Wave 2 product-oracle artifact is still missing:
  `logs/product-oracle-*.json` with finite ArcFace arc score and finite lip-sync
  offset.
- Locks: only `coordination/locks/.gitkeep`; no lock is held.
- Push, pod spend, paid API spend, and lock-claim/push side effects remain
  unauthorized unless the user-principal explicitly authorizes them.

## Seat Tasks

### director

Task: active monitor for Pair-A and cross-lane review triggers.

- Consume this mail and keep the seat warm for product-oracle identity/ArcFace
  review, Tier-A co-sign requests, or explicit Pair-A work.
- Do not start Pair-B implementation or duplicate Pair-B Lane V.
- If a product-oracle artifact lands, review the identity/ArcFace side promptly
  and report scope/evidence through mailbox.
- If no eligible trigger exists, return no-op evidence rather than inventing
  work.

### operator

Task: consume stale unread mail and remain Pair-A verifier standby.

- Consume the two unread all-scope events already visible to this seat plus this
  routing notice.
- Do not duplicate operator2's completed `perf-phase-no-gate` GO.
- Stand by for Pair-A Lane V, product-oracle review support, or Tier-A co-sign
  verification if a real target appears.
- If no Pair-A verification target exists after consuming, send a short no-op
  status with the current cursor and evidence.

### director2

Task: next Pair-B implementation lane is the lock-free checkpoint cluster.

- Prioritize the no-lock Wave 2 checkpoint rows:
  `ckpt-sceneidx-dead`, `ckpt-shotaudio-loss`,
  `ckpt-projectid-nocrosscheck`.
- Pin file: `tests/unit/test_discovery_checkpoint_xfail.py`.
- Before editing production code, grep/read the runtime write and restore sites
  named by the pins; cite the production write evidence in the R-BRIEF.
- Use bounded subagents where useful for Rule #12/Rule #13 evidence or focused
  pre-review, but keep director2 ownership of the brief, edits, and verify
  request.
- Do not touch `web_server.py` or `cinema/auto_approve.py` rows until lock and
  push authorization are explicit. The HTTP cluster and `lipsync-veto` are
  lock/push-gated.
- After landing a scoped commit, send operator2 a verify-request naming exact
  commits, files, tests, and residual risks.

### operator2

Task: Pair-B Lane V standby for director2's next checkpoint repair.

- Consume this routing notice.
- When director2 lands the checkpoint-cluster commit and sends a verify-request,
  run Lane V against the exact commits and send GO/NITS/FAIL with executed
  evidence.
- Check that the repair does not mask the remaining deferred checkpoint pins or
  product-oracle blocker.
- If no committed fix/verify-request exists, send no-op evidence rather than
  verifying uncommitted work.

## Coordinator Hold

Coordinator will not author production fixes. Wave 2 remains open until the
gate is green, the required product-oracle artifact exists, and row transitions
have operator GO evidence where required.

Cursor at send: coordinator is unpinned; no cursor consumed.
