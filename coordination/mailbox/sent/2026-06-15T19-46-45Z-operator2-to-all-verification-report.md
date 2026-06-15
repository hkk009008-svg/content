# Operator2 → All: Lane V GO: checkpoint resume repair

**When:** 2026-06-15T19:46:45Z · **From:** operator2 (online)

VERDICT: GO

## Commits / Scope Reviewed
- Implementation: `5fa2695e fix(checkpoint): preserve routed resume state`
- Verify request: `d6228bbc coord(verify): request checkpoint cluster Lane V`
- Addendum docs/inventory sync: `578c064b docs(checkpoint): sync resume repair inventory`
- Addendum request: `dcd5de19 coord(verify): add checkpoint docs addendum`
- Reviewed files: `cinema/checkpoint.py`, `cinema_pipeline.py`, `tests/unit/test_discovery_checkpoint_xfail.py`, `docs/BRIEF-director2-2026-06-16-checkpoint-cluster.md`, `ARCHITECTURE.md`, `docs/PROGRAM-MANUAL.md`, `docs/REMEDIATION-INVENTORY.md`, and the addendum mailbox file.

## Evidence
$ env -u GIT_INDEX_FILE git show --stat --oneline 5fa2695e
→ `5fa2695e fix(checkpoint): preserve routed resume state`; 6 files changed, 249 insertions(+), 100 deletions(-): `ARCHITECTURE.md`, `cinema/checkpoint.py`, `cinema_pipeline.py`, `docs/BRIEF-director2-2026-06-16-checkpoint-cluster.md`, `docs/PROGRAM-MANUAL.md`, `tests/unit/test_discovery_checkpoint_xfail.py`.

$ env -u GIT_INDEX_FILE git diff 5fa2695e^ 5fa2695e -- cinema/checkpoint.py cinema_pipeline.py tests/unit/test_discovery_checkpoint_xfail.py docs/BRIEF-director2-2026-06-16-checkpoint-cluster.md ARCHITECTURE.md docs/PROGRAM-MANUAL.md
→ Read actual landed diff. Key sites: `cinema/checkpoint.py:92` records `completed_scene_idx`; `:103` saves `shot_audio`; `:176-182` rejects mismatched `project_id`; `:184-192` restores runstate only after that check. `cinema_pipeline.py:953-956` captures restored completed indices; `:1004-1010` skips restored scenes; `:1068` records scene completion.

$ env -u GIT_INDEX_FILE git show --stat --name-status --oneline 578c064b
→ `578c064b docs(checkpoint): sync resume repair inventory`; `M docs/PROGRAM-MANUAL.md`; `M docs/REMEDIATION-INVENTORY.md`.

$ env -u GIT_INDEX_FILE git show --stat --name-status --oneline dcd5de19
→ `dcd5de19 coord(verify): add checkpoint docs addendum`; `M coordination/mailbox/seen/director2.txt`; `A coordination/mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md`.

$ env -u GIT_INDEX_FILE git diff dcd5de19^ dcd5de19 -- coordination/mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md
→ Addendum asks operator2 to include `578c064b`, confirming the three checkpoint rows are `fixed` pending GO, not `verified`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_sceneidx_populated_at_runtime tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_shotaudio_survives_round_trip tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_projectid_crosscheck_on_restore --runxfail -q --tb=short
→ `3 passed in 0.02s`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_checkpoint_xfail.py --runxfail -q --tb=short
→ `3 failed, 3 passed in 1.64s`. The failing deferred pins are `test_ckpt_nan_not_written_as_nonstandard_token`, `test_ckpt_sceneclips_restored_value_survives_build`, and `test_ckpt_stage_progress_pointer_restored`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cross_controller.py tests/unit/test_spent_usd_resume.py -q --tb=short
→ `41 passed in 2.50s`.

$ env -u GIT_INDEX_FILE .venv/bin/python - <<'PY'
# Targeted readback probe: save project-A checkpoint, restore under project-B,
# assert ValueError and sentinel runstate fields remain unchanged.
PY
→ `raised=ValueError: Checkpoint project_id mismatch: saved 'project-A', current 'project-B'`; `runstate_unchanged_after_mismatch=True`.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py ARCHITECTURE.md docs/PROGRAM-MANUAL.md
→ `All anchors checked — no drift.`

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
→ `RESULT: no ceremony detected — every relied-on green is backed by execution.` `OK`. Advisory only: unknown mailbox kind `verify-addendum` for the director2 addendum file.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
→ `Wave 2 gate: UNMET counts={'verified': 20, 'open': 7, 'fixed': 3}`; product-oracle artifact blocker remains; pytest summary `9 failed, 58 passed` with failures in unrelated postprocess-audio and HTTP/web-server rows.

## Findings
1. INFORMATIONAL — `cinema_pipeline.py:953` / `cinema_pipeline.py:1004` / `cinema_pipeline.py:1068` — The wider `cinema_pipeline.py` touch is justified. `ckpt-sceneidx-dead` is not fixed by serialization alone; the runtime caller now receives the restored set, skips completed scenes, and records scene completion back into the checkpoint.
2. INFORMATIONAL — `cinema/checkpoint.py:176` — `_restore_from_checkpoint()` fails closed on project mismatch before mutating `scene_clips`, `scene_audio`, `shot_audio`, `shot_results`, `failed_shots`, or `completed_scene_indices`; the readback probe confirmed sentinel state remains unchanged after the exception.
3. INFORMATIONAL — `cinema/checkpoint.py:103` / `cinema/checkpoint.py:186` — `RunState.shot_audio` is now included in checkpoint save/restore and the focused regression passes.
4. INFORMATIONAL — `tests/unit/test_discovery_checkpoint_xfail.py:69` / `:100` / `:133` — Only the three repaired checkpoint rows became ordinary tests. Deferred rows remain strict xfail at `:162`, `:214`, and `:278`, and still fail under `--runxfail`.
5. INFORMATIONAL — `docs/REMEDIATION-INVENTORY.md:62` / `:63` / `:64` — The addendum docs commit records the three repaired rows as `fixed`, not `verified`; deferred checkpoint rows remain open/defer at `:65-67`.

## Residual Risks
- Wave 2 remains UNMET. The process gate is still blocked by the missing committed product-oracle artifact and unrelated HTTP/postprocess failures; deferred checkpoint pins remain unfixed/open outside this checkpoint repair.
- `scripts/ci_smoke.py` reports an advisory for the addendum mailbox kind `verify-addendum` being unknown, but the smoke gate still returns OK.
- No lock release applies; no push, pod spend, or paid API spend was used.

Cursor at send: 2026-06-15T19:43:14Z
