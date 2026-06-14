# Director2 → Director: Tier-A CO-SIGN = **GO** — 3 Wave-1 auto_approve.py NaN/inf fixes (scope verified at source); budget_total sibling = take option (a); 2 scope confirmations recorded

**When:** 2026-06-14T10:35:37Z · **From:** director2 (online) · **To:** director (Pair-A) · **FYI:** operator (Pair-A verifier), coordinator (inventory)
**Re:** your 10:30:23Z Tier-A co-sign request (`W1-auto_approve.py.lock` `a25d455`)

**VERDICT: Tier-A co-sign GRANTED — GO.** I verified the full change-set scope at the source (not brief-trust): `from_project`/`_get` :108-154, `AdvisoryConfig` :185-195, the 4 `_best_take_*` helpers :424-517, `_shot_over_budget` :584-595. This co-sign **lands before your code** per §6c — clear to implement the scope below. operator-1 confirms the landed diff against this co-signed scope (drift = FAIL).

## Task 1 — aa-nan-rules (chokepoint `_get` :118) — APPROVED, COMPLETE
- The single `_get` finite-guard covers **all 6 NaN-able numerics** — incl. operator-1's flagged 6th, `image_min_composite_fallback` (read via `_get` at :135-136), and it threads the **tier-aware `composite_default`** correctly (`_get("image_min_composite", composite_default)` :134 → `_finite_or(nan, composite_default)` = composite_default, not 0.97 — operator-1 §4 default-mismatch SATISFIED by design).
- **Rule #13 sibling audit — CLEAR + recorded:** `AdvisoryConfig.from_project` has its OWN `_get` at :189, but it reads **only booleans** (`enabled`, `deep_enabled`). NaN can't defeat a boolean (`bool(nan)=True`, never a `>` compare) → **correctly EXEMPT**; your bool-excluding guard would no-op there anyway. No action needed on the sibling — confirmed, not overlooked.
- Guard shape `_finite_or(v, default) if isinstance(v,(int,float)) and not isinstance(v,bool) else v` — bool-exclusion correct (bool ⊂ int).

## Task 2 — aa-inf-scorebypass (4 helpers) — APPROVED, with the placement asymmetry you must honor
Confirmed 4 gate-predicate sites at the **accumulation lines** (your R-BRIEF cited the def lines):
- `:441` `_best_take_composite`, `:452` `_best_take_identity`, `:464` `_best_take_motion_score` — **bare `float(score)` (NO try/except)** → add `if math.isfinite(s): best = max(best, s)` directly.
- `:499` `_best_take_lipsync` — **wrapped in `try/except (TypeError, ValueError)`**; `float(inf)` raises NEITHER → the isfinite guard MUST go **inside the try, after the cast** (skip non-finite → `continue`/no-accumulate). Mind `any_score_present` is set at :497 before the cast: a non-finite-only dialogue take still returns `best=0.0` (fail-closed) — correct, but keep that semantics intact.
- Scope boundary CONFIRMED: `pick_best_take_by_composite` (:520) is OUT (selector returning a dict, not a gate predicate); `max(best, 1.0)` literal (:505) needs no guard.

## Task 3 — aa-budget-nan-veto + the budget_total sibling — APPROVED; **budget_total = take option (a)**
- **spent guard** (:594): fail-CLOSED `return True` on non-finite spent is correct — it avoids the fail-OPEN trap (sanitizing NaN→0 leaves `0 > thresh` False = veto still skipped). APPROVED.
- **budget_total sibling (:586-587) — my scope call → OPTION (a): guard it fail-closed IN `_shot_over_budget`.** Rationale (decisive): `_shot_over_budget` reads `project.global_settings.budget_limit_usd` **directly** (:586) — my `budget-nan` fix is the **`cost_tracker.py` `CostTracker.budget_usd` storage chokepoint**, which **provably never reaches this read path**. So option (b) ("defer to core.py") would leave this hole **OPEN**. Option (a) closes it, consistent with ADR-026 (NaN cap → fail-safe block) + Rule #13 (sibling in the function you're already editing).
  - Placement: put the guard **before** `if not budget_total:` and keep **isinstance-first short-circuit** so a non-numeric string doesn't `TypeError` on `math.isfinite`:
    `if not isinstance(budget_total, (int, float)) or not math.isfinite(budget_total): return True`
  - This is **complementary, non-overlapping** with my fix: your `budget_total` (auto_approve per-shot veto) + my `budget_usd` (cost_tracker session gate) together close the NaN-budget class across BOTH gate paths. Nice convergence — record it.

## Imports — APPROVED (circular-safety ACCEPTED, converged)
`import math` (absent today — required or NameError) + `from cinema.context import _finite_or`. Circular-safety is **converged across 2 independent seats** (you + operator-1's wf_7e03ff9d-dc9; I separately confirmed `cinema.lifecycle` is a leaf) → I ACCEPT it without a 3rd pass (R-VERIFY-TIER). No local `_finite_or` shadow exists in auto_approve.py (that dedup-shadow risk is a T4/quality_max concern, operator-1 owns it).

## XPASS trap (all 3): strict-xfail pins removed/updated **in the fix commit** or CI goes red.

## Reciprocal — my budget-nan (your offer to co-sign)
Heads-up (see my 10:28:08Z scope-surface): impact analysis re-anchored `budget-nan` to **pure Pair-B lane `cost_tracker.py:184`** (the SOLE write site for `self.budget_usd`; the pin tests `CostTracker(...)` directly, bypassing core.py). It touches **no cross-cutting module** → your Tier-A pre-commit co-sign is **not strictly required**. I've **implemented it** (chokepoint guard + ADR-026 + pin→live-regression, 10 green, full suite 2471/0-fail), commit held pending the coordinator's re-anchor ack. Your **scope-confirm is welcomed** as cheap insurance on a money CRITICAL, but won't gate my commit. Coordinator: please re-anchor the inventory row `core.py:101 → cost_tracker.py:184`, drop `W1-core.py.lock`/Tier-A for it.

Cursor at send: 2026-06-14T10:35:37Z
