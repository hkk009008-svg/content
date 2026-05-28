# Divergence Ledger — §8.6 insight-achievement pilot

**Status:** CANDIDATE apparatus (N=0 → earns codification per N=2 discipline).
**Created:** 2026-05-28, cycle-17 Phase-1 entry (operator-seat).
**Spec:** brief v2.0 [§8.6.3](BRIEF-comprehensive-test-v2.0-2026-05-28.md) (component 3 — divergence-logging) + §8.6.4 (metric + failure mode).
**Frame:** [§2.6](BRIEF-comprehensive-test-v2.0-2026-05-28.md) — the test's *product* is a **located divergence-point** (where the brief failed to transmit intent), not a pass/fail verdict.

---

## What this is

The predict→compare→mine-the-difference methodology, made systematic. The
predicting party (operator at dispatch-claim time; cell author at cell-write
time) records **predicted behavior/outcome BEFORE execution**. After execution,
actual is compared to predicted. Each divergence is logged here as one row and
**classified**:

| Class | Meaning | Disposition |
|---|---|---|
| **INTENT-GAP** | Intent under-transmitted; the *brief* failed to encode why/what. | → brief-enrichment (edit the named §). **This is the only class that feeds brief edits.** |
| **REAL-BUG** | Pipeline did the wrong thing; intent was clear. | → finding (fix the code, not the brief). |
| **PREDICTION-ERROR** | The predictor's mental model was wrong, not the brief. | → recalibrate the predictor; no brief/code change. |

The **insight** is *not* the agent understanding itself — it is **locating where
intent-encoding was insufficient** (the INTENT-GAP subset only). A §2.4 DEGRADED
cell (output present, marker absent) is usually an INTENT-GAP or REAL-BUG to
classify.

## The metric (§8.6.4) — what "working" means

Track **prediction-match rate** (did *behavior* align with stated intent?) and
**divergence-point frequency**, **NOT rationale-volume** (more rationale text is
easy to game and diverges from the goal). Working =

- prediction-match rate **rises** across cycles, AND
- divergence-point (esp. INTENT-GAP) frequency **falls** across cycles, AND
- no increase in rationale-talk.

**Failure mode (anti-bloat guard):** if INTENT-GAP frequency does **not** fall,
the mechanism is producing rationale-talk without behavioral effect → **rework
or retire it.** This ledger is the falsification instrument for its own pilot.

---

## Divergence-point log

One row per divergence-point. `DP-<NN>`. Empty until the first Phase-1 dispatch
compare step.

| ID | Cycle / Dispatch | Brief § (intent source) | INTENT (stated) | PREDICTED | ACTUAL | Class | Disposition |
|---|---|---|---|---|---|---|---|
| DP-01 | 17 / D1 (C-D3 pt1) | dispatch-claim INTENT (`cf02b3c`) + §4.4 P-CHIEFDIR | "scope retry to **parse failures** only" | implementer narrows `except` to `json.loads` (JSONDecodeError) — clean | did exactly that; but the narrowing removed the broad-except that absorbed **valid-but-non-dict** results → new uncaught `AttributeError` crash on the Anthropic path | **REAL-BUG** (primary) · **INTENT-GAP** (secondary) | REAL-BUG → fixed `1b3ca2d` (isinstance guard + regression test). INTENT-GAP → **enrich**: parse-robustness intent must say "handle malformed AND parsed-but-wrong-type", not just JSONDecodeError → **applied to Dispatch 3 (C-D2) INTENT** |
| DP-02 | 17 / D2 (C-D3 pt2) | dispatch-claim INTENT (`8b7aed1`) — "distinguish eval-error from substantive veto" | additive `deferred` field; error paths set it (early-return shape unpredicted) | implementer added an unpredicted per-predicate **early-return** that set `deferred=True` UNCONDITIONALLY → a real veto co-occurring with a later predicate crash gets mislabeled DEFERRED (deferred wins over VETO in the controller) | **REAL-BUG** | fixed `fd67f2e` (`if not vetoes` guard — a clean eval-error defers; a real veto stands as VETO) + regression test. No INTENT-GAP: the intent ("distinguish eval-error from veto") was clear; the early-return *violated* it |

**DP-02 detail.** Unlike DP-01, the intent here was unambiguous — the whole point
of C-D3 pt2 is the DEFERRED-vs-VETO distinction. The implementer's early-return
refinement (which they self-flagged as a divergence from my prediction) over-applied
deferral and *masked* a real veto, undermining the fix's own purpose. So this is a
clean **REAL-BUG** (no brief-enrichment needed; the code, not the intent, was
wrong). Lane V #16 code-quality reviewer caught + reasoned the edge cold.
**Minor PREDICTION-ERROR** (not a DP row): I leaned "C-D5 marker in controller";
the implementer put it in the named predicate (co-located with the threshold
choice) — cleaner; my "cleaner option" lean was wrong. Recalibrate: co-location
beats consumer-side emission when the decision is made in the predicate.

**DP-01 detail.** The 3 *explicit* predictions (helper-locality, fallback-decision,
diagnosis-retry) all MATCHED. The divergence emerged *outside* the prediction
set: my INTENT + PREDICTION framed robustness as "parse failure" (JSONDecodeError)
and never named the "parsed successfully but wrong type" case — so the implementer
faithfully scoped to JSONDecodeError and the broad-except's incidental type-safety
was lost. The insight is the INTENT-GAP: **"robust parse" ≠ "robust to
JSONDecodeError"; it must also mean "robust to valid-but-wrong-shape."** This is
the §8.6 engine working — a Dispatch-1 divergence enriches Dispatch-3's intent
*before* it ships the same class of bug. (Lane V #15 code-quality reviewer caught
it cold; empirically reproduced.)

---

## Per-cycle metric roll-up (§8.6.4 data source)

| Cycle | Dispatches w/ prediction | Predictions made | Prediction-matches | Match-rate | Divergence-points | INTENT-GAP count | INTENT-GAP freq (per dispatch) |
|---|---|---|---|---|---|---|---|
| 17 (Phase-1 pilot) | 3 of 3 (D1+D2+D3 done) | 10 explicit (3+4+3) | ~9.5 (only D2 (d) marker-loc soft-miss) | ~95% (explicit) | 2 (DP-01, DP-02; **D3 clean**) | 1 (DP-01 only) | **0.33** (1 INTENT-GAP / 3 dispatches) |

**Caveat on the high match-rate (the honest read):** explicit predictions match
well (~93%), yet 2 divergence-points emerged — DP-01 *outside* the prediction set
(type-safety dimension unnamed), DP-02 an unpredicted implementer refinement. So
match-rate overstates foresight; the real signal is **prediction-set completeness**,
not match-rate on predictions I happened to make. **Both divergences were REAL-BUGs
caught by Lane V**, not shipped — the parse/eval-robustness fixes were themselves
fragile in ways the cold reviewers caught. That is the system working: predict →
implement → independent-review → the *review* finds what the prediction missed.

**§8.6.4 falsification test — VERDICT: the fold-forward WORKED (N=1 positive).**
Dispatch 3 (C-D2 ensemble, the same `json.loads` + `parsed["..."]` extraction shape
that crashed in DP-01) inherited the enriched INTENT — "add retry WITHOUT narrowing
the broad-except; preserve type-safety; do not repeat DP-01." **D3 shipped with the
broad `except Exception`→first-valid fallback preserved, and the DP-01 bug-class did
NOT recur.** Not self-reported: the cold Lane V #17 code-quality reviewer
*independently traced all 5 wrong-shape inputs* (list / dict-missing-scores /
dict-missing-winner / bare-string / None) and confirmed each is caught → fallback,
none propagate (crash-safety verdict: YES). INTENT-GAP freq **1/2 → 1/3.** This is
**behavioral effect, not rationale-volume** — exactly the §8.6.4 success signal.

**Honest scope of the claim:** this is **N=1** — one known bug-class, prevented once,
within one cycle. It is a positive data point for the candidate, NOT codification
(which needs N=2 per existing discipline). The mechanism's cost was ~1 enriched
sentence in D3's INTENT field (cheap, no rationale-bloat). If future cycles show
INTENT-GAP freq does NOT keep falling, revert per the §8.6.4 anti-bloat guard.

**Trend read (needs N≥2 cycles):** _N=1 cycle; no cross-cycle trend. The intra-cycle
D1→D3 fold-forward is the first within-pilot evidence; verdict at D3 close._

---

## Pilot status

- **Component 1 (intent-encoding):** piloted — INTENT field on each Phase-1 Lane B dispatch-claim.
- **Component 2 (purpose-verification):** folds into Phase-1 Lane V once intent fields are concrete (§8.6.5 step 2).
- **Component 3 (divergence-logging):** this ledger.
- **Codification gate:** each component stays CANDIDATE until N=2 per existing discipline. A mechanism that works once is N=1, not codification-ready.
