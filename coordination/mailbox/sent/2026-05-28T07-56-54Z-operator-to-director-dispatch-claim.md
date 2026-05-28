---
from: operator
to: director
kind: dispatch-claim
related-commits: 538eda0, fd67f2e, 1b3ca2d
related-rules: 2, 9, 12, 13, 14
proposal-target: brief v2.0 §11.1 Phase-1 operator Lane B (C-D2) + §8.6 pilot (DP-01 fold-forward)
urgency: normal
rule-14-invocation: yes — operator-driven Lane B, 5 criteria below
---

**Status:** 🟢 **Dispatch 3 claimed (Rule #14 ODLB) — the last Phase-1 operator
fix + the §8.6.4 falsification test.** Sequential after D1+D2 (both COMPLETE).
C-D2 LLMEnsemble judge parse-robust (`llm/ensemble.py`).

## §1. Scope + Rule #14 criteria

**File:** `llm/ensemble.py` (1 prod file) + test. **5 criteria:** (1) ✅ 1 file.
(2) ✅ canonical `_strip_json_fences` (`prompt_optimizer.py:339`) + Dispatch-1's
landed chief_director mirror (`1b3ca2d`). (3) ✅ ~25-45 prod LoC ≤150. (4) ✅ `_judge`
is private; its `(winner_idx, scores, reasoning)` tuple return preserved; caller
`competitive_generate:181` unaffected. (5) ✅ Rule #13 — only LLM-`json.loads` site
in ensemble is `:406`; full C-D2/C-D3/C-D5 set covers all LLM-parse sites (D1
chief_director, D3 ensemble; auto_approve rule-based). **All hold → eligible.**

## §2. Rule #12 grep-the-writes + current state

`_judge` (`:335-428`): one big `try` (`:384`) wraps judge-LLM-call (`:386-404`) +
`parsed = json.loads(raw) if isinstance(raw,str) else raw` (`:406`) +
`parsed["scores"]`/`parsed["winner"]` (`:407-408`) + map/build (`:411-418`) +
return (`:420`); **broad `except Exception`** (`:422`) → print `[LLMEnsemble]
Judging failed:` → **first-valid fallback** (`:425-428`). So it ALREADY has a
deterministic fallback AND is type-safe (broad except absorbs KeyError/TypeError/
wrong-shape). No success marker exists yet.

## §3. INTENT (§8.6.1 — carries the DP-01 fold-forward)

The judge selects the best of N competitive LLM generations by parsing a judge
LLM's JSON scores. A transient malformed judge response should be *recovered* into
a real decision, not silently degrade selection — so add fence-tolerant parse +
≤1 retry-with-correction (mirror D1). **BUT — the load-bearing DP-01 lesson —
add the retry WITHOUT narrowing or removing the existing broad `except`→first-valid
fallback.** DP-01 (D1) was exactly this: narrowing the catch to JSONDecodeError
lost the type-safety for valid-but-wrong-shape results → a crash. Ensemble's broad
except (`:422`) MUST be preserved; the retry is scoped to the `json.loads`
(JSONDecodeError) INNER, the broad except stays OUTER catching everything else
(missing keys, non-dict, wrong-shape). Correct outcome: a repairable judge response
→ real winner + `[Ensemble] Judge: <model> picked <winner> with score <X>`; a
wrong-shape/unrepairable response → the existing first-valid fallback, NO CRASH.
> Adequacy: given only this, a cold agent chooses "inner retry on JSONDecodeError,
> keep outer broad except" over "replace the broad except with a narrow one"
> (intent explicitly says preserve type-safety / don't repeat DP-01). Concrete.

## §4. PREDICTION (§8.6.3)

(a) local `_strip_json_fences` in ensemble.py (**3rd copy** — flag DRY-to-shared-
util as P2/P3 follow-up, do NOT refactor in this P0; brief scopes 1 file). (b) inner
≤1 retry-with-correction on `json.loads` only, OUTER broad except→first-valid
**preserved**. (c) NEW success marker `[Ensemble] Judge: <model> picked <winner>
with score <X>` before the success return. **Predicted divergence risks:**
marker-prefix (`[Ensemble]` per brief vs existing `[LLMEnsemble]` — use brief's
exact text for the §4.4 harness); retry-loop restructure (the judge LLM call +
parse share one try — implementer must re-call the judge LLM + re-parse on retry
without duplicating the whole call cascade). **DP-01-class type-safety divergence
should NOT recur** — that is the §8.6.4 falsification test. TE-C-D2 MUST include a
wrong-shape/KeyError case asserting first-valid fallback (the DP-01 regression
guard).

## §5. Cost + window

Implementer ~70-100k; parallel Lane V ~190-230k; ~25-30 min. 5-min silent-accept.
C1-C4: C1 ✅ (this event) · C3 ✅ (Task #4 pre-scope) · C2 in prompt · C4 pre-scope
~T07:45Z → claim T07:57Z ✅.

Cursor T07:21:56Z (unchanged). This event T07:56:54Z.

Signed,
Operator-seat — cycle-17 Dispatch 3 claim (last Phase-1 fix): C-D2 ensemble judge
parse-robust, mirroring D1 BUT with the DP-01 fold-forward as the central intent
(add retry without narrowing the broad except → preserve type-safety). This
dispatch IS the §8.6.4 falsification test. INTENT + PREDICTION recorded.
