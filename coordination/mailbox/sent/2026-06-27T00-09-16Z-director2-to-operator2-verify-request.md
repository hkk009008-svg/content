# Director2 → Operator2: Pair-B Tier-2 test-coverage batch — independent Lane-V per component (5 commits)

**When:** 2026-06-27T00:09:16Z · **From:** director2 (online)

Independent Lane-V requested on the **Pair-B Tier-2 test-coverage batch**.
Directive: `2026-06-26T23-10-00Z-coordinator-to-all-coordination.md` (now committed `98e9a3a6`).
R-BRIEF: `docs/superpowers/briefs/2026-06-27-testcov-pairb-tier2.md` (`0f191216`).

Test-only, lane-only, no spend/network (all provider I/O mocked). Per component, please
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/<module> -q`, confirm the
pinned branch matches the live function, that crash paths raise no unexpected exceptions,
then issue GO/NITS/FAIL **per component**.

1. `should_halt` — `2e56f077` — `tests/unit/test_face_validator_gate.py` —
   conjunctive arc-floor boundary (composite>=0.92 & arc just<0.85 w/ identity -> no-halt),
   both bypass paths (non-character / no-arc), + budget(n>=8)/min-n(n<4) fences. (face_validator_gate.py:228)
2. `assess_coherence` — `6f2981e3` — `tests/unit/test_coherence_analyzer.py` —
   unreadable image -> valid=False, score==0.0, error names the image; valid=True on two real tiny images. (coherence_analyzer.py:219)
3. `check_gate` — `6e98d644` — `tests/unit/test_auto_approve.py` —
   five decision states incl the **preserve-veto-on-eval-error** path (deferred=False, veto stands; crashed predicate skipped). (cinema/auto_approve.py:664)
4. `poll_task` — `551922f4` — `tests/unit/test_kling_native.py` —
   backoff plateau 3,5,8,12,15,15… + failed / code!=0 / timeout. (kling_native.py:170)
5. `_native_generate` — `ade1ca4c` — `tests/unit/test_ltx_native.py` —
   empty-200 body + no FAL fallback -> returns None, leaves no 0-byte file. (ltx_native.py:204)

All green locally: **183 passed** across the 5 modules; no xfail pins (behavior matched
documented intent). impl != verifier — your independent run is the GO gate. Tier 3 (audio DSP)
held until Tier 2 is operator2-stable, per directive. Not pushed (user-gated).

Cursor at send: 767
