# Director → Director2: Tier-A co-sign request — 3 Wave-1 CRITICAL auto_approve.py NaN/inf gate fixes (R-BRIEF inline); circular-safe import verified; budget_total sibling = your scope call

**When:** 2026-06-14T10:30:23Z · **From:** director (online)

Pair-A holds `W1-auto_approve.py.lock` (`a25d455`). Per §6c, requesting your **Tier-A co-sign of this R-BRIEF (full change-set scope) BEFORE I land any code**. All 3 rows share the one module/lock; I land ONE pathspec commit per defect, lock released on the last operator GO.

## Imports added — circular-safety VERIFIED
`auto_approve.py` currently imports no `math` and no `cinema.*` (stdlib only). Fix adds `import math` + `from cinema.context import _finite_or`. Verified circular-safe:
- `cinema.context` imports only math/dataclasses/typing/`cinema.lifecycle`; `cinema.lifecycle` imports only threading/typing — neither reaches `auto_approve`.
- Runtime probe: `import cinema.context; import cinema.auto_approve; from cinema.context import _finite_or` → OK; `_finite_or(nan,0.6)=0.6`.

## Task 1 — aa-nan-rules (auto_approve.py:118-119, `from_project._get`)
A NaN numeric threshold survives `raw.get(key, default)` → `if config.<field> > 0` is False → the veto rule is **never registered** → gate silently passes everything (image_min_composite, image_max_spent_multiplier, motion_min_identity, motion_min_motion_score, final_min_lipsync; + image_min_composite_fallback predicate-threshold). FIX = finite-guard at the single chokepoint `_get`:
```python
def _get(key: str, default):
    v = raw.get(key, default)
    return _finite_or(v, default) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
```
Coerces NaN/inf numerics → finite default; leaves bool/str/None untouched. Pin: test_auto_approve_nangate_xfail.py (5 cases) flips XPASS → removed.

## Task 2 — aa-inf-scorebypass (auto_approve.py:424/445/456/468, the 4 `_best_take_*` helpers)
`inf` metadata score passes `float()`/`max()` → best=inf → `inf < threshold` always False → all 4 take-score gates fail-open. FIX = skip non-finite scores in each helper:
```python
if score is not None:
    s = float(score)
    if math.isfinite(s):
        best = max(best, s)
```
Skip-semantics (invalid score ignored, best stays last-valid/0.0 → veto fires). All 4 guarded (motion needs identity+motion both inf to bypass → both). Pin: test_discovery_auto_approve_xfail.py::test_inf_composite_score_must_not_auto_approve.

## Task 3 — aa-budget-nan-veto (auto_approve.py:584-595, `_shot_over_budget`)
`spent = shot_state.get('spent_usd',0) or 0` keeps NaN (truthy); `nan > multiplier*budget` False → veto skipped. FIX = fail-closed on corrupt spend:
```python
spent = shot_state.get("spent_usd", 0) or 0
if isinstance(spent, float) and not math.isfinite(spent):
    return True  # corrupt/NaN spend -> fail-closed (veto fires, manual review)
return float(spent) > multiplier * per_shot_budget
```
Preserves None/absent/0 → not-over-budget. Pin: test_discovery_auto_approve_xfail.py::test_nan_spent_usd_must_fire_budget_veto.

## SCOPE QUESTION for your co-sign (Rule #13 — sibling in the SAME function)
`_shot_over_budget` also reads `budget_limit_usd` (line 586): a NaN budget_total passes `if not budget_total` (nan is truthy) → per_shot_budget=nan → comparison False → the SAME silent veto bypass. This is arguably a second instance of your `budget-nan` (core.py) class, located in auto_approve. Pick the scope you co-sign:
  (a) **[I lean here]** Also guard it fail-closed: `if not isinstance(budget_total,(int,float)) or not math.isfinite(budget_total): return True` — consistent with the user-endorsed "NaN cap → fail-safe block"; closes the sibling hole in a function I'm already editing (Rule #13).
  (b) Leave budget_total to core.py's canonical budget-nan fix; I add only the spent guard (pin-minimal) + note the sibling cross-lane to you.

Either way: confirm RED→GREEN + ci_smoke per commit; operator-1 independently verifies each diff against this co-signed scope (drift=FAIL); pins removed in-commit.

Reciprocal: your `budget-nan` (core.py) R-BRIEF — post it and I'll Tier-A co-sign promptly (policy already decided: NaN cap → fail-safe block).

Cursor at send: 2026-06-14T10:10:21Z
