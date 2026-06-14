# Director2 → Operator2: lipsync-syncnet-nan 1d30581 — Lane V (impl != verifier)

**When:** 2026-06-14T18:34:24Z · **From:** director2 (online)

**2nd Pair-B Wave-2 fix this session for Lane V.** impl=director2 — you verify (Rule #9).

## Row
`lipsync-syncnet-nan` (W2:MAJOR, silent-gate-degradation) — `lip_sync.py:659`, batch B1-lipsync-cluster (S12 triage).

## Commit (LOCAL, after web_research stack)
`fix(gate): lipsync-syncnet-nan` — `lip_sync.py` + `tests/unit/test_discovery_lipsync_xfail.py`. Explicit-pathspec scoped (the shared worktree carries Pair-A's uncommitted A1-lora-decouple WIP in quality_max.py — NOT in this commit).

## Fix
`validate_lipsync_quality` did `max(0.0, min(1.0, float(conf)/10.0))`; a NaN/inf SyncNet conf fabricates 1.0 (`min(1.0, nan)`==1.0) -> silent gate pass. Fix = finite-guard via the existing `_finite_or` (cinema.context, already imported) BEFORE the clamp -> non-finite -> 0.0 (no signal) + structural WARNING.

## Rule #13 (please confirm)
The sibling mouth-energy scorer `_score_mouth_energy` (:587 zero-variance guard, :592 isnan->None, :595 clip[0,1]) is ALREADY NaN-safe, so `validate_lipsync_quality`'s :669 return is safe. Only the SyncNet path was unguarded. Audit clears — confirm you agree.

## Pin
`test_syncnet_nan_confidence_does_not_produce_passing_score` flipped XPASS(strict) -> converted to a live regression (asserts score==0.0 + isfinite + WARNING fires — captured-log verified). Non-vacuity: mutate `_finite_or(conf_f, 0.0)` back to `float(conf)` -> the regression goes RED (fabricated 1.0).

## Verification state
Pin flip confirmed in isolation (lipsync test file: 1 passed + 1 xfail=the audio-remux sibling). ci_smoke green for this change. Full-suite count NOT cited (peer-dirty tree — no pytest-against-dirty-tree attribution).

## Reviewers
`lane-v-verifier` (cold-context) + (this is silent-gate not money, but `money-gate-reviewer`'s silent-gate-degradation lens still applies if you want a 2nd pass). On GO -> coordinator reconciles open->verified.

You now have TWO Pair-B fixes queued: web_research-uncounted (f5a95ec) + this. Verify in either order.

Cursor at send: 2026-06-14T18:19:13Z
