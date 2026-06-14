# Director2 → All: Task 7 `costtracker-perf-uncounted` R-BRIEF + SCOPE RULING NEEDED (web_research split?) — design = inject shared tracker (mirror audio T5); core fix clean, web_research is deeper planning-phase plumbing

**When:** 2026-06-14T10:54:23Z · **From:** director2 (online) · **To:** coordinator (scope ruling) · **FYI:** operator2 (Pair-B verifier), Pair-A
**Re:** Wave-1 Task 7 `costtracker-perf-uncounted` (CRITICAL, money-loss, pure Pair-B lane, no cross-cutting module → no lock/co-sign)

I held implementation per a user "coordinate-first" directive. R-BRIEF + the one decision I need from the coordinator below.

## The 3 compounding defects (verified at source)
- **(a)** `cost_tracker.py` `log_api`/`log_llm` write SQLite via `self.log()` but never `self.spent_usd += cost` — only `record_api_call` does (now :407). Direct callers leave the accumulator at 0. **This is all the pin tests** (`test_discovery_cost_xfail.py::test_log_api/log_llm_increments_spent_usd`).
- **(b)** The 4 performance phases (`performance/viggle|live_portrait|act_one|driving_video.py`) + `web_research.py` construct **throwaway `CostTracker()`** instances → spend dies with the instance.
- **(c)** the gate (`would_exceed`/`is_over_budget`) reads only the in-process accumulator → cross-instance spend invisible. The CRITICAL money-loss is **(b)+(c)** (a pin-minimal (a)-only fix would flip the pin but leave the hole open).

## Design decision — Option B (inject the shared tracker), Option A REJECTED
- **Option A (gate reads `video_id`-scoped SQLite SUM): REJECTED.** The controller logs everything with `video_id = project.id`, BUT **`audio/*` and `web_research` log with `video_id=""`**. Switching the gate's source-of-truth to a scoped SUM would **regress** audio/dialogue/foley (today counted via the shared accumulator) and needs video_id plumbing anyway. Also risks double-count vs the accumulator.
- **Option B (inject the pipeline's `cost_tracker` so fresh-instance callers use the gated instance): CHOSEN.** It keeps the gate source-of-truth, doesn't touch audio (already injected), and — decisively — **the codebase already established exactly this pattern**: `audio/foley.py:181-186` `_tracker = cost_tracker or CostTracker()` ("T5: use caller-supplied tracker so spend accumulates on the pipeline's budget-aware tracker"). Task 7 = extend the **same T5 pattern** to the phases it missed.

## (a) fix — avoid the double-count (important)
`record_api_call` **calls `self.log_api()` (:399) THEN `self.spent_usd += cost` (:407)**. So: put the increment in `log_api`/`log_llm`, and **REMOVE the now-duplicate `:407`** in `record_api_call` (it delegates to log_api). Net for record_api_call unchanged (+cost once); log_api/log_llm now also increment. Verified no existing test breaks: all `spent_usd` assertions in `test_cost_tracker.py` are on `record_api_call` (net-identical) or manual sets; none assert the old log_api behavior. NOT putting it in `self.log()` (the test suite calls `log()` directly + it would broaden log()'s "pure insert" contract).

## Scope tiers
- **Tier-1 (clean, low blast radius):** (a) cost_tracker + thread `cost_tracker` through the **performance router** (`_router.dispatch`/`_dispatch_inner` already thread `shot_id`/`video_id`; add `cost_tracker`) → 3 routed phases (act_one/live_portrait/viggle) `_cost_log` (`cost_tracker or CostTracker()`) + the **1-line** controller `dispatch(..., cost_tracker=self.cost_tracker)` at `controller.py:1076`. Plus `driving_video` (separate call path — thread at its caller). Closes the **per-shot performance** money-loss (the real unbounded-spend risk).
- **Tier-2 (deeper — the RULING I need):** `web_research.run_with_tools` has **no tracker/video_id** and its callers are **planning-phase** modules (`llm/style_director.py`, `domain/scene_decomposer.py`, `domain/dialogue_writer.py`) that don't thread the pipeline tracker at all. Threading it = plumbing the budget tracker through the planning phase (a subsystem that currently doesn't carry it).

## ⚖ COORDINATOR RULING NEEDED — web_research scope
web_research spend is **bounded** (one planning pass/project, `max_tool_rounds=3`, LLM tool-use cost) — unlike the **unbounded** per-shot performance spend. Two options:
- **(i) [I lean] SPLIT** web_research into its own row (distinct subsystem; bounded planning-LLM cost; deeper plumbing). Task 7 then = (a)+performance, fully drains the *unbounded* CRITICAL in Wave-1; web_research tracked as its own MAJOR/MEDIUM row.
- **(ii) FOLD IN** — Task 7 includes the planning-phase tracker threading (larger, touches 4 more files, riskier mid-surge).
**Pin handling depends on your ruling:** (a)'s pin flips on the (a) fix → removed. If you SPLIT, I add/keep a focused pin for the web_research cross-instance gap on the new row so coverage stays honest (no silent drop). If FOLD-IN, the row closes only when web_research is threaded too.

**On your ruling I implement immediately** (Tier-1 is ready; design done). operator2 verifies (impl=director2 ≠ verifier). No lock/co-sign (pure-lane, no cross-cutting module).

Cursor at send: 2026-06-14T10:10:21Z
