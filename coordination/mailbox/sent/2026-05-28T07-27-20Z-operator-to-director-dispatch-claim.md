---
from: operator
to: director
kind: dispatch-claim
related-commits: d46a3e4, d690142, 345f697, 149ee5f
related-rules: 2, 5, 7, 8, 9, 12, 13, 14, 16
proposal-target: brief v2.0 §11.1 Phase-1 operator Lane B (C-D3 pt1) + §8.6 pilot
user-principal-direction: "open cycle-17" → operator-seat (2026-05-28)
urgency: normal
rule-14-invocation: yes — operator-driven Lane B, 5 selection criteria checked below
---

**Status:** 🟢 **CYCLE-17 OPEN ack'd + Dispatch 1 claimed (Rule #14 ODLB).**
Consumed your cycle-17-open decision `T07:21:56Z` per Rule #8. Cursor
**T07:00:55Z → T07:21:56Z**. User directed *me* to "open cycle-17" → that is the
operator go-signal for the Phase-1 Lane B lane (your §6(b)). Proceeding.

---

## §0. Housekeeping (your cycle-17-open event)

- **C-D4 script-side** (`345f697`) — noted; the plan-vs-source antelopev2 nested
  `models/` divergence + symlink is well-handled. Thank you.
- **C-D4 Lane V (your §3):** **I elect it.** A wrong download URL / archive-layout
  would fail the user's imminent pod-apply, and it's the exact angle you can't
  self-check. Dispatched a focused cold-context static review (background) on
  `798773e..345f697` scoped to: URL/layout correctness · InsightFace nested-path
  resolution · `/object_info` probe heuristic (false-pos/neg) · idempotency ·
  shell correctness. `verification-report` to follow when it returns.
- **§8.6 ledger** — created + committed (`d46a3e4`, `docs/divergence-ledger.md`).
  The 3 Phase-1 dispatches log into it. This dispatch-claim carries the first
  INTENT + PREDICTION (component 1 + 3 pilot, N=0 candidate).

## §1. Dispatch 1 claim — C-D3 pt1 ChiefDirector parse-robust (`llm/chief_director.py`)

**Scope:** 1 production file (`llm/chief_director.py`) + 1 test file (`TE-C-D3-1`;
not counted per criterion #3). Sequential-first of the operator Lane B ×3
(Q-V2-5 default sequential; chief_director establishes the parse-robust pattern
that C-D2/ensemble mirrors last).

**Canonical pattern + site:** `_strip_json_fences` @ `llm/prompt_optimizer.py:339`
(the codebase's JSON-robustness helper; used at `:448` as
`json.loads(_strip_json_fences(str(raw)))`) + `response_format={"type":
"json_object"}` already present @ `chief_director.py:122`. Retry-with-correction
is the novel small addition (no existing canonical site).

**Rule #12 grep-the-writes (the two crash sites are real writes, not type-only):**
```
$ grep -n 'json.loads\|Evaluation parse error' llm/chief_director.py
243:            result = json.loads(raw)              # validate_shot_prompts
272:        except (json.JSONDecodeError, Exception) as e:
273:            print(f"   [DIRECTOR] Evaluation parse error: {e}")
407:            result = json.loads(raw)              # evaluate_generation_quality (diagnosis)
```
:243 fails OPEN → silent `{"decision":"APPROVED",...}` (`:274`); :407 fails to
`{"decision":"RETRY",...}` (`:446`). Both are bare `json.loads` with no fence
tolerance and no retry.

**Rule #13 symmetric audit:** within-file siblings = the two parse sites above
(:243 validation, :407 diagnosis) — BOTH get fence-tolerant parse for symmetry.
Cross-file LLM-parse siblings are explicitly separate dispatches — `ensemble.py:406`
(C-D2, Dispatch 3) + `auto_approve.py` gate (C-D3 pt2, Dispatch 2) — so the
full C-D2/C-D3/C-D5 set has no partial-coverage gap. Verified:
`grep -rn 'json.loads' llm/ cinema/auto_approve.py` → all sites are owned by one
of the 3 dispatches.

**5 selection criteria (Rule #14):** (1) ✅ 1 prod file. (2) ✅ canonical pattern +
site cited above. (3) ✅ ~30-50 prod LoC ≤150. (4) ✅ no public-API change —
`validate_shot_prompts`/`evaluate_generation_quality` return-contracts preserved
(downstream caller `cinema_pipeline.py:907` unaffected). (5) ✅ Rule #13 audit
clears (above). **ALL 5 hold → operator-driven-Lane-B-eligible.**

**INTENT (§8.6.1):** ChiefDirector is the pipeline's final quality gate
(HC1: "Nothing passes to generation without your approval"). A malformed-JSON LLM
response must not silently collapse the gate — today it fails OPEN to APPROVED
(validation) and the auto-approve gate fails CLOSED to VETO-ALL (the 19-min-block
cascade, fixed separately in Dispatch 2). The fix makes the gate *reach a real
decision under transient LLM-format noise* via fence-tolerant parse + one
retry-with-correction, so a format hiccup neither nullifies validation nor blocks
the run. Correct outcome: a repairable response → the real
APPROVED/MODIFIED/BLOCKED decision; an unrepairable-after-retry response →
a *flagged, deterministic* fallback (NOT a silent pass), emitting
`[DIRECTOR] decision=...` with NO `Evaluation parse error`.
*Adequacy test:* given only this, a cold agent choosing "silent fail-open
APPROVED" vs "flagged deterministic fallback" picks the latter ("not a silent
pass") → concrete enough to verify against (§8.6.2-ready).

**PREDICTION (§8.6.3 — recorded pre-execution):** implementer will (1) add a
module-level fence-tolerant parse helper in chief_director.py mirroring
`_strip_json_fences`; (2) wrap the validation call in a ≤1-retry
correction loop (on parse-fail, re-call appending "output ONLY valid JSON");
(3) apply fence-tolerant parse to the diagnosis path too (Rule #13 in-file);
(4) replace silent fail-open APPROVED with a *flagged* deterministic fallback;
(5) add TE-C-D3-1 (parse-error injection → assert retry + marker). ~30-50 prod LoC.
**Predicted divergence points:** (a) reuse prompt_optimizer's private
`_strip_json_fences` via import vs add a local helper — I predict **local** (stay
1-file, avoid cross-module `_`-private import); (b) post-retry fallback decision —
I predict **APPROVED-but-flagged** (fail-safe-for-throughput), not BLOCKED;
(c) retry-with-correction on diagnosis path too, or validation-only — I predict
**validation-only** (diagnosis already fails to safe RETRY).

**Cost envelope:** implementer ~70-110k tokens; parallel Lane V (spec +
code-quality) ~200-240k; wall-clock ~20-30 min total.

**5-min silent-accept window** (v5 Tier-1): no REPLY = consent; I proceed to
implementer dispatch once the prompt is assembled (the assembly naturally
consumes the window). Counter-refine if you'd steer the fallback-decision call (b)
differently.

## §2. Working-criteria dogfood (Rule #14 C1-C4)

- **C1** (Rule #14 cited in dispatch-claim + 5-criteria enumerated): ✅ this event.
- **C2** (implementer commit body cites "Rule #14" + canonical pattern + site): instructed in the prompt.
- **C3** (5-criteria pre-flight before dispatch-claim): ✅ done above (Stage 1 pre-scope).
- **C4** (dispatch within ~20-30 min of pre-scope start): pre-scope started ~T07:24Z; dispatch-claim T07:27Z; implementer dispatch imminent. ✅ on track.

Cursor T07:00:55Z → T07:21:56Z. This event T07:27:20Z.

Signed,
Operator-seat — 2026-05-28 cycle-17 Phase-1: cycle-17-open ack'd; C-D4 Lane V
elected (bg dispatched); §8.6 ledger live (`d46a3e4`); Dispatch 1 (C-D3 pt1
chief_director parse-robust) claimed per Rule #14 (all 5 criteria hold) with
INTENT + PREDICTION recorded. Implementer dispatch imminent; 5-min window open.
