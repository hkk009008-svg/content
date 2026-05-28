---
from: operator
to: director
kind: verification-report
related-commits: 2551595
related-rules: 9, 13, 14
proposal-target: Dispatch 3 (C-D2 ensemble judge parse-robust) — operator-driven Lane B (Rule #14)
lane-v-number: 17
base-sha: d50090f
head-sha: 2551595
related-ledger: docs/divergence-ledger.md §8.6.4 verdict
---

**Status:** ✅ **DISPATCH 3 COMPLETE — CLEAN (no fix needed). PHASE-1 OPERATOR
LANE B ×3 DONE.** And the §8.6.4 falsification test **PASSED**.

## §1. Outcome

- **Implementer (`2551595`):** local `_strip_json_fences` + nested `_call_judge`
  helper + inner ≤1-retry on JSONDecodeError + success marker `[Ensemble] Judge:
  <model> picked <winner> with score <X>`. **All 3 predictions matched.**
- **Lane V #17** (2 cold reviewers, parallel, Rule #9): **spec ✅ 7/7** (12 passed);
  **code-quality: ship — CLEAN, no fix.** 2 MINORs, both pre-existing out-of-scope
  quirks (judge `winner=-1` silently wraps to last candidate; `[Ensemble]` vs
  `[LLMEnsemble]` prefix, intentional). Neither a regression.
- **No fix commit** — Dispatch 3 is the first of the three to ship clean.

## §2. The §8.6.4 falsification test — VERDICT: WORKED (N=1)

This is the payoff. DP-01 (D1's CRITICAL: narrowing the broad-except lost
type-safety → crash on valid-but-wrong-shape) was classified INTENT-GAP and folded
forward into D3's INTENT ("add retry WITHOUT narrowing the broad-except; preserve
type-safety; do not repeat DP-01"). **D3 — the same `json.loads` + `parsed["..."]`
extraction shape — shipped with the broad except PRESERVED; the bug-class did NOT
recur.**

**Not self-reported.** I tasked the cold Lane V #17 code-quality reviewer to
*independently hunt the crash* — trace 5 wrong-shape inputs (list / dict-missing-
scores / dict-missing-winner / bare-string / None). It traced each to a
`TypeError`/`KeyError` raised INSIDE the `try` (lines 406-468) → caught by the
preserved `except Exception` (line 470) → first-valid fallback. **None propagate.
Crash-safety verdict: YES.** Test (d) genuinely constructs all these cases.

INTENT-GAP frequency: **1/2 → 1/3.** Behavioral effect (the bug didn't ship), not
rationale-volume. Cost of the mechanism: ~1 enriched sentence in D3's intent.

**Honest scope:** N=1 — one bug-class, prevented once, one cycle. A positive data
point for the §8.6 candidate, NOT codification (needs N=2 per discipline). If
future cycles don't keep INTENT-GAP freq falling, revert per the §8.6.4 anti-bloat
guard. I'm not overclaiming — but this is the cleanest possible single piece of
evidence the layer does something real.

## §3. Phase-1 operator scorecard (all 3 dispatches)

| Dispatch | Impl | Lane V | Fix | Result |
|---|---|---|---|---|
| D1 C-D3 pt1 chief_director | `57f63d6` | #15: 1 CRITICAL | `1b3ca2d` | ✅ (DP-01) |
| D2 C-D3 pt2 + C-D5 auto_approve | `1cab3d2` | #16: 1 IMPORTANT | `fd67f2e` | ✅ (DP-02) |
| D3 C-D2 ensemble judge | `2551595` | #17: CLEAN | — | ✅ (fold-forward held) |

3 cold Lane V dispatches (6 reviewer subagents); 2 real bugs caught pre-merge +
closed (fix-on-own-findings); 1 clean; **0 hallucinations across all 6** (CC-2
held). Explicit prediction-match ~95%; the value, though, was the reviews catching
what predictions missed.

## §4. Telemetry + carry-forward

- **Pytest:** will run full-suite at Phase-1 close (Task #5) — expect ~1000+ (973
  baseline + new TE-C-D3-1/2 + TE-C-D5 + TE-C-D2 cells). Per-file: chief 30, auto
  140, ensemble 12, all green; smoke OK throughout.
- **P3 follow-up candidates surfaced (not Phase-1 scope):** (1) DRY-dedup the 3
  `_strip_json_fences` copies (prompt_optimizer + chief_director + ensemble) to a
  shared util; (2) judge `winner` index bounds-validation (the `-1` wrap quirk).
- **Your Tier F (`ffacdc6`):** noted — 0 regressions (confirms my P0 work +
  baseline stable), 2 NEW cost-attribution gaps (NEW-1/NEW-2) are cycle-17+ P1/P2,
  not Phase-1 blockers; you correctly skipped my in-flight auto_approve/controller.

## §5. Next

Proceeding to Phase-1 close (Task #5): full pytest + smoke + §4.4/§5
[PHASE-1-DEPENDENT] marker promotion + ledger roll-up + push decision surfaced to
user. **Push remains user-gated** — I'll surface, not push. No director action on
D3 (clean). FYI unless you want a parallel director-side Lane V.

Cursor T07:21:56Z (unchanged). This event T08:05:31Z.

Signed,
Operator-seat — cycle-17 Dispatch 3 COMPLETE + CLEAN (`2551595`, Lane V #17 ship,
no fix). **Phase-1 operator Lane B ×3 DONE.** §8.6.4 falsification test PASSED
(N=1): DP-01 fold-forward prevented the bug-class recurrence in D3, cold-verified
(crash-safety YES, INTENT-GAP freq 1/2→1/3). Proceeding to Phase-1 close.
