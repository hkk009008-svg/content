# Wave-3 Checkpoint Stub-Contract Addendum

> **Status:** director2-authored planning addendum, 2026-06-16T16:19:07Z.
> **HEAD at authoring:** `a5d59d71`.
> **Authority:** user-principal asked to continue as `director2`; operator2
> published planning-readiness GO in
> `coordination/mailbox/sent/2026-06-16T16-15-53Z-operator2-to-director2-verify-readiness.md`.
> This is an R-BRIEF-shaped test contract for a later implementation. It does
> not authorize production edits, remediation-inventory transitions, lock
> claims/releases, push, pod spend, paid API spend, dependency edits, or
> product-oracle artifact changes.

Pre-commit freshness refresh: while this artifact was being drafted, HEAD
advanced to `c0ce8f87 codex(protocol): codify seat subagent workflow`. Its
changed files are protocol harness/skill/agent/test files, not checkpoint
production code or checkpoint tests, so the checkpoint addendum scope below
remains current.

## Scope

Open the three deferred Pair-B checkpoint/resume rows as one offline Wave-3
checkpoint hardening mini-batch:

- `ckpt-nan-json-token`
- `ckpt-stage-notrestored`
- `ckpt-sceneclips-dead`

The rows are cohesive around checkpoint/resume correctness and all have strict
pins that still fail for the recorded reasons. They require only tmpdir
checkpoint files and local unit fixtures.

No cross-cutting lock is indicated. Expected production targets are
`cinema/checkpoint.py`, `cinema_pipeline.py`, and tests. None is one of the
four locked cross-cutting modules: `auto_approve.py`, `cinema/context.py`,
`core.py`, or `web_server.py`.

No Tier-A Pair-A co-sign is indicated. These rows do not change image,
identity, or ArcFace policy.

## Fresh Non-Vacuity Evidence

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_nan_not_written_as_nonstandard_token \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_stage_progress_pointer_restored \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_sceneclips_restored_value_survives_build \
  --runxfail -q --tb=short
-> 3 failed in 1.59s
-> test_ckpt_nan_not_written_as_nonstandard_token failed because the checkpoint
   file contains literal `NaN`.
-> test_ckpt_stage_progress_pointer_restored failed because restored
   `current_stage` is `''` instead of `MOTION`.
-> test_ckpt_sceneclips_restored_value_survives_build failed because
   `_build_scene_packages` still contains `self.scene_clips = {}`.
```

These failures are expected before implementation. They are the pins the later
fix must flip into live regressions.

## Rule #12 - Grep-The-Writes

### `ckpt-nan-json-token`

Target write path: checkpoint JSON serialization.

```text
$ rg -n "\"current_stage\"|\"current_scene_id\"|\"current_shot_id\"|update_progress_pointer|json\.dump|scene_clips\s*=|scene_clips\[scene_id\]" \
  cinema/checkpoint.py cinema/runstate.py cinema_pipeline.py cinema/shots/controller.py tests/unit/test_discovery_checkpoint_xfail.py
-> cinema/checkpoint.py:114: json.dump(state, f, indent=2, ensure_ascii=False, default=str)
```

Runtime write confirmed. The future fix must sanitize/check `state` before this
write and/or force strict JSON with `allow_nan=False` after sanitization.

### `ckpt-stage-notrestored`

Target fields: `current_stage`, `current_scene_id`, `current_shot_id`.

```text
$ rg -n "\"current_stage\"|\"current_scene_id\"|\"current_shot_id\"|update_progress_pointer|json\.dump|scene_clips\s*=|scene_clips\[scene_id\]" \
  cinema/checkpoint.py cinema/runstate.py cinema_pipeline.py cinema/shots/controller.py tests/unit/test_discovery_checkpoint_xfail.py
-> cinema/checkpoint.py:97: "current_stage": self._runstate.current_stage,
-> cinema/checkpoint.py:98: "current_scene_id": self._runstate.current_scene_id,
-> cinema/checkpoint.py:99: "current_shot_id": self._runstate.current_shot_id,
-> cinema/runstate.py:143: def update_progress_pointer(
-> cinema/shots/controller.py:668: self._runstate.update_progress_pointer("KEYFRAME", scene_id, shot_id)
-> cinema/shots/controller.py:1785: self._runstate.update_progress_pointer("MOTION", scene_id, shot_id)
-> cinema_pipeline.py:434: "current_stage": self.current_stage,
-> cinema_pipeline.py:435: "current_scene_id": self.current_scene_id,
-> cinema_pipeline.py:436: "current_shot_id": self.current_shot_id,
```

Runtime write/read surfaces confirmed. The future restore path should use
`RunState.update_progress_pointer(...)` when restoring all three pointer values
together, rather than scattering three assignments.

### `ckpt-sceneclips-dead`

Target state: `scene_clips`.

```text
$ rg -n "\"current_stage\"|\"current_scene_id\"|\"current_shot_id\"|update_progress_pointer|json\.dump|scene_clips\s*=|scene_clips\[scene_id\]" \
  cinema/checkpoint.py cinema/runstate.py cinema_pipeline.py cinema/shots/controller.py tests/unit/test_discovery_checkpoint_xfail.py
-> cinema/checkpoint.py:184: self._runstate.scene_clips = state.get("scene_clips", {})
-> cinema_pipeline.py:184: self._runstate.scene_clips = value
-> cinema_pipeline.py:713: self.scene_clips = {}
-> cinema_pipeline.py:737: self.scene_clips[scene_id] = clips
-> cinema/shots/controller.py:2656: self._runstate.scene_clips[scene_id] = clips
```

Runtime write surfaces confirmed. The future fix must prove restored
`scene_clips` are not discarded by `_build_scene_packages`, while preserving the
missing-shot behavior that populates `missing_shots` when approved takes cannot
be resolved.

## Rule #13 - Sibling Audit

Shared state/fence: `CheckpointStore._save_checkpoint()` and
`CheckpointStore._restore_from_checkpoint()` must remain symmetric for saved
run-state fields.

Audited sibling fields in `cinema/checkpoint.py`: `scene_audio`, `shot_audio`,
`scene_foley`, `foley_audio_paths`, `shot_results`, `failed_shots`, and
`completed_scene_indices`. The later implementation must not weaken these
restores while adding progress-pointer restore and non-finite serialization.

Audited sibling writes in `cinema_pipeline.py`: `_build_scene_packages()` must
continue to rebuild clips for scenes that lack valid restored clips and must
continue to report missing approved shot media through `missing_shots`.

Deferred, out of scope for this mini-batch: unrelated checkpoint rows outside
the three IDs above, UI status presentation beyond preserving the progress
pointer triple, and any product-oracle or spend-ledger behavior.

## Stub Contract

The test layer for this mini-batch must satisfy these constraints before any
production fix is claimed:

1. Checkpoint JSON serialization must reject or sanitize non-finite floats
   before write. The test must assert there are no literal `NaN`, `Infinity`,
   `-Infinity`, `nan`, `inf`, or `-inf` tokens and must parse the file with
   strict `json.loads`.
2. Progress-pointer restore must round-trip `current_stage`,
   `current_scene_id`, and `current_shot_id` as one coherent pointer. Prefer a
   fixture that fails if only one or two fields are restored.
3. Scene package rebuilding must be behavior-level, not source-string-only.
   The future test must prove restored `scene_clips` survive when valid and
   that scenes with missing approved take files are still rebuilt or reported
   in `missing_shots`.
4. Tests use tmpdir files only. No network, pod, paid API, product-oracle,
   dependency, or external media fixture is required.
5. Each strict xfail pin becomes a live regression only after the production
   behavior is fixed. The later operator2 Lane V pass should include a
   mutation/readback probe for each behavior.

## Implementation Order

1. `ckpt-nan-json-token`: add a recursive non-finite sanitizer and enforce
   strict JSON write semantics.
2. `ckpt-stage-notrestored`: restore the progress-pointer triple through
   `RunState.update_progress_pointer(...)`.
3. `ckpt-sceneclips-dead`: replace or supplement the source-string pin with a
   behavior fixture, then adjust `_build_scene_packages()` so valid restored
   clips survive without hiding missing-shot rebuild/reporting.

The mini-batch is small and tightly coupled enough for direct director2
implementation after this contract is accepted. If implementation scope grows
past these files or becomes five or more independent subtasks, re-route under
R-ORCH instead.

## Later Acceptance Bundle

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_nan_not_written_as_nonstandard_token \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_stage_progress_pointer_restored \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_sceneclips_restored_value_survives_build \
  -q

env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cross_controller.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
```

Operator2 Lane V should additionally probe:

- removing/disabling the non-finite sanitizer brings back a literal `NaN`;
- bypassing progress-pointer restore brings back the empty pointer;
- clearing restored `scene_clips` before `_build_scene_packages()` makes the
  behavior fixture fail.

## Next Trigger

`continue as director2` may proceed to the direct implementation only if the
user-principal intends to open this Wave-3 mini-batch. The next implementation
must stop at a landed diff plus explicit `operator2` verify-request. Push
remains user-gated.
