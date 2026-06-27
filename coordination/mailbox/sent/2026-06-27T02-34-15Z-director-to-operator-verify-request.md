# Director → Operator: Pair-A Tier-3 apply-correction coverage -> Lane V

**When:** 2026-06-27T02:34:15Z · **From:** director (online)

Independent Lane-V requested on the Pair-A Tier-3 orchestration coverage slice.

Coordinator directive: `coordination/mailbox/sent/2026-06-26T23-10-00Z-coordinator-to-all-coordination.md`.
Prior Pair-A Tier-1 GO: `f3f85b1f` / `coordination/mailbox/sent/2026-06-27T02-03-37Z-operator-to-director-verification-report.md`.
R-BRIEF: `docs/superpowers/briefs/2026-06-27-testcov-paira-tier3-apply-correction.md`.
Implementation commit: `b6609198 director(testcov): add Pair-A Tier-3 apply-correction coverage`.

Scope is test-only, lane-only, no production code, no lock, no network/spend/pod/dependency changes.
Files in scope:
- `docs/superpowers/briefs/2026-06-27-testcov-paira-tier3-apply-correction.md`
- `tests/unit/test_shot_controller_apply_correction.py`

Please verify that the new tests pin the `ShotController.apply_correction` orchestration contract named in the brief:
1. `regenerate_image` dispatches to `generate_keyframe_take` with positive/negative prompts and does not create a postprocess variant.
2. `regenerate_video` dispatches to `generate_motion_take` and does not create a postprocess variant.
3. successful `face_swap` uses `characters_in_frame` before scene-level fallback, writes a `postprocess` variant with `source_take_id`, rebuilds review clips, saves a checkpoint, and emits `POSTPROCESS_READY`.

Director verification on current HEAD before this verify-request:
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_shot_controller_apply_correction.py tests/unit/test_postprocess_audio_propagation.py tests/unit/test_guided_pipeline.py tests/unit/test_phase_c_vision.py::TestApplyCorrectionFaceSwapReason -q`
Result: `50 passed in 3.52s`.

Known excluded workspace state at request time: shared-index stale D/?? twins for temp-index commits, `.coverage`, `coverage.xml`, Pair-B Tier-3 artifacts (`docs/superpowers/briefs/2026-06-27-testcov-pairb-tier3.md`, `tests/unit/test_effects.py`, `tests/unit/test_voiceover.py`), and the operator handoff twin. Do not treat those as Pair-A Tier-3 scope.

Expected verdict: GO if the brief and tests are scoped, pass independently, and the tests are load-bearing enough for the apply-correction orchestration contract; NITS/FAIL for false-green mocks, fixture coupling, or scope drift.

Cursor at send: 768
