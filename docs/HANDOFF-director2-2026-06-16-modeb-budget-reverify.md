# HANDOFF - director2 - 2026-06-16 - Mode-B budget repair ready for Lane V

READ FIRST AS `director2` / Pair-B director. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State

Timestamp: `2026-06-15T18:34:02Z` (`2026-06-16T03:34:02+0900` Asia/Seoul).

Current HEAD before this handoff:

```text
fb86ef4e docs(perf): sync mode-b budget gate notes
04cc0c78 fix(performance): gate mode-b driving budget envelope
b4c7d02f docs(handoff): director active monitor capacity
797eec50 docs(handoff): operator2 active monitor standby
45e53bbc coord(cursor): operator consume monitor updates
```

`seat_status.py director2 --wave 2`:

```text
HEAD fb86ef4e docs(perf): sync mode-b budget gate notes
vs origin/main: 27 ahead, 0 behind
director2 unread: 0
cursor: 2026-06-15T18:30:29Z
peers: director/operator/operator2 ONLINE
Wave 2: UNMET counts={'verified': 19, 'open': 11}; product-oracle artifact missing.
```

## What Landed

`04cc0c78 fix(performance): gate mode-b driving budget envelope`

- Adds a combined pre-spend gate for Mode-B performance capture before any paid
  driving synth or performance dispatch.
- Adds `CostTracker.would_exceed_cost(...)` for multi-call cost envelopes.
- Adds `performance.driving_video.estimate_driving_face_cost(...)`, shared by
  the gate and `_cost_log`.
- Converts the Mode-B combined-cost pin to a live regression.
- Keeps `PERFORMANCE_HALTED` as intentional pause/review behavior, not
  cancellation.

`fb86ef4e docs(perf): sync mode-b budget gate notes`

- Syncs `docs/PROGRAM-MANUAL.md` anchors and budget-gate wording.
- Keeps `perf-phase-no-gate` open in `docs/REMEDIATION-INVENTORY.md` pending
  operator2 GO.

## Evidence

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_budget_pre_spend_gate.py \
  tests/unit/test_cost_tracker.py::TestApiCostUsdCompleteness \
  tests/unit/test_cost_tracker.py::TestEstimatedCostBudgetGate \
  -q
-> 20 passed in 1.65s

env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_budget_pre_spend_gate.py::TestPerformancePreSpendBudgetGate::test_mode_b_refuses_when_combined_driving_and_engine_cost_exceeds_budget \
  --runxfail -q
-> 1 passed in 1.60s

env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py docs/PROGRAM-MANUAL.md
-> All anchors checked - no drift.

env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; R2 invisible-green advisories only.

env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
-> UNMET counts={'verified': 19, 'open': 11}; product-oracle artifact missing; unrelated open clusters remain.
   The prior Mode-B perf failure is gone from the tail: 15 failed, 57 passed.
```

Subagent capacity used:

- `money-gate-reviewer` sidecar returned NITS: no remaining Mode-B
  pre-dispatch bypass; continuation behavior is a product choice and now
  pinned/documented; stale manual anchors were folded. It also noted
  pre-existing adapter `_cost_log(... except Exception: pass)` undercount risk,
  outside this pre-spend row unless the coordinator files/routes it.

## Mailbox

Verify request sent:

`coordination/mailbox/sent/2026-06-15T18-34-02Z-director2-to-operator2-verify-request.md`

No lock was held or needed. No push performed.

## Next

- `operator2`: run Lane V on `04cc0c78` plus `fb86ef4e`.
- `director2`: stand by for GO/NITS/FAIL. If NITS/FAIL, repair only the scoped
  `perf-phase-no-gate` issue and re-request verification.
- Coordinator should reconcile inventory only after operator2 GO.
