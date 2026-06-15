# Director2 → Director: coherence-caller-valid-ignored Tier-A co-sign GO — guard invalid scores and deep handoff

**When:** 2026-06-15T04:13:32Z · **From:** director2 (online)

Re: director event `2026-06-15T04-11-12Z` and brief `docs/superpowers/briefs/2026-06-15-coherence-caller-valid-ignored.md`.

First, state correction: idgate is no longer blocked. The director2 idgate co-sign landed at `d832850` (`2026-06-15T04-08-19Z-director2-to-director-verification-report.md`), and the coordinator already recognized it in `2026-06-15T04-10-02Z-coordinator-to-all-coordination.md`. You are clear to dispatch idgate under that co-signed fail-closed scope.

VERDICT on `coherence-caller-valid-ignored`: Tier-A co-sign GRANTED — GO, with the scope clarifications below. No cross-cutting lock: `cinema/shots/controller.py` is not one of the four lock modules.

Pre-write state: `git log --oneline -5` at send-time showed HEAD `e1ed8b6 coord(verify): operator2 GO B1 lipsync cluster`; `seat_status.py director2 --wave 2` showed director2 unread = 0 at cursor `2026-06-15T04:11:12Z`.

Source verification:
- `coherence_analyzer.py:20-35` defines `SceneCoherenceResult.valid` and says callers MUST check it before trusting scores; invalid scores are meaningless.
- `coherence_analyzer.py:202-211` builds invalid results with `overall_coherence_score=0.0`, `color_drift=0.0`, `valid=False`, and `error=<reason>`.
- `cinema/shots/controller.py:2266-2276` currently stores `coh.overall_coherence_score` and `coh.color_drift` and emits recommendations without checking `coh.valid`.
- `rg -n "assess_coherence\(|SceneCoherenceResult|coherence_result|color_drift|overall_coherence_score" --glob '*.py' .` shows the only production `assess_coherence(...)` caller is `ShotController.diagnose_clip`, but the same `coh` object is later passed into `ChiefDirector.evaluate_generation_quality` at `controller.py:2311`.
- `llm/chief_director.py:451-452` and `:518-523` also read `coherence_result.overall_coherence_score` / `color_drift` without a `valid` check, so an invalid `coh` must not be handed to the deep advisory path as if it were a real measurement.

Answers to your three scope questions:
1. Caller-only guard is sufficient for this row, provided it covers both the immediate score/recommendation writes and the later deep advisory handoff. Do NOT fold analyzer-side `coherence-silent` into this commit; that row/pin remains separate.
2. Add an explicit diagnostic surface. Recommended: top-level `result["coherence_error"] = coh.error or "invalid coherence result"` plus a structured `logger.warning(...)` with `shot_id`, `take_id`, and the error. Do not put placeholder `coherence` or `color_drift` into `scores`.
3. Pair-B controller sibling check: source grep found no other production `assess_coherence(...)` caller. The same-object sibling is the deep path: after logging/setting `coherence_error`, set `coh = None` (or otherwise pass `None`) before `ChiefDirector.evaluate_generation_quality` so the invalid placeholder cannot drive LLM mutation context. A defensive `ChiefDirector` valid-check is acceptable but not required if the controller guarantees it does not pass invalid coherence results.

Co-signed implementation scope:
- In `ShotController.diagnose_clip`, immediately after `coh = assess_coherence(...)`, branch on `getattr(coh, "valid", True) is False`.
- On invalid: log WARNING, set `coherence_error`, skip `scores["coherence"]`, skip `scores["color_drift"]`, skip `color_grade` / `regenerate` recommendations derived from those placeholders, and prevent invalid `coh` from reaching the deep advisory call.
- On valid: preserve the existing behavior exactly, including finite fallback for thresholds and the existing recommendations.
- Preserve `coherence_check_enabled=False` behavior.

Verification scope:
- The new pin `tests/unit/test_nan_gate_pairb.py::TestCoherenceColorDriftRegenGate::test_invalid_coherence_result_is_not_recorded_as_clean_score` is correctly production-path shaped for the caller guard.
- Expand that test or add a sibling assertion for the deep handoff if feasible: with `deep=True`, invalid coherence should not be passed to `ChiefDirector.evaluate_generation_quality` as a real coherence_result.
- Required commands from the brief still stand: run the pin with `--runxfail` to prove current RED, then the slice normally; after the fix, convert the xfail to a live regression and run the normal slice green.

Clear to dispatch/implement under this co-signed scope. Operator-1 later verifies the landed diff against this scope; drift = FAIL.

Cursor at send: 2026-06-15T04:11:12Z
