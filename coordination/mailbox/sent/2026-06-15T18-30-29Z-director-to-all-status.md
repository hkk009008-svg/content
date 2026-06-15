# Director -> All: active monitor after perf-phase FAIL route

**When:** 2026-06-15T18:30:29Z · **From:** director (online)

Director consumed and processed the Pair-B `perf-phase-no-gate` FAIL route plus
operator/operator2 active-monitor baselines.

The user-principal also directed Codex to use subagents whenever they are a good
fit, especially when safe parallel execution improves outcome quality, speed,
coverage, or independent verification. Director will apply that preference
within protocol boundaries: no parallel agents on shared files, and no subagent
bypass of director/operator/coordinator responsibilities.

## Consumed Events

Director consumed:

- `2026-06-15T18-16-10Z-operator2-to-all-verification-report.md`
- `2026-06-15T18-18-10Z-coordinator-to-all-coordination.md`
- `2026-06-15T18-21-31Z-operator2-to-all-status.md`
- `2026-06-15T18-23-03Z-operator-to-all-status.md`
- `2026-06-15T18-26-14Z-operator-to-all-status.md`
- `2026-06-15T18-29-08Z-operator2-to-all-status.md`

Cursor advanced through:

```text
cursor director: 2026-06-15T18:26:14Z -> 2026-06-15T18:29:08Z; unread now: 0
```

## Capacity Board

| seat | state | what/how/why |
|---|---|---|
| director | active monitor / support only | Pair-A has no active implementation row, verify request, Tier-A co-sign, or product-oracle artifact. Director is watching all seats and ready for product-oracle identity/ArcFace review, Tier-A co-sign, explicit Pair-A work, or bounded subagent support where role-safe. |
| director2 | active repair | Coordinator routed `perf-phase-no-gate` repair to director2 after operator2 FAIL. Visible uncommitted repair files suggest director2 work is now in flight; this director does not own those edits. |
| operator2 | standby for re-verification | Operator2 issued the formal FAIL, published active-monitor standby, and remains the correct verifier for the next committed director2 fix plus verify-request. |
| operator | standby / no-op | Pair-A operator recorded the same active-monitor directive but still has no Pair-A Lane V target and must not duplicate Pair-B Lane V by default. |

## Evidence

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
797eec50 docs(handoff): operator2 active monitor standby
45e53bbc coord(cursor): operator consume monitor updates
1a158cec docs(handoff): operator active monitor baseline
14676d2f docs(handoff): operator standby after pairb route
6feb5397 docs(handoff): operator2 standby after perf fail route

$ CODEX_SEAT=director GIT_INDEX_FILE=.git/index-codex-director .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2
HEAD 797eec50 docs(handoff): operator2 active monitor standby
UNREAD: 2 before consuming, then 0 after consume-events
Wave 2 gate: UNMET counts={'verified': 19, 'open': 11}
gate rows: 21; executable selectors: 24
PRODUCT ORACLE BLOCKER: missing Wave 2 product-oracle artifact

$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK

$ env -u GIT_INDEX_FILE git diff --name-only
ARCHITECTURE.md
cinema/phases/performance.py
cinema/shots/controller.py
cinema_pipeline.py
coordination/mailbox/seen/director.txt
coordination/mailbox/seen/director2.txt
coordination/mailbox/seen/operator.txt
coordination/mailbox/seen/operator2.txt
coordination/mailbox/sent/2026-06-15T18-05-33Z-director2-to-all-status.md
cost_tracker.py
docs/PROGRAM-MANUAL.md
docs/BRIEF-director2-2026-06-16-perf-phase-no-gate.md
docs/REMEDIATION-INVENTORY.md
performance/driving_video.py
tests/unit/test_budget_pre_spend_gate.py
tests/unit/test_cost_tracker.py
```

## Director Decision

No Pair-A implementation or verification work is legal from this seat right now.
The max-capacity move is active monitoring plus fast response to the next
eligible trigger:

- if director2 lands the scoped repair, operator2 should verify immediately;
- if director2 goes stale before acting, re-run seat status and escalate through
  coordinator/user rather than silently waiting;
- if product-oracle identity/ArcFace evidence appears, director should review it
  promptly;
- if a Tier-A co-sign request appears, director should verify source scope before
  signing;
- use bounded subagents whenever they improve outcome or safe parallel coverage,
  without crossing seat ownership or touching shared files in parallel.

No production code, inventory row, lock, product-oracle artifact, or push is
owned by this status.

Cursor at send: 2026-06-15T18:29:08Z
