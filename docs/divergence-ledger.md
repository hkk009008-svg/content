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
| 17 (Phase-1 pilot) | 1 of 3 (D1 done; D2/D3 pending) | 3 explicit | 3 | 100% (explicit) | 1 (DP-01) | 1 (DP-01 secondary) | 1.0 (1 dispatch) |

**Caveat on the 100%/1-divergence pair (the honest read):** the 3 *explicit*
predictions matched, yet a divergence still emerged — because it fell *outside*
the prediction set (I never predicted the type-safety dimension). So "100%
match-rate" overstates foresight; the real signal is **prediction-set
completeness**, not just match rate on the predictions I happened to make. Cycle-17
target as D2/D3 land: does the DP-01 INTENT-GAP fold-forward (richer Dispatch-3
intent) *prevent* the same class of divergence (→ INTENT-GAP freq falls)? That is
the §8.6.4 falsification test in miniature.

**Trend read (needs N≥2 cycles):** _N=1 at cycle-17; no cross-cycle trend yet. The
intra-cycle D1→D3 fold-forward is the first within-pilot evidence._

---

## Pilot status

- **Component 1 (intent-encoding):** piloted — INTENT field on each Phase-1 Lane B dispatch-claim.
- **Component 2 (purpose-verification):** folds into Phase-1 Lane V once intent fields are concrete (§8.6.5 step 2).
- **Component 3 (divergence-logging):** this ledger.
- **Codification gate:** each component stays CANDIDATE until N=2 per existing discipline. A mechanism that works once is N=1, not codification-ready.
