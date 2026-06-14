# Coordinator → All: ruling: web_research SPLIT (MAJOR) + Wave-1 closes on planned 8 (C-1 Wave-2 lead) + Task-7 RELEASED to director2 in-lane + pin obligations to operator2

**When:** 2026-06-14T12:04:33Z · **From:** coordinator (online)

**From:** coordinator (Session-9, LIVE) · **To:** all · **Kind:** decision
**Evidence:** `logs/discovery-wf_e370ed39-bca.json` (read-only verify fan-out wf_e370ed39-bca, 11 Explore agents; 10/11 premises confirmed). **Inventory:** committed `e00f6c2`. **User-blessed** 2026-06-14 ("proceed with recommendation").

## Ruling
1. **Wave-1 closes on its planned 8-row scope.** Do NOT expand the gate for mid-wave sweep finds (the "infinite wave" failure). On `costtracker-perf-uncounted` (Task 7) verified-GO → gate MET; the milestone is announced PRECISELY ("the 8 planned CRITICAL rows are verified", NOT "all money-loss closed"). `shot-spent-usd-never-written` (C-1) is the **Wave-2 lead**.
2. **`web_research` SPLIT** out of Task 7 → own row `web_research-uncounted`, severity **MAJOR**. Premise correction (P1 REFUTED): `run_with_tools` is called once-**per-scene** by `scene_decomposer`/`dialogue_writer` (only `style_director` is 1/project) → spend **scales with scene count**, NOT bounded. SPLIT is justified by blast-radius isolation (P6: deeper planning-phase plumbing), not by "bounded". Do not file it as MEDIUM.
3. **`aa-nan-budget-total` = NO row** — subsumed by `baac518` `is not None` guard (ratified).

## Task 7 — RELEASED to director2 (in-lane implement now)
Scope (verification-confirmed): **(a)** add `self.spent_usd += cost` to `log_api` AND `log_llm`, and **REMOVE the now-duplicate `record_api_call:407`** (P3: `record_api_call:399` already calls `log_api`, so leaving :407 double-counts). **(b)** thread the pipeline's shared `cost_tracker` through the 4 performance phases (Option-B, the `audio/foley.py:185` T5 pattern — P5-confirmed) via `_router.dispatch`/`_dispatch_inner` → `controller.py:1076` + the `driving_video` caller. **Option-A (SQLite-SUM gate) stays REJECTED** — P4 confirms the gate is in-process by documented design; a SUM gate is a redesign that regresses audio.
- **pure Pair-B lane — no cross-cutting lock, no Tier-A co-sign** (cost_tracker.py is not in the first-mover sequence; verified).
- Task 7 fixes **visibility only**. The missing pre-spend gate on the perf path is a DISTINCT row (`perf-phase-no-gate`, Wave-2) — do not scope-creep it into Task 7.
- **operator2 verifies** (impl=director2 ≠ verifier). The existing pins `test_log_api_increments_spent_usd` / `test_log_llm_increments_spent_usd` (test_discovery_cost_xfail.py) flip XPASS on the (a) fix → remove them per the file's protocol.

## Assignments / new Wave-2 rows (filed `e00f6c2`)
- **C-1 `shot-spent-usd-never-written` (CRITICAL) → director2 / Pair-B.** The per-shot veto at `auto_approve.py:627` is DEAD in prod (zero production writers of `spent_usd` to a shot dict; grep-confirmed). Bridge = `CostTracker.get_shot_spent(shot_id)` = SQLite `SUM(cost_usd) WHERE shot_id=?`, injected into the gate loop before `check_gate`. Wave-2 lead.
- **C-2 `spent-usd-reset-on-resume` (MAJOR, design-open)** — `spent_usd=0.0` on every construct, no rehydration on resume. Needs a direction-pick before a pin (seed from `SUM(cost_log) WHERE video_id`). cross-lane checkpoint+core; director2 may own the Pair-B portion.
- **`charmgr-cost-fresh-instance` (MAJOR)** + **`perf-phase-no-gate` (MAJOR)** + **`web_research-uncounted` (MAJOR)** — all Wave-2, Pair-B.

## R-VERIFY-TIER(B) pin obligations (operator2 / Pair-B, this session)
These were confirmed-and-left-unfixed; each needs a strict-xfail pin OR a labeled exemption so CI carries it, not memory:
- **pin owed:** `shot-spent-usd-never-written`, `web_research-uncounted`, `charmgr-cost-fresh-instance` → land strict-xfail pins (own the wording; no vacuous/suppressive pins).
- **labeled-exempt (no pin owed):** `spent-usd-reset-on-resume` = design-open (direction-pick first); `perf-phase-no-gate` = test-infeasible (precheck inside ~600-line `generate_performance_take`, needs full ShotController harness — cf. `lipsync-precheck-cascade-gap`).

## Push
Coordinator commits (`1406865` evidence, `e00f6c2` inventory) are local; **push is user-gated** — not pushing unilaterally. Will surface the Wave-1-MET milestone for a push decision when Task 7 verifies.

Cursor at send: unknown
