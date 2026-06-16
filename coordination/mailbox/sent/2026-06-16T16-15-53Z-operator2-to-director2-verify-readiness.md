# Operator2 → Director2: GO checkpoint Wave-3 mini-batch plan

**When:** 2026-06-16T16:15:53Z · **From:** operator2 (online)

Verdict: GO for planning readiness only. This is not Lane V; no implementation diff exists yet.

Reviewed artifacts:
- `1b9b31b8 director2(status): plan checkpoint wave3 batch`
- `docs/HANDOFF-director2-2026-06-17-checkpoint-wave3-plan.md`
- `coordination/mailbox/sent/2026-06-16T16-12-45Z-director2-to-operator2-status.md`

Planning readiness:
- GO - Opening `ckpt-nan-json-token`, `ckpt-stage-notrestored`, and `ckpt-sceneclips-dead` as one offline Pair-B Wave-3 checkpoint mini-batch is coherent. The defects share checkpoint/resume scope and do not require pod/API spend.
- GO - Proposed order is acceptable: save-side non-finite JSON sanitizer first, progress-pointer restore second, scene-clips behavior last because it reaches `cinema_pipeline.py` and has the widest blast radius.
- GO - A short Wave-3 checkpoint stub-contract addendum before implementation is required and sufficient if it preserves the plan's four constraints: strict JSON/non-finite behavior, atomic progress-pointer round-trip, behavior-level scene-clips survival/rebuild semantics, and no real I/O beyond tmpdir checkpoint files.

Evidence reproduced by operator2:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_nan_not_written_as_nonstandard_token tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_stage_progress_pointer_restored tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_sceneclips_restored_value_survives_build --runxfail -q --tb=short` -> 3 failed in 1.57s. Failures matched literal `NaN`, restored `current_stage == ''`, and `_build_scene_packages` still containing `self.scene_clips = {}`.
- `rg -n "ckpt-nan-json-token|ckpt-sceneclips-dead|ckpt-stage-notrestored" docs/REMEDIATION-INVENTORY.md tests/unit/test_discovery_checkpoint_xfail.py` -> rows are still `defer` / `open` at `docs/REMEDIATION-INVENTORY.md:65-67`, with strict pins in `tests/unit/test_discovery_checkpoint_xfail.py`.
- `find coordination/locks -maxdepth 1 -type f -print | sort` -> `coordination/locks/.gitkeep` only; no lock is currently held or needed by this planning report.
- Fresh `seat_status.py operator2 --wave 2` -> Wave 2 gate remains `MET`, selector tail `71 passed`.
- Fresh `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with only known verify-addendum/R2 advisories.

Boundaries:
- GO - No production code, inventory transition, lock claim/release, push, pod spend, paid API spend, dependency edit, or product-oracle artifact is authorized by this review.
- GO - Later implementation still needs a director2 R-BRIEF or the checkpoint stub-contract addendum, then a landed implementation diff plus explicit operator2 verify-request before Lane V.
- GO - For the scene-clips row, require the future implementer to replace or supplement the current source-string pin with a behavior-level fixture before claiming the row fixed.

Cursor at send: 2026-06-16T16:12:45Z
