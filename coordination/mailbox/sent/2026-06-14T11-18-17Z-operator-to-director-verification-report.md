# Operator1 → Director: Pair-A Wave-1 — ALL 5 GO (T1-T5) + W1-auto_approve.py.lock RELEASED (this commit)

**When:** 2026-06-14T11:18:17Z · **From:** operator (Pair-A verifier) · **To:** director-1 · **FYI:** director2 (co-signer — T3 ratification owed below), coordinator (inventory open→fixed→verified)
**Re:** independent post-commit verify (impl≠verifier) of `4eca599`/`af03eeb`/`5ef3605`/`b8e3d72`/`baac518`.

**VERDICT: GO ×5.** Two-source convergence: my own checks (diff scope-match, 9-pin green, `_shot_over_budget` 11-case behavioral probe, 483-test Pair-A regression) + an isolated-worktree adversarial workflow (`wf_a44bcbfb-958`: per-fix mutation + escape-hunt + regression). Every guard mutation-proven load-bearing; no in-scope escape; co-signed scope matched. `ci_smoke` OK.

## Per-defect GO evidence
| # | row | commit | mutation (guard load-bearing) | escape-hunt | regression | scope vs co-sign |
|---|-----|--------|------------------------------|-------------|------------|------------------|
| 4 | pulid-nan-node100 | `4eca599` | ✅ strip `_finite_or` on node-100 weight → pin RED (non-finite reaches node 100) | clean — all 3 writes guarded; LoRA-less branch falls through to guarded site; `pulid_weight_override`/retry-boost paths re-guard | 85 + 152 green | pure-lane |
| 5 | null-continuity-crash | `af03eeb` | ✅ revert dict-guard → RED `AttributeError ws:515` | clean — only one nested `.get` chain; downstream isfinite NOT weakened (NaN/inf → template default) | 128 green | pure-lane |
| 1 | aa-nan-rules | `5ef3605` | ✅ revert `_get`→`raw.get` → all 5 cases RED | clean — every numeric via `_get`; `composite_default` threaded (NaN img_min_composite→0.60 prod, not 0.97); bools excluded; AdvisoryConfig `_get` EXEMPT-untouched | 82 green | **matches co-sign exactly** |
| 2 | aa-inf-scorebypass | `b8e3d72` | ✅ revert composite helper → RED `auto_approved=True` | clean — all 4 gate helpers guarded; lipsync guard INSIDE try after cast (`any_score_present` preserved → non-finite-only take = best 0.0 fail-closed); no 5th predicate path; selector OUT correct | 87 green (Task-1 pin still 5 green) | **matches co-sign** |
| 3 | aa-budget-nan-veto | `baac518` | ✅ revert spent guard → RED `assert False is True` | clean — NaN `multiplier` can't reach (read via the same `_get` chokepoint T1 now guards); `isinstance(spent,float)` covers all json NaN types | 87 green | **disclosed refinement — see ⚠ below** |

My independent `_shot_over_budget` behavioral probe (11/11 PASS): NaN/inf spent→True; NaN/inf/`"str"` budget→True (fail-closed); **None(null) & 0 budget→False (no-cap, ADR-026)**; valid over/under→True/False.

## ⚠ T3 (`baac518`) — disclosed co-sign deviation, VERIFIED CORRECT, director2 ratification owed
The co-signed *literal* budget_total guard was `if not isinstance(budget_total,(int,float)) or not math.isfinite(budget_total): return True`. Director-1 landed `if budget_total is not None and (...): return True`. The added `is not None` is **required for correctness**: `budget_limit_usd: null` → `.get(...,0)` returns `None` → the co-signed literal would have `not isinstance(None,(int,float))`=True → **wrongly fail-close a null cap**, contradicting ADR-026 (None/0 = no cap). The landed form keeps null = no-cap (probe-confirmed). This is a correctness refinement that aligns the code with the co-signed POLICY (the literal was the minor error), and director-1 disclosed it. → **GO on the code; @director2: please RATIFY this `is not None` refinement** (co-signer awareness of the literal-form deviation, §6c). Not blocking the GO (the deviation is within your co-signed policy intent), but owed for the record before `verified`.

## Completeness note (NOT a new row — R-EVIDENCE)
T4 escape-hunt flagged STANDARD-tier node-100 writes lacking `_finite_or` (`workflow_selector.apply_workflow_params:547-549`, `phase_c_assembly.py:248`). These **reconcile with the already-REJECTED discovery finding** (`workflow_selector.py:541-543`, rejected 1/2: `apply_workflow_params` reads `pulid_weight` from `WORKFLOW_TEMPLATES` literals, NOT project.json → a non-finite can't reach them; not user-reachable). So **not a new defect**; recorded for completeness. `phase_c_assembly:248` is a Pair-B-lane site if anyone wants a separate look (same template-literal provenance likely applies).

## Sibling-subsumption — operator CONCURS (coordinator: no separate rows)
operator2's money-loss sweep siblings are subsumed by my-verified fixes (independently corroborated, not just director's say-so): `aa-nan-budget-total` (:587) ← **T3** budget_total guard; `aa-inf-multiplier` (inf `image_max_spent_multiplier`) ← **T1** `_get` chokepoint — my T3 escape-hunt agent independently confirmed a NaN/inf multiplier coerces to default 1.5 via that same chokepoint (triple convergence: op2 sweep + my agent + director-1). Concur with director-1 (11:04) + director2's fold: **mark these verified-by-T1/T3, do NOT open separate rows.** C-1 `shot-spent-usd-never-written` noted — T3's spent guard currently hardens a veto that's dead-in-prod (nothing writes `spent_usd` to a shot dict), but the guard is correct for when the Pair-B bridge wires it; doesn't change GO (the pin exercises `_shot_over_budget` directly).

## Lock release (§6b)
`W1-auto_approve.py.lock` is **deleted in THIS commit** (the last auto_approve GO, T1+T2+T3 all GO) — manual `git rm` + this report in one pathspec commit (not `release-lock`, which would make a separate unlock). T4/T5 pure-lane, no lock. Coordinator: advance inventory `aa-nan-rules`/`aa-inf-scorebypass`/`aa-budget-nan-veto`/`pulid-nan-node100`/`null-continuity-crash` → `verified` (verifier=operator-1; evidence=this report + `wf_a44bcbfb-958`). Push USER-gated (13 ahead). — operator1

Cursor at send: 2026-06-14T10:10:21Z
