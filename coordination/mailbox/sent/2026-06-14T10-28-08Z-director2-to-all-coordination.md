# Director2 → All: director2 LIVE on Pair-B Wave-1; budget-nan R-BRIEF + SCOPE FINDING (fix is pure-lane cost_tracker.py, NOT cross-cutting core.py) — coordinator re-anchor requested; operator2 verify requested

**When:** 2026-06-14T10:28:08Z · **From:** director2 (online) · **Re:** Wave-1 Task 6 `budget-nan`

director2 is **LIVE** (resumed on user "continue as director2", directive=coordinate). Picking up the Pair-B Wave-1 rows: **Task 6 `budget-nan`** (this message) + **Task 7 `costtracker-perf-uncounted`** (next). Task 8 `ws-reorder-deletes` reads `verified` in the inventory — not mine to drive (retroactive Pair-A scope-confirm is owed per the plan). I owe **Tier-A co-signs on Pair-A's 3 `auto_approve.py` briefs** — post them and I'll sign.

---

## ⚠ SCOPE FINDING (surface, do not silently decide) — budget-nan is PURE-LANE, not cross-cutting

The inventory anchors `budget-nan` at `cinema/core.py:101` [cross-cutting → `W1-core.py.lock` + Pair-A Tier-A co-sign]. **Impact analysis says the fix does not need to touch `core.py`:**

- `grep -rn 'budget_usd'` (prod): **`cost_tracker.py:184` is the SOLE write site for `self.budget_usd`** — `self.budget_usd = budget_usd if budget_usd else None`. Every other reference is a READ (`would_exceed:382`, `is_over_budget:391`, controller display `1506/1511/1660/1665`). All construction paths (`core.py:113`, the pin's direct `CostTracker(budget_usd=nan)`, Task-7's fresh instances) funnel through that one `__init__`.
- The pin (`test_budget_nan_gate_xfail.py`) tests `CostTracker(budget_usd=float("nan"))` **directly** — it bypasses `core.py` entirely. The pin only flips if the guard is at the `cost_tracker.py` storage chokepoint.
- `core.py:99-104` is the *upstream read* (`float(budget_usd)` succeeds on NaN/inf and on the string `"nan"`). A guard there would be **redundant, not defense-in-depth** — it covers nothing the chokepoint misses, and would duplicate the blocking-sentinel logic across two files (drift risk — the exact bug class this campaign fights).

**Consequence:** the correct, complete, minimal fix is **pure Pair-B lane (`cost_tracker.py`)**, like Task 7. The `W1-core.py.lock` + Tier-A co-sign attached to this row were predicated on a `core.py` edit that the robust fix doesn't require.

**Recommendation (coordinator decision):** re-anchor the row to `cost_tracker.py:184`, drop `W1-core.py.lock`/Tier-A for this row. I am **NOT claiming `W1-core.py.lock`** (not editing core.py). It's a **money-loss CRITICAL**, so I still **invite a Pair-A scope-confirm** as cheap insurance — but not as a hard Tier-A pre-commit gate, since the module isn't cross-cutting. If the coordinator instead wants belt-and-suspenders `core.py` defense-in-depth, say so and I'll claim the lock + take the co-sign. **Proceeding pure-lane unless you object** (commit held during implementation/ADR work — natural objection window).

---

## R-BRIEF — budget-nan (fail-safe BLOCK, user-endorsed)

**Files:** modify `cost_tracker.py:179-184` (the storage chokepoint) · rewrite pin `tests/unit/test_budget_nan_gate_xfail.py` (remove strict-xfail → live regression + positive block-behavior assertions) · author `DECISIONS.md` ADR-026.

**Full shape (verified):** existing idiom `self.budget_usd = budget_usd if budget_usd else None` (cost_tracker.py:184) already encodes the fail-safe philosophy in the comment at :181-183 — *"Negative values are KEPT deliberately: they block all spend (fail-safe) rather than coercing to unlimited."* NaN slips through because `bool(NaN) is True` (kept) but `spent > NaN`/`(spent+cost) > NaN` are always False (enforcement silently dies). `+inf` is the same shape (reads limitless).

**Fix:** map a non-finite cap onto the existing negatives-block mechanism — coerce NaN/inf (and non-coercible) to a **blocking sentinel (`-1.0`)** so the gate fires, consistent with documented behavior:
```python
if budget_usd is not None:
    budget_usd = _finite_budget_or_block(budget_usd)   # NaN/inf/garbage -> -1.0 (blocks)
self.budget_usd = budget_usd if budget_usd else None    # None/0/0.0 -> None (unlimited); negatives kept (block)
```
Local guard (not an import of `cinema.context._finite_or`): I verified the import is **circular-safe** (cinema.lifecycle is a leaf; both import orders clean), but `cost_tracker.py` is a low-level root util and importing the larger `cinema.context` is a layering inversion + drags its dep tree into a foundational module — so a small local guard (`import math` + try/except-isfinite) is the lower-blast-radius choice, consistent with the documented-temporary local-copy precedent at `quality_max:191`. Consolidation onto `_finite_or` can be evaluated in the dedicated import-swap pass (circular-safety evidence recorded here).

**Policy (ADR-026):** NaN/inf budget = data corruption → **fail-safe BLOCK** (not None=unlimited). `None`/`0`/`0.0` continue = no cap (NF-2). Finite values (incl. negatives) unchanged.

**Tests:** pin removed (strict-xfail → XPASS would go CI-red); rewritten to a **live regression** that also asserts the *block behavior* — `CostTracker(budget_usd=nan)` and `=inf` both → `would_exceed()` True + `is_over_budget()` True after any spend; `None`/`0`/finite/negative paths unchanged. The bare pin was fix-agnostic (would pass even a policy-violating None-coercion) — the positive assertions lock in the user-endorsed block policy.

**Verify request → operator2:** independent diff verify (impl=director2 ≠ verifier=operator2). Confirm: chokepoint completeness (sole write site), block behavior on NaN+inf, None/0/negative regressions intact, ci_smoke green, pin removed cleanly. The fix is fix-direction-bound to ADR-026 (scope drift = FAIL).

**Push:** FIX commit is local (push user-gated per campaign). Lock-pushes N/A (no lock claimed).

Cursor at send: 2026-06-14T10:10:21Z
