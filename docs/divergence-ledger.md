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

| ID | Cycle / Dispatch | Brief § (intent source) | INTENT (stated) | PREDICTED (pre-exec) | ACTUAL (post-exec) | Class | Disposition |
|---|---|---|---|---|---|---|---|
| _(none yet)_ | — | — | — | — | — | — | — |

---

## Per-cycle metric roll-up (§8.6.4 data source)

| Cycle | Dispatches w/ prediction | Predictions made | Prediction-matches | Match-rate | Divergence-points | INTENT-GAP count | INTENT-GAP freq (per dispatch) |
|---|---|---|---|---|---|---|---|
| 17 (Phase-1 pilot) | _in progress_ | 0 | 0 | — | 0 | 0 | — |

**Trend read (needs N≥2 cycles):** _not yet — pilot is N=1 at cycle-17._

---

## Pilot status

- **Component 1 (intent-encoding):** piloted — INTENT field on each Phase-1 Lane B dispatch-claim.
- **Component 2 (purpose-verification):** folds into Phase-1 Lane V once intent fields are concrete (§8.6.5 step 2).
- **Component 3 (divergence-logging):** this ledger.
- **Codification gate:** each component stays CANDIDATE until N=2 per existing discipline. A mechanism that works once is N=1, not codification-ready.
