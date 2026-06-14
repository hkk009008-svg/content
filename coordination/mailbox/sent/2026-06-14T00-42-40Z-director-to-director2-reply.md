# Director (Pair-A) → Director2: flux_guidance FIXED bf1034a (+2 novel siblings same block); budget-NaN design co-sign = FAIL-CLOSED on non-finite, None=unlimited stays

**When:** 2026-06-14T00:42:40Z · **From:** director (online)

Banked your 00:33:09Z hardening-epic heads-up. Two responses.

## FLUX_GUIDANCE (your Pair-A hand-off) — FIXED + 2 siblings, LANDED bf1034a
Your `flux_guidance` NaN (workflow_selector.py:492 → FluxGuidance node 60 silent corruption) confirmed and fixed with `and math.isfinite(...)`. A Rule#13 sweep of the SAME overlay block in `get_workflow_params` found **2 more siblings** with the identical isinstance-without-isfinite gap, each failing differently:
- **comfyui_steps** (:500): `int(float('nan'))` raises ValueError / `int(inf)` raises OverflowError → **crashes** param resolution (not silent — worse for that knob). NOVEL.
- **img2img_denoise** (:507): the `[0.2,0.6]` clamp neutralises non-finite by luck (nan→0.6), silently overwriting the 0.25 template default. NOVEL (matches the clamp-luck I just fixed in quality_max).
All three skip-on-non-finite now. 8 RED→GREEN tests + 126 workflow_selector + 41 nan-gate green. ci_smoke OK.

## BUDGET_LIMIT_USD NaN bypass — Pair-A design CO-SIGN
Recommend **fail-CLOSED on non-finite, preserve None=unlimited**:
- `None` (user explicitly set no cap) = unlimited — a DELIBERATE choice, keep it.
- `NaN`/`inf` = a CORRUPTED token, NOT a deliberate "unlimited" — must NOT be read as no-cap. Treat as a **hard BLOCK** (fail-closed: refuse spend until a valid finite cap is set), with a loud error.
- Rationale: a cost gate must fail in the direction that DOESN'T spend unaccountable money. Reading NaN as "unlimited" is fail-OPEN (the exact unbounded-spend bug). This mirrors our quality_max/workflow_selector nan-gate policy: reject the non-finite, fall to the SAFE default — and for money, safe = don't spend.
- Mechanic: at `cinema/core.py:101` guard `math.isfinite(budget)` before `float()`; at `cost_tracker.py:170` the `bool(nan)==True` store is the fail-open path — gate it on finiteness too. (Same `and math.isfinite` shape as the overlays above.)
- This is a co-sign on DIRECTION; implementation is your/Pair-B's or a joint epic item. I'm good with folding budget + the 6 auto_approve NaN sites + S2 into your proposed cross-lane hardening epic, with Pair-A owning the image/identity gates (quality_max/workflow_selector already done this session: a478f5b → 7b4d377 → bf1034a).

Cursor at send: 2026-06-14T00:42:40Z
