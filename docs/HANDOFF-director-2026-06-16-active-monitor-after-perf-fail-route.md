# HANDOFF - Director (Pair-A), 2026-06-16 - active monitor after perf FAIL route

READ FIRST AS NEXT PAIR-A DIRECTOR. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Wrap

- Seat: `director` / Pair-A image, identity, realism.
- Write timestamp: `2026-06-15T18:30:29Z`
  (`2026-06-16T03:30:29+0900` Asia/Seoul).
- Current HEAD before writing:
  `45e53bbc coord(cursor): operator consume monitor updates`.
- Director consumed the Pair-B FAIL route plus operator/operator2
  active-monitor baselines and advanced its cursor through
  `2026-06-15T18:29:08Z`.
- The consumed route says `operator2` formally FAILed
  `6e8da868 fix(performance): gate capture before budget spend`; coordinator
  assigned the scoped repair to `director2`.
- Pair-A director remains implementation-idle, but now actively monitoring all
  seats per the user-principal's max-capacity directive. The user-principal also
  directed Codex to use subagents when they improve outcome, especially for safe
  parallel work.
- Active locks: `coordination/locks/.gitkeep` only.
- No committed Wave 2 `logs/product-oracle-*.json` artifact exists.
- Wave 2 remains `UNMET`: `verified=19`, `open=11`, executable selectors `24`,
  product-oracle blocker present. Current shared-worktree gate output may
  reflect in-flight Pair-B repair files until director2 commits and operator2
  verifies, so do not treat it as a committed GO.
- `scripts/ci_smoke.py` returns `OK` with existing advisory warnings only.
- Visible in-flight repair files in the shared worktree include
  `cinema/shots/controller.py`, `cost_tracker.py`,
  `performance/driving_video.py`, `tests/unit/test_budget_pre_spend_gate.py`,
  `tests/unit/test_cost_tracker.py`, and
  `docs/BRIEF-director2-2026-06-16-perf-phase-no-gate.md`; this director did
  not edit or stage those files.
- No production code, inventory row, lock, product-oracle artifact, or push is
  owned by this handoff/status.

## Capacity Board

| seat | status | reason |
|---|---|---|
| director | active monitor/support | Pair-A has no live row; director owns fast response for product-oracle identity/ArcFace review, Tier-A co-signs, or explicit Pair-A work. |
| director2 | active repair | Coordinator routed `perf-phase-no-gate` FAIL repair to Pair-B director2; visible uncommitted repair files suggest work is in flight. |
| operator2 | standby verifier | Operator2 owns the next formal verification once director2 sends the scoped fix request; operator2 also published an active-monitor standby handoff. |
| operator | standby/no-op | Pair-A operator has no Pair-A verify request and should not duplicate Pair-B Lane V. |

## Consumed Mailbox

- `coordination/mailbox/sent/2026-06-15T18-16-10Z-operator2-to-all-verification-report.md`
  - Formal FAIL for `perf-phase-no-gate`: Mode-B driving synth spend is not
    included in the pre-spend budget decision, and `PERFORMANCE_HALTED`
    continuation behavior needs an explicit director decision.
- `coordination/mailbox/sent/2026-06-15T18-18-10Z-coordinator-to-all-coordination.md`
  - Routes repair to `director2`; reserves `operator2` for re-verification;
    keeps Pair-A seats standby; no lock, pod, paid API, push, or product-oracle
    spend authorization.
- `coordination/mailbox/sent/2026-06-15T18-21-31Z-operator2-to-all-status.md`
  - Operator2 is standby for the next scoped fix and verify-request.
- `coordination/mailbox/sent/2026-06-15T18-23-03Z-operator-to-all-status.md`
  - Pair-A operator is standby/no-op.
- `coordination/mailbox/sent/2026-06-15T18-26-14Z-operator-to-all-status.md`
  - Pair-A operator also recorded the user-principal's active-monitor directive
    and remains role-safe standby.
- `coordination/mailbox/sent/2026-06-15T18-29-08Z-operator2-to-all-status.md`
  - Operator2 recorded active-monitor standby, noted visible in-flight repair
    files, and reaffirmed that no verification applies until a committed
    director2 fix plus verify-request exists.

## Evidence

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
797eec50 docs(handoff): operator2 active monitor standby
45e53bbc coord(cursor): operator consume monitor updates
1a158cec docs(handoff): operator active monitor baseline
14676d2f docs(handoff): operator standby after pairb route
6feb5397 docs(handoff): operator2 standby after perf fail route

$ CODEX_SEAT=director GIT_INDEX_FILE=.git/index-codex-director coordination/bin/consume-events director
cursor director: 2026-06-15T18:26:14Z -> 2026-06-15T18:29:08Z; unread now: 0

$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
WARNING: 176 doc-anchor drift(s) in docs/PROGRAM-MANUAL.md
R1 xfail-strictness ....... PASS
R2 invisible-green ........ WARN
R3 gate-executes-pins ..... PASS
R4 ci-runs-runxfail ....... PASS
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK

$ CODEX_SEAT=director GIT_INDEX_FILE=.git/index-codex-director .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2
HEAD 797eec50 docs(handoff): operator2 active monitor standby
UNREAD: 2 before consuming, then 0 after consume-events
Wave 2 gate: UNMET counts={'verified': 19, 'open': 11}
gate rows: 21; executable selectors: 24
PRODUCT ORACLE BLOCKER: missing Wave 2 product-oracle artifact
```

## Next Director Move

Keep monitoring rather than passively idling:

- Re-run seat status before substantive action and surface unread counts.
- If director2 lands the scoped `perf-phase-no-gate` repair, do not verify it;
  make sure operator2 gets/acts on the verify-request.
- If director2 heartbeat goes stale with no repair/status after the coordinator
  route, escalate through coordinator/user rather than taking Pair-B code.
- If product-oracle identity/ArcFace evidence appears, review promptly from the
  Pair-A director lane.
- If a Tier-A co-sign request appears, verify full source scope before signing.
- Use bounded subagents whenever they improve outcome or safe parallel coverage,
  without crossing seat ownership or touching shared files in parallel.

This handoff/status should commit only:

- `coordination/mailbox/seen/director.txt`
- `coordination/mailbox/sent/2026-06-15T18-30-29Z-director-to-all-status.md`
- `docs/HANDOFF-director-2026-06-16-active-monitor-after-perf-fail-route.md`
