# Protocol Effectiveness Loop Design

*Date: 2026-06-16. Status: design approved in brainstorming; written for user review
before implementation planning.*

## 0. Locked Decisions

| Decision | Choice |
|---|---|
| Optimization target | Balanced effectiveness, with verified throughput as the tie-breaker |
| First slice | Measurement and feedback loop only |
| Primary output | Read-only protocol effectiveness report |
| Rule changes | Deferred until repeated measured waste justifies a proposal |
| Automation | Deferred until manual coordinator patterns are measured and stable |

## 1. Problem And Intent

The four-seat protocol now has strong safety rules: mailbox-first state, role
boundaries, operator GO requirements, product-oracle gates, capacity-max cycles,
and no-op evidence for idle seats. The remaining optimization problem is not
"add more protocol." It is knowing which protocol moves increase verified
progress and which ones add coordination churn.

This design adds a read-only effectiveness loop around the existing process.
After a coordinator or live-cycle wrap, one command should answer:

- what moved the wave,
- what consumed coordination,
- what blocked verified progress,
- which seats were active or correctly idle,
- what the next capacity board should optimize.

The tie-breaker is verified throughput. A process change counts as effective
only when it helps rows reach operator GO, moves the wave gate, completes the
product-oracle requirement, or reduces avoidable coordination without weakening
evidence.

## 2. Scope

Implement a report command:

```bash
.venv/bin/python scripts/protocol_effectiveness_report.py --wave 2
```

The command reads existing evidence and emits a structured JSON artifact:

```text
logs/protocol-effectiveness-2026-06-16-cycle01.json
```

It may also print a short Markdown-style summary to stdout for the coordinator
to paste into a handoff or routing note.

The report is observational. It never consumes mailbox cursors, sends mailbox
events, edits `docs/REMEDIATION-INVENTORY.md`, marks rows verified, claims locks,
or authorizes push/spend.

## 3. Inputs

The report uses only existing durable or current-state sources:

| Source | Purpose |
|---|---|
| Git history | Identify recent commits, HEAD movement, handoff/status/fix/verify commit patterns |
| `coordination/mailbox/sent/` | Read verify requests, verification reports, coordinator routes, status/no-op reports |
| `coordination/mailbox/seen/` | Report cursor positions and unread splits without consuming them |
| `docs/REMEDIATION-INVENTORY.md` | Read row id, severity, lane owner, wave, status, verifier, notes |
| `scripts/wave_gate_check.py N` | Capture executable gate blockers, product-oracle blockers, and pin failures |
| `coordination/locks/` | Detect lock blockers and contested files |
| `coordination/presence/` | Report seat liveness/staleness when available |
| `docs/HANDOFF-*.md` | Count handoff churn and detect uncommitted/stale draft risk conservatively |

Uncommitted handoff drafts are useful context but not durable truth. The report
may mention them as working-tree observations, but it must not use them as proof
of verified progress.

## 4. Outputs

The JSON artifact contains four top-level sections:

```json
{
  "artifact_kind": "protocol-effectiveness",
  "wave": 2,
  "generated_at": "2026-06-16T00:00:00+09:00",
  "head": "abc1234",
  "summary": {},
  "metrics": {},
  "classifications": [],
  "recommendations": []
}
```

`summary` is the coordinator-facing answer, for example:

```text
2 verified rows, 4 coordination-only events, Wave 2 still blocked by product
oracle and 9 executed pin failures.
```

`metrics` contains counters and timestamps that can be compared across cycles.

`classifications` contains event or row outcomes:

- `verified_progress`: a row reached required operator GO or the wave gate moved.
- `blocked_progress`: work was attempted but remains blocked by product oracle,
  open executed pins, push/lock/spend authorization, missing GO, or stale evidence.
- `coordination_only`: mailbox, handoff, cursor, or status changed without verified
  row or gate movement.
- `no_op_evidence`: a seat was checked and correctly idle.
- `stale_or_conflicted`: a handoff, mailbox, or git claim contradicted newer evidence.
- `unknown`: evidence was missing, ambiguous, or unparsable.

`recommendations` are conservative next-cycle hints. They are advice to the
coordinator, not authority. Examples:

- route product-oracle work before more status handoffs,
- keep an operator idle only when no verify request exists,
- avoid a third verification pass unless it asks a new question,
- resolve unread split before claiming all seats received the route,
- prefer no-lock work while push/lock authorization is absent.

## 5. Metrics

The first metric set stays small and defensible:

| Metric | Meaning |
|---|---|
| `verified_rows_delta` | Rows newly supported by operator GO during the cycle |
| `wave_gate_blocker_delta` | Change in gate blockers from baseline to wrap |
| `route_to_go_seconds` | Time from verify request or coordinator route to verification report GO |
| `mailbox_events_per_verified_row` | Coordination volume divided by verified progress |
| `handoff_commits_per_verified_row` | Handoff churn divided by verified progress |
| `seat_utilization` | Per-seat classification: active, verification, routing-only, no-op, unread, stale |
| `duplicate_verification_count` | Repeated verification on the same question without a new stated question |
| `stale_claim_count` | Claims corrected or contradicted by newer git/mailbox evidence |
| `blocked_reason_counts` | Product oracle, open pins, missing GO, lock, push, spend, unread split, parse error |

The report should not overfit on token counts or subjective effort. The initial
goal is enough signal to improve the next coordinator capacity board.

## 6. Evidence Rules

The report inherits the protocol's evidence discipline:

- Inventory `status=verified` is not proof by itself.
- `scripts/wave_gate_check.py` process state is not correctness proof by itself.
- A verified transition requires the expected operator verification-report GO
  plus row-specific executed evidence where the protocol requires it.
- Product-oracle completion requires a committed `logs/product-oracle-*.json`
  artifact with the required finite fields for the wave.
- Mailbox receipt proves mail state only, not completion.
- Missing or ambiguous evidence becomes `unknown`, never success.

Fail-closed behavior is part of the design. If the report cannot parse a row,
mailbox event, git range, or gate output, it records a parse error and refuses
to use that item as success evidence.

## 7. Operational Flow

The report is used at three points:

1. **Cycle start baseline**: optional, so latency and blocker deltas have an
   anchor.
2. **Cycle end wrap**: required for coordinator reconciliation or a live-cycle
   wrap.
3. **Handoff**: optional, linked or pasted into a handoff draft when a seat is
   transferred.

The coordinator flow is:

1. Capture or read the latest baseline.
2. Let the seats do normal protocol work.
3. Run `scripts/protocol_effectiveness_report.py --wave 2`.
4. Read the report before building the next capacity board.
5. Route based on bottlenecks, not merely newest mail.

The report does not become a new wave gate. It is a coordinator input.

## 8. Future Optimization Path

The implementation should avoid premature automation:

1. First pass: read-only report command and tests.
2. Second pass: coordinator capacity board cites the latest report during routing.
3. Third pass: propose rule consolidation only when repeated measured waste appears.
4. Fourth pass: automate recurring coordinator decisions only after the report proves
   the pattern is stable and low-risk.

This sequencing prevents a common failure mode: automating coordinator behavior
before knowing which behavior actually improves effectiveness.

## 9. Testing Plan

Testing should focus on parsers, classifiers, and fail-closed behavior.

Unit tests:

- mailbox filename and event-kind parsing,
- verification-report and verify-request classification,
- inventory row parsing,
- gate-output parsing,
- commit classification,
- conservative `unknown` classification for malformed evidence.

Fixture tests:

- a synthetic cycle with one `verified_progress`,
- a synthetic cycle with `coordination_only`,
- a synthetic cycle with `blocked_progress`,
- a synthetic cycle with `no_op_evidence`,
- a stale handoff or unread split classified as `stale_or_conflicted`.

Smoke check:

```bash
.venv/bin/python scripts/protocol_effectiveness_report.py --wave 2 --stdout-only
```

The smoke check must be read-only and emit valid JSON or a valid summary without
modifying mailbox cursors, inventory, locks, or handoffs.

Regression requirement:

- a test proves the report does not treat inventory `status=verified` alone as
  proof without the required evidence class.

## 10. Non-Goals

This design does not:

- rewrite the four-seat protocol,
- change role authority,
- change wave-gate rules,
- automate routing,
- create a new mandatory ceremony for every small handoff,
- replace `seat_status.py`, `continuation_readiness.py`, or `draft_handoff.py`,
- decide which open Wave 2 production defect to fix next.

## 11. Acceptance Criteria

The implementation plan should be considered complete when:

1. `scripts/protocol_effectiveness_report.py` exists and runs read-only.
2. It emits a structured `protocol-effectiveness` JSON artifact or stdout-only
   JSON summary.
3. It classifies verified progress, blocked progress, coordination-only work,
   no-op evidence, stale/conflicted evidence, and unknown evidence.
4. It records a concise recommendation list for the next capacity board.
5. It has focused parser/classifier tests plus at least one synthetic cycle test.
6. It has a regression test proving status-only `verified` rows are not treated
   as evidence.
7. The relevant Codex protocol docs mention the report as a coordinator input,
   not a gate or authority.

## 12. Open Review Question

The design intentionally keeps the first pass narrow. After the first report has
been used on at least one real cycle, decide whether the next spec should target:

- coordinator capacity-board integration,
- handoff-draft integration,
- rule consolidation based on measured waste,
- or recurring-decision automation.
