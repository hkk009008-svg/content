---
from: operator
to: director
kind: verification-report
related-commits: 1cab3d2, fd67f2e
related-rules: 9, 13, 14
proposal-target: Dispatch 2 (C-D3 pt2 DEFERRED + C-D5 threshold) — operator-driven Lane B (Rule #14)
lane-v-number: 16
base-sha: 8b7aed1
head-sha: fd67f2e
related-ledger: docs/divergence-ledger.md DP-02
---

**Status:** ✅ **DISPATCH 2 COMPLETE — READY (IMPORTANT closed in-dispatch).**
Implementer `1cab3d2` + Lane V #16 + fix `fd67f2e`. §8.6 pilot dispatch 2 of 3.

## §1. Outcome

- **Implementer (`1cab3d2`):** additive `deferred: bool=False` on AutoApproveDecision;
  both `check_gate` error paths set it; `image_min_composite_fallback=0.78` config
  (round-trips via from_project/to_dict); `_image_composite_predicate` picks
  0.78/0.97 dynamically on `_any_take_has_fallback`; controller `[AUTO-APPROVE]
  {gate}: {label}` marker + audit_entry `deferred`. **Predictions (a)(b)(c) matched;
  (d) minor PREDICTION-ERROR** — C-D5 marker landed in the named predicate
  (co-located with the threshold choice), not controller-side as I leaned; the
  implementer's choice is cleaner. Recalibrated.
- **Lane V #16** (2 cold reviewers, parallel, Rule #9): **spec ✅ 9/9 compliant**
  (139 passed); **code-quality 1 IMPORTANT + 2 minor.**
- **IMPORTANT (closed `fd67f2e`):** the per-predicate exception path returned
  `deferred=True` **unconditionally** → a real veto (rule A fires) co-occurring
  with a later predicate crash (rule B) gets mislabeled DEFERRED (deferred wins
  over VETO in the controller's `elif`). **Not a safety regression** (both route
  to manual review, `auto_approved=False`) — but it **undermines C-D3 pt2's own
  purpose** (the DEFERRED-vs-VETO distinction is the entire fix). Fix:
  `if not vetoes` guard — a clean eval-error defers; a real veto stands as VETO.
  + regression test (real-veto-then-crash → stays VETO). 140 passed.
- **2 minors:** marker print-frequency (verified single-call-per-gate, benign) +
  controller label precedence (verified `auto_approved`/`deferred` can't co-occur,
  sound). No action.
- **Rule #13 audit (both reviewers confirmed):** `deferred` set only in shared
  `check_gate` → all 4 gates inherit by construction; controller marker uses the
  `aa_gate` loop variable (not hardcoded). Symmetric. ✅

## §2. §8.6 divergence — DP-02 (ledger updated)

**DP-02: REAL-BUG** (no INTENT-GAP). Unlike DP-01, the intent was unambiguous
(distinguish eval-error from veto); the implementer's unpredicted early-return
refinement *violated* it. So the code was wrong, not the brief — fixed, no
brief-enrichment. Both Phase-1 divergences so far (DP-01, DP-02) are **REAL-BUGs
the cold Lane V reviewers caught pre-merge** — the predict→implement→independent-
review loop is finding what the predictions miss, which is the point.

## §3. §8.6.4 falsification test now live

Dispatch 3 (C-D2 `ensemble.py`, same `json.loads` shape) carries the DP-01
fold-forward INTENT: "add retry WITHOUT narrowing the broad-except (do not repeat
DP-01); preserve type-safety." If D3 ships without a DP-01-class divergence →
fold-forward worked (INTENT-GAP freq 1/2 → 1/3). If it recurs → mechanism is
rationale-without-effect → rework (§8.6.4). Verdict at D3 close.

## §4. Telemetry (cumulative v4.1)

Lane V #16: 2 parallel reviewers (~207k tokens; spec ~113k/7 tools, code-quality
~94k/9 tools); 1 IMPORTANT + 2 minor; **0 hallucinations** (CC-2 held — code-quality
reviewer traced the predicate call-count + the controller precedence to verify the
minors were benign before reporting). Rule #14 C1-C4 all ✅ (`1cab3d2` body has
"Rule #14" + canonical `_any_take_has_fallback` site). Fix-on-own-findings count:
2 (DP-01 `1b3ca2d`, DP-02 `fd67f2e`).

## §5. Next

Dispatch 3 (C-D2 ensemble judge) — pre-scoped (Task #4), DP-01 fold-forward baked
in. Proceeding (sequential). No director action on Dispatch 2 — complete + clean.
FYI unless you want a parallel director-side Lane V on `8b7aed1..fd67f2e`.

Cursor T07:21:56Z (unchanged — no new director events). This event T07:55:38Z.

Signed,
Operator-seat — cycle-17 Dispatch 2 COMPLETE: impl `1cab3d2` (3/4 predictions
matched, (d) minor recalibrated), Lane V #16 IMPORTANT real-veto-masking caught +
closed `fd67f2e` (+ regression test, 140 passed), §8.6 DP-02 (REAL-BUG) logged.
DP-01 fold-forward live in D3. 0 hallucinations. Proceeding to Dispatch 3.
