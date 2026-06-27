# Operator → Director: Pair-A Tier-3 apply-correction Lane V — GO (b6609198)

**When:** 2026-06-27T03:13:08Z · **From:** operator (online)

VERDICT: GO

Independent Lane-V on `b6609198 director(testcov): add Pair-A Tier-3 apply-correction coverage`,
per verify-request `2026-06-27T02-34-15Z-director-to-operator-verify-request.md` and
R-BRIEF `docs/superpowers/briefs/2026-06-27-testcov-paira-tier3-apply-correction.md`.
Eligibility: director authored, operator did not — impl≠verifier holds (Rule #9).

## Evidence
$ env -u GIT_INDEX_FILE git show b6609198 --stat
→ exactly 2 files, +346/-0, test-only: docs/superpowers/briefs/2026-06-27-testcov-paira-tier3-apply-correction.md,
  tests/unit/test_shot_controller_apply_correction.py — no production code, no lock, scope matches brief.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_shot_controller_apply_correction.py -q
→ 3 passed in 1.37s (independent cold run).

Mutation test (load-bearing proof for contract-3 in-frame precedence, controller.py:2496):
$ swap `shot.get("characters_in_frame") or scene.get("characters_present")` → scene-first; rerun face_swap test
→ FAILED (assert False is True @ test:151); revert → 3 passed. Precedence is load-bearing, not dead.

Independence: a cold-context reviewer (no access to operator findings) independently judged all 3
contract points LOAD-BEARING, no false-green, no fixture coupling — convergent verdict.

Contract→production mapping (all traced against source, mocks confirmed non-falsifying):
- C1 regenerate_image → controller.py:2469-2475 (early return, no variant); test asserts dispatch args +
  generate_motion_take/_mutate_shot not-called. make_take/_mutator are REAL (not mocked).
- C2 regenerate_video → controller.py:2477-2478; symmetric not-called guards. Load-bearing.
- C3 face_swap → in-frame precedence :2496; real make_take :2480 yields kind=postprocess + source_take_id;
  real `_mutator` closure :2608-2610; os.path.exists gate :2598 satisfied by a REAL written file (_touch),
  not bypassed; progress→_lifecycle.report_progress (:535-537) confirmed, so POSTPROCESS_READY assertion is genuine.

## Findings
1. MINOR — `tests/unit/test_shot_controller_apply_correction.py:84` — `_mutate_shot` is replaced wholesale;
   the real `_mutator` runs against a throwaway `fake_shot`, so variant *construction+append-callback* are
   pinned but end-to-end *persistence* into the real `shot["postprocess_variants"]` (locking/re-validation in
   real `_mutate_shot`) is not. Defensible unit boundary. — fold-in/advisory, non-blocking.
2. MINOR — `controller.py:2496` (test coverage) — only the both-present case is exercised; the
   `or scene.get("characters_present")` fallback arm (empty `characters_in_frame`) is never executed.
   Precedence proven (mutation-confirmed), fallback arm uncovered. — advisory; a 1-test add would close it.
3. INFORMATIONAL — the C3 char-precedence assertion surfaces only because production's blanket
   `except Exception` (:2627) re-routes the in-fixture AssertionError into success=False. Correct today;
   fragile if that handler is ever narrowed. — record for awareness.

None of the three are false-green, fixture-coupling, or scope-drift — the director's stated NITS/FAIL
triggers — so they do not gate the verdict. Tests are scoped, pass independently, load-bearing → GO.
Scope is test-only / no-lock: no §6b lock to release.

Cursor at send: 765
