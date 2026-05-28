---
from: operator
to: director
kind: dispatch-claim
related-commits: e0434b7, 1b3ca2d
related-rules: 2, 9, 12, 13, 14
proposal-target: brief v2.0 §11.1 Phase-1 operator Lane B (C-D3 pt2 + C-D5) + §8.6 pilot
urgency: normal
rule-14-invocation: yes — operator-driven Lane B, 5 selection criteria below
---

**Status:** 🟢 **Dispatch 2 claimed (Rule #14 ODLB).** Sequential after Dispatch 1
(COMPLETE, `e0434b7`). Bundled C-D3 pt2 + C-D5 in `cinema/auto_approve.py`
(+ `cinema/review/controller.py` marker). §8.6 pilot continues (dispatch 2 of 3).

## §1. Scope + Rule #14 criteria

**Files:** `cinema/auto_approve.py` + `cinema/review/controller.py` (2 sibling
prod files — controller is the gate-decision consumer) + tests. **5 criteria:**
(1) ✅ 2 siblings ≤3. (2) ⚠️ WEAKEST — C-D5 has a canonical site
(`_any_take_has_fallback` @ `:436` + `image_veto_on_fallback` config), but the
C-D3 pt2 **DEFERRED** state is novel (additive-dataclass-field is a standard
idiom; no single canonical site). (3) ✅ ~30-60 prod LoC ≤150. (4) ✅ **conditional
on the additive approach I mandate below** — preserves `controller.py:331`
`if decision.auto_approved` branch. (5) ✅ Rule #13 audit below. **All hold (crit-2
weakest, judged MET) → operator-eligible.** Flagging crit-2 explicitly per Rule
#14 honesty; counter-refine if you'd rather director-drive the DEFERRED design.

## §2. Rule #12 grep-the-writes + Rule #13 symmetric audit

`check_gate` (`auto_approve.py:486-573`) is the SHARED evaluator for all 4 gates
(plan/image/motion/final via `_builders` `:518`). Its error paths today:
`:544` per-rule predicate exc → `fired=True` (rule veto); `:561` whole-gate exc →
`auto_approved=False` + `module_error` veto. **Both already route to manual
review** (`auto_approved=False`) — but in an UNATTENDED run that "manual review"
IS the 19-min block, and a module-error is indistinguishable from a substantive
veto. Consumer `controller.py:314-333` branches on `decision.auto_approved` +
builds `audit_entry` (`:323`) + logs `_aa_logger.info` (`:333`).
**Rule #13:** because `check_gate` is shared, an additive `deferred` field applies
symmetrically to all 4 gates by construction — implementer verifies + emits the
marker per-gate. The `web_server.py:1785-1826` manual-rejection path is a DIFFERENT
surface (human said no, not gate-eval-error) → correctly exempt from DEFERRED.

**Plan-vs-source divergence (flagged now):** brief marker `[AUTO-APPROVE] plan:
<decision>` does NOT exist — existing code uses `_aa_logger.info("auto_approve:
...")`. The marker is NEW (print-style, for the §4.4 grep-harness). Implementer
adds it in the controller; does not remove the logger.

## §3. INTENT (§8.6.1)

**C-D3 pt2:** the auto-approve gate must DISTINGUISH "I evaluated and a rule
legitimately vetoed" (→ manual review, clear reason) from "I could not evaluate
(predicate/module error)" (→ **DEFER-TO-MANUAL**, a distinct, legible state).
Today both collapse to `auto_approved=False` and an unattended run blocks 19 min
without distinguishing them. Add a DEFERRED signal **additively** (new
`deferred: bool=False` on AutoApproveDecision; error paths set it True, keep
auto_approved=False) so the error case is legible + never silently conflated with
a substantive veto — WITHOUT changing the manual-review routing
(`controller.py:331` must keep working unchanged). Correct outcome: an eval-error
emits `[AUTO-APPROVE] plan: DEFERRED`, controller still routes to manual.
**C-D5:** the keyframe composite threshold (0.97, PuLID-calibrated) is unreachable
for a non-PuLID fallback engine → wrongly vetoes good fallback takes. Apply a
conditional threshold (0.78 when a fallback was used / 0.97 for PuLID), keyed on
the existing `_any_take_has_fallback` signal, so fallback takes are judged at a
fair bar. Correct outcome: a fallback keyframe judged at 0.78 emits
`[AUTO-APPROVE] image_min_composite_kontext_fallback=0.78 applied`.
> Adequacy: given only this, a cold agent chooses "additive deferred field, keep
> auto_approved bool" over "replace bool with enum" (intent says "preserve
> routing"), and "conditional 0.78/0.97 keyed on fallback" over "lower 0.97
> globally" (intent says "fair bar for fallback, unchanged for PuLID"). Concrete.

## §4. PREDICTION (§8.6.3 — pre-execution)

(a) **DEFERRED:** additive `deferred: bool=False` on `AutoApproveDecision`;
`check_gate`'s `:561` whole-gate-exc sets `deferred=True` (+ likely the `:544`
predicate-exc path too); `auto_approved` stays False. (b) **Marker:** new
print-style `[AUTO-APPROVE] {gate}: {DEFERRED|APPROVED|...}` in
`controller.py` near `:333`; `audit_entry` gains `"deferred"`. → **2-file change.**
(c) **C-D5:** new config field `image_min_composite_fallback: float=0.78` on
`AutoApproveConfig` (mirrors existing config pattern) + conditional in
`_rules_for_image` (`:193`) selecting it via `_any_take_has_fallback(takes)`.
(d) **Rule #13:** DEFERRED symmetric across 4 gates by construction (shared
check_gate). **Predicted divergence risks:** marker-location (controller vs
web_server — I predict controller); config-field-vs-hardcoded-0.78 (I predict
config field); whether predicate-exc `:544` also sets deferred (I predict yes, for
symmetry). **Carry-forward from DP-01:** auto_approve has NO LLM json.loads, so
the DP-01 type-safety INTENT-GAP does NOT apply here (it folds to Dispatch 3
ensemble instead).

## §5. Cost + window

Implementer ~80-120k; parallel Lane V ~200-240k; ~25-35 min. 5-min silent-accept
window (counter-refine the DEFERRED additive-vs-enum call or crit-2 if you'd
director-drive). C1-C4 dogfood: C1 ✅ (this event) · C3 ✅ (pre-scoped, Task #3) ·
C2 instructed in prompt · C4 pre-scope ~T07:30Z → claim T07:43Z ✅.

Cursor T07:21:56Z (unchanged). This event T07:43:03Z.

Signed,
Operator-seat — cycle-17 Dispatch 2 claim: C-D3 pt2 (additive DEFERRED, preserve
auto_approved routing) + C-D5 (conditional 0.78/0.97 threshold) in auto_approve.py
+ controller.py marker. Rule #13 symmetric via shared check_gate; crit-2 flagged
weakest-but-met; INTENT + PREDICTION recorded. Implementer imminent.
