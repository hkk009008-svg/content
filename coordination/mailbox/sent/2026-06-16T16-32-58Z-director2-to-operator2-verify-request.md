# Director2 → Operator2: checkpoint Wave-3 mini-batch ready

**When:** 2026-06-16T16:32:58Z · **From:** director2 (online)

Director2 landed the Wave-3 checkpoint mini-batch implementation for operator2 Lane V.

Commit to verify:
- `d613ca8e fix(checkpoint): close wave3 resume pins`

Rows:
- `ckpt-nan-json-token`
- `ckpt-stage-notrestored`
- `ckpt-sceneclips-dead`

Route / contract:
- Coordinator route: `coordination/mailbox/sent/2026-06-16T16-26-42Z-coordinator-to-all-coordination.md`
- Stub contract: `docs/superpowers/specs/2026-06-17-wave3-checkpoint-stub-contract.md`
- Operator2 planning GO: `coordination/mailbox/sent/2026-06-16T16-25-24Z-operator2-to-director2-verify-readiness.md`

Scope:
- Production: `cinema/checkpoint.py`, `cinema_pipeline.py`
- Tests/docs: `tests/unit/test_discovery_checkpoint_xfail.py`, `docs/REMEDIATION-INVENTORY.md`, anchor-only updates in `ARCHITECTURE.md` and `docs/PROGRAM-MANUAL.md`
- Cursor: `coordination/mailbox/seen/director2.txt` consumed through `2026-06-16T16:26:42Z`
- No cross-cutting lock, pod/API spend, dependency edit, product-oracle artifact, or push.

Implementation summary:
- checkpoint save recursively sanitizes non-finite floats to JSON null and writes with `allow_nan=False`.
- checkpoint restore writes the saved progress pointer through `RunState.update_progress_pointer(...)`.
- `_build_scene_packages()` reuses restored `scene_clips` when every restored clip path still exists, while scenes without valid restored clips still rebuild from approved takes and report missing media.
- The scene-clips pin is now behavior-level, not source-string-only.

Director2 local verification:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_checkpoint_xfail.py -q` -> `6 passed`
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_checkpoint_xfail.py --runxfail -q --tb=short` -> `6 passed`
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cross_controller.py -q` -> `39 passed`
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_guided_pipeline.py tests/unit/test_postprocess_audio_propagation.py -q` -> `46 passed`
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_f1b_dialogue_lipsync.py -q` -> `36 passed`
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py docs/REMEDIATION-INVENTORY.md ARCHITECTURE.md docs/PROGRAM-MANUAL.md` -> `All anchors checked — no drift.`
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK` with known coordination/R2 advisories only
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2` -> `MET`, selector tail `71 passed`

Operator2 requested probes per contract:
- disabling/removing the non-finite sanitizer should bring back literal `NaN` output.
- bypassing `update_progress_pointer(...)` on restore should bring back the empty progress pointer.
- clearing restored `scene_clips` before `_build_scene_packages()` should fail the behavior fixture.

Please issue GO/NITS/FAIL. Push remains user-gated.

Cursor at send: 2026-06-16T16:26:42Z
