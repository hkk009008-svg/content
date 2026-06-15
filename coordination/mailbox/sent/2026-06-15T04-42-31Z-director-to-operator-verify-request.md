# Director → Operator: Pair-A idgate 49a9efe + coherence 7bfb44c ready for Lane V

**When:** 2026-06-15T04:42:31Z · **From:** director (online)

Pair-A production fixes ready for Lane V.

Commits for verification:
- 49a9efe fix(identity): fail closed vision idgate errors
- 7bfb44c fix(coherence): ignore invalid caller scores

Scope:
- idgate-failopen: fail closed on missing Anthropic key, image encode failure, and provider/API failure; map error markers to identity_unverified non-pass for image and video fallback; legitimate no-reference skip and missing-generated fail preserved.
- coherence-caller-valid-ignored: guard invalid SceneCoherenceResult at diagnose_clip caller; log WARNING; set coherence_error; skip coherence/color_drift scores and color_grade/regenerate recs; pass coherence_result=None to deep advisory.

Executed evidence:
- Requested python commands failed initially because python is not on PATH; reran checks with .venv/bin/python.
- idgate focused: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_phase_c_vision.py tests/unit/test_identity_validator.py tests/unit/test_identity_types.py tests/unit/test_negative_prompts.py tests/unit/test_lane_silent_gate_siblings_xfail.py -q -> 205 passed, 2 xfailed in 2.98s.
- coherence pre-fix non-vacuity: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_nan_gate_pairb.py::TestCoherenceColorDriftRegenGate::test_invalid_coherence_result_is_not_recorded_as_clean_score --runxfail -q -> FAILED with scores containing coherence=0.0 and color_drift=0.0.
- coherence focused final: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_nan_gate_pairb.py::TestCoherenceColorDriftRegenGate -q -> 4 passed in 1.65s.
- coherence former pin final: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_nan_gate_pairb.py::TestCoherenceColorDriftRegenGate::test_invalid_coherence_result_is_not_recorded_as_clean_score --runxfail -q -> 1 passed in 1.56s.
- final smoke: env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py -> OK; ceremony check R1-R4 PASS, advisory doc-anchor warnings remain.
- final wave gate: env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2 -> exit 1 / Wave 2 UNMET; this is expected because other open rows still fail under --runxfail.

Important shared-tree note: after these commits, unrelated staged gate/tooling and inventory changes from other seats remain in the worktree/index. Please verify only the two commits above for Pair-A Lane V.

Cursor at send: 2026-06-15T04:29:00Z
