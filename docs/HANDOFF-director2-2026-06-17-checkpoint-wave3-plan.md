# Director2 Handoff - Checkpoint Wave-3 Mini-Batch Plan

Generated: `2026-06-16T16:10:32Z` (`2026-06-17T01:10:32+0900` Asia/Seoul)
Repo: `/Users/hyungkoookkim/Content`

This is a director2 planning/status artifact. Trust live git, mailbox, gate,
and filesystem state over this snapshot if they diverge.

## Source Route Consumed

- Read same-seat handoff first:
  `docs/HANDOFF-director2-2026-06-17-guardrail-lanev-go.md`.
- Read coordinator route:
  `coordination/mailbox/sent/2026-06-16T16-03-34Z-coordinator-to-all-coordination.md`.
- Director2 unread before consume: `1`.
- Consumed director2 mailbox through `2026-06-16T16:03:34Z`:

```text
coordination/bin/consume-events director2 --to 2026-06-16T16:03:34Z
-> cursor director2: 2026-06-16T15:20:30Z -> 2026-06-16T16:03:34Z; unread now: 0
```

The coordinator route authorized planning/status only. This artifact does not
authorize or perform production code edits, remediation inventory transitions,
lock claims/releases, push, pod spend, paid API spend, dependency edits, or
product-oracle/log changes.

## Route-Start Live Evidence

```text
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 2
-> HEAD d89c5fe9 operator2(handoff): stand by for checkpoint plan
-> main is 3 ahead / 0 behind origin/main
-> director2 UNREAD: 1 for the coordinator checkpoint planning route
-> Wave 2 gate: MET counts={'verified': 30}; selector tail 71 passed
```

```text
env -u GIT_INDEX_FILE git log --oneline -5
-> d89c5fe9 operator2(handoff): stand by for checkpoint plan
-> a524c7ba coord(cursor): director consume checkpoint planning route
-> 80f6a8a2 coord(route): open checkpoint planning pass
-> 7dde8947 docs(handoff): capture coordinator push boundary
-> 8bf41bcf director2(status): close guardrail handoff Lane V
```

```text
.venv/bin/python scripts/ci_smoke.py
-> OK
-> existing advisory only: unknown verify-addendum kind and R2 warnings
```

```text
.venv/bin/python scripts/wave_gate_check.py 2
-> Wave 2 gate: MET counts={'verified': 30}
-> selector tail 71 passed
```

## Pre-Commit Freshness Refresh

While this plan was being verified, `HEAD` advanced from other seat activity:

```text
env -u GIT_INDEX_FILE git log --oneline -8
-> 30e1af59 docs(handoff): director checkpoint plan standby
-> 5ca9e824 coord(cursor): operator consume checkpoint route
-> d89c5fe9 operator2(handoff): stand by for checkpoint plan
-> a524c7ba coord(cursor): director consume checkpoint planning route
-> 80f6a8a2 coord(route): open checkpoint planning pass
-> 7dde8947 docs(handoff): capture coordinator push boundary
-> 8bf41bcf director2(status): close guardrail handoff Lane V
-> b3a060b7 operator(verify): GO guardrail handoff prompts
```

```text
env -u GIT_INDEX_FILE git show --stat --oneline 5ca9e824 30e1af59
-> 5ca9e824 touched only coordination/mailbox/seen/operator.txt
-> 30e1af59 added docs/HANDOFF-director-2026-06-17-checkpoint-plan-standby.md
```

No newer mailbox event addressed to `director2` appeared before this commit.
The only sent event newer than this plan file was the director2 status event
created for operator2:
`coordination/mailbox/sent/2026-06-16T16-12-45Z-director2-to-operator2-status.md`.

```text
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 2
-> HEAD 30e1af59 docs(handoff): director checkpoint plan standby
-> main is 5 ahead / 0 behind origin/main
-> director2 UNREAD: 0
-> Wave 2 gate: MET counts={'verified': 30}; selector tail 71 passed
```

## Current Deferred Pin Evidence

```text
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_nan_not_written_as_nonstandard_token \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_stage_progress_pointer_restored \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_sceneclips_restored_value_survives_build \
  --runxfail -q --tb=short
-> 3 failed in 1.66s
```

Failure signatures:

- `ckpt-nan-json-token`: checkpoint file contains literal `NaN`.
- `ckpt-stage-notrestored`: `current_stage` restores as `''` instead of
  `"MOTION"`.
- `ckpt-sceneclips-dead`: `CinemaPipeline._build_scene_packages()` still
  contains the unconditional `self.scene_clips = {}` reset.

Relevant current source evidence:

```text
rg -n "CheckpointStore|current_stage|scene_clips|ckpt" docs tests cinema scripts coordination/mailbox/sent
-> tests/unit/test_discovery_checkpoint_xfail.py:13: confirmed[21] Wdefer:MINOR:ckpt-nan-json-token
-> tests/unit/test_discovery_checkpoint_xfail.py:14: confirmed[22] Wdefer:MINOR:ckpt-sceneclips-dead
-> tests/unit/test_discovery_checkpoint_xfail.py:15: confirmed[23] Wdefer:MINOR:ckpt-stage-notrestored
-> docs/REMEDIATION-INVENTORY.md:65: ckpt-nan-json-token ... wave defer ... status open
-> docs/REMEDIATION-INVENTORY.md:66: ckpt-sceneclips-dead ... wave defer ... status open
-> docs/REMEDIATION-INVENTORY.md:67: ckpt-stage-notrestored ... wave defer ... status open
```

```text
rg -n "def _build_scene_packages|self\\.scene_clips = \\{\\}|scene_clips" \
  cinema_pipeline.py cinema/shots/controller.py cinema/runstate.py tests/unit/test_cross_controller.py
-> cinema_pipeline.py:709: def _build_scene_packages(...)
-> cinema_pipeline.py:713: self.scene_clips = {}
-> cinema_pipeline.py:737: self.scene_clips[scene_id] = clips
-> cinema/shots/controller.py:2646: clips = self._runstate.scene_clips.get(scene_id, [])
-> cinema/shots/controller.py:2656: self._runstate.scene_clips[scene_id] = clips
-> cinema/runstate.py:87: scene_clips: dict = field(default_factory=dict)
```

```text
sed -n '140,210p' cinema/runstate.py
-> RunState.update_progress_pointer(stage, scene_id, shot_id) writes all three
   progress-pointer fields atomically.
```

## Director2 Recommendation

Open all three Pair-B deferred checkpoint rows as a small, offline Wave-3
checkpoint hardening mini-batch:

- `ckpt-nan-json-token`
- `ckpt-stage-notrestored`
- `ckpt-sceneclips-dead`

Rationale:

- All three have strict pins that still fail for the recorded reasons.
- All three are no-spend and can be exercised with local checkpoint fixtures.
- The work is cohesive around checkpoint/resume correctness.
- No cross-cutting lock is indicated by the current plan because the expected
  production targets are `cinema/checkpoint.py`, `cinema_pipeline.py`, and tests;
  none are one of `auto_approve.py`, `cinema/context.py`, `core.py`, or
  `web_server.py`.
- No Pair-A Tier-A co-sign is indicated; these are Pair-B checkpoint/pipeline
  mechanics and do not change Pair-A identity/image policy.

Do not keep the rows deferred if the next wave is an offline/no-spend hardening
pass. They are small enough to plan and review together, but the implementation
should still land behind a director2 R-BRIEF or equivalent Wave-3 checkpoint
stub-contract addendum before code changes.

## Proposed Row Order

1. `ckpt-nan-json-token`

   First because it is the save-side serialization chokepoint and independent of
   runtime resume control flow. Acceptance: remove the strict xfail mark or
   convert it to a live regression, make
   `test_ckpt_nan_not_written_as_nonstandard_token` pass, and include a
   non-vacuity check that reverting/removing the non-finite sanitizer reintroduces
   the literal `NaN` failure. Candidate implementation shape: recursively map
   non-finite floats to `None` before JSON writing and/or enforce
   `allow_nan=False` after sanitization.

2. `ckpt-stage-notrestored`

   Second because it stays inside `CheckpointStore._restore_from_checkpoint()`
   and completes the save/restore contract for fields already persisted. Acceptance:
   make `test_ckpt_stage_progress_pointer_restored` pass and confirm restore uses
   one atomic triple assignment path, preferably `RunState.update_progress_pointer`,
   rather than three scattered writes.

3. `ckpt-sceneclips-dead`

   Third because it is the only row that reaches into `cinema_pipeline.py` and
   has the highest blast radius. Acceptance: replace or supplement the current
   source-string pin with a behavior-level checkpoint fixture that proves restored
   `scene_clips` are not discarded by `_build_scene_packages()`, then make
   `test_ckpt_sceneclips_restored_value_survives_build` pass. The implementation
   should preserve rebuilt clips for scenes that truly need rebuilding and should
   not silently skip missing approved shots.

## Stub-Contract Addendum

A small Wave-3 checkpoint stub-contract addendum is required before
implementation. The existing Wave-2 stub contract has a checkpoint fixture row,
but its matrix was issued for Wave-2 and does not fully specify these deferred
fault modes or the scene-clips behavior test shape.

The addendum should be short and test-only. It should specify:

- checkpoint JSON serialization must reject or sanitize non-finite values before
  write, with strict JSON parse evidence;
- progress-pointer restore must round-trip `current_stage`, `current_scene_id`,
  and `current_shot_id` as one coherent pointer;
- scene package rebuilding must be fixture-driven and behavior-level, proving
  restored `scene_clips` survive when valid while still rebuilding/reporting
  missing clips when necessary;
- no real I/O beyond tmpdir checkpoint files, no network, no pod, no paid API,
  and no product-oracle artifact is required for this mini-batch.

## Acceptance Evidence For A Later Implementation

Minimum command bundle after a future implementation diff:

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

Operator2 should add at least one mutation/readback probe per changed behavior
before GO:

- sanitizer removed -> literal `NaN` failure returns;
- progress-pointer assignment removed -> pointer restores empty again;
- restored `scene_clips` are cleared -> behavior fixture fails.

## Exact Next Trigger

`continue as operator2` to cold-review this director2 checkpoint mini-batch plan
for planning readiness, no-spend/no-lock boundaries, and whether the stub-contract
addendum is sufficient before implementation. This is not a Lane V verify-request;
Lane V starts only after a later implementation diff plus explicit verify-request.

After operator2 publishes a planning-readiness report, coordinator can reconcile
and route the Wave-3 checkpoint addendum/R-BRIEF if the user-principal wants the
mini-batch opened.

Push remains user-gated.
