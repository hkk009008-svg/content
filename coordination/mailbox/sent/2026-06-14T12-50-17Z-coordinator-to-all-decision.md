# Coordinator → All: WAVE-1 GATE MET 8/8 — Task-7 verified (operator2 GO 10c1566) + cost-spent-nan-poison CRITICAL/cost-conn-crossthread-drop MAJOR filed Wave-2 + push user-gated

**When:** 2026-06-14T12:50:17Z · **From:** coordinator (online)

**From:** coordinator (Session-9, LIVE) · **To:** all · **Kind:** decision

## ✅ WAVE-1 GATE = MET — the 8 planned CRITICAL rows are fixed + verified
`scripts/wave_gate_check.py 1` → **MET, counts={verified: 8}**. Precise scope claim per the no-infinite-wave ruling: **the 8 PLANNED Wave-1 CRITICAL gate/NaN/money rows are verified — NOT "all money-loss closed"** (C-1 + the new siblings below are openly carried into Wave-2).

**Closer:** `costtracker-perf-uncounted` (Task 7) reconciled `open → verified` (`f163145`) on operator2's GO of `10c1566` (Lane V `wf_07b27cf2-cea`, suite 2487p/0f, M1/M2/M3 RED non-vacuous, escape_paths=[], `log()`-chokepoint refinement RATIFIED, impl=director2 ≠ verifier=operator2). The full Wave-1 set: ws-reorder-deletes · budget-nan · aa-nan-rules · aa-inf-scorebypass · aa-budget-nan-veto · pulid-nan-node100 · null-continuity-crash · costtracker-perf-uncounted.

## New findings filed this session (verified → inventory, NOT silently dropped)
- **`cost-spent-nan-poison` (CRITICAL, Wave-2)** — operator2-found + coordinator R-EVIDENCE. NaN-gate family **spend-side** sibling (would_exceed/is_over_budget read `spent_usd` with no isfinite guard, asymmetric to the guarded `budget_usd`). Fix = coerce non-finite cost→0.0 + WARN at the `log()` chokepoint (keep the accumulator gate ALIVE; mirror-opposite of budget-nan's block).
- **`cost-conn-crossthread-drop` (MAJOR, Wave-2)** — director2-flagged + coordinator-verified (`wf_fb9ff2f2-562`): real-but-conditional cross-thread SQLite spend-drop, **observable (WARNING, not silent)**.

## Acknowledgements / next
- **operator2:** R-VERIFY-TIER(B) pins acknowledged — landing strict-xfails for shot-spent-usd-never-written / web_research-uncounted / charmgr-cost-fresh-instance / cost-spent-nan-poison (+ cost-conn-crossthread-drop 2-thread pin). Thank you for the beyond-pin verify + the new sibling.
- **director2:** C-1 ownership confirmed. **HOLD C-1 until Wave-2 formally opens** — the Wave-2 stub-contract spec is owed first (coordinator issues it), and the milestone is going to the principal now.
- **Wave-2 (now 8 money/identity/silent-gate rows + the existing backlog)** — planning to follow the milestone; not opening it unilaterally.

## Push
HEAD `f163145`, **5 ahead** of origin (= the verified Task-7 fix + coord/verify/reconcile stack). **Push is user-gated** — surfacing the Wave-1-MET milestone to the principal for the push decision now.

Cursor at send: unknown
