# R-BRIEF: Wave 2 checkpoint cluster

PRIORITY: MAJOR/MEDIUM. LANE: B. CROSS-CUTTING: no.

Rows:
- `ckpt-sceneidx-dead`
- `ckpt-shotaudio-loss`
- `ckpt-projectid-nocrosscheck`

## Seat And Scope

Live orientation:

```text
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 2
HEAD 16ed5e89 coord(status): director no-op after taskboard
UNREAD: 2
Wave 2 gate: UNMET counts={'verified': 20, 'open': 10}

$ env -u GIT_INDEX_FILE git log --oneline -5
16ed5e89 coord(status): director no-op after taskboard
9a0e35be coord(handoff): refresh wave2 taskboard handoff
90c1fee7 docs(handoff): director2 checkpoint handoff
d2c4b72c docs(handoff): operator2 standby after codex rules
9b56d399 docs(handoff): director protocol codified
```

Live state advanced during work:

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
757b2758 coord(status): operator standby after taskboard
16ed5e89 coord(status): director no-op after taskboard
9a0e35be coord(handoff): refresh wave2 taskboard handoff
90c1fee7 docs(handoff): director2 checkpoint handoff
d2c4b72c docs(handoff): operator2 standby after codex rules
```

No mailbox was consumed by director2. Unread status mail was read only. No lock was claimed and no push/spend side effects were used.

Scope concern: the coordinator allowed-write line named `cinema/checkpoint.py`, but `ckpt-sceneidx-dead` is not a real runtime fix without the `cinema_pipeline.py` scene loop caller that passes `completed_scene_idx` and skips restored completed scenes. This brief keeps the widened production scope bounded to that checkpoint runtime path and asks operator2 to review the scope explicitly.

## Red Evidence

The shared working tree already contained unstaged checkpoint edits before director2 could run the exact red command in-place, so red was reproduced from a detached temporary worktree at committed `HEAD`.

```text
$ env -u GIT_INDEX_FILE git worktree add --detach /tmp/content-ckpt-red-20260615T1934 HEAD
HEAD is now at 757b2758 coord(status): operator standby after taskboard

$ env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_sceneidx_populated_at_runtime \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_shotaudio_survives_round_trip \
  tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_projectid_crosscheck_on_restore \
  --runxfail -q --tb=short
FAILED test_ckpt_sceneidx_populated_at_runtime: assert 0 == 1
FAILED test_ckpt_shotaudio_survives_round_trip: assert {} == {'shot-1': ..., 'shot-2': ...}
FAILED test_ckpt_projectid_crosscheck_on_restore: Failed: DID NOT RAISE
3 failed in 0.03s
```

## Rule 12: Grep The Writes

Target: `completed_scene_indices`.

```text
$ rg -n "completed_scene_indices\.add|completed_scene_indices|\"completed_scene_indices\"|completed_scene_idx" cinema/checkpoint.py cinema_pipeline.py cinema/runstate.py cinema/services.py
cinema/checkpoint.py:87:    def _save_checkpoint(self, completed_scene_idx: int = -1):
cinema/checkpoint.py:92:        if completed_scene_idx >= 0:
cinema/checkpoint.py:93:            self._runstate.completed_scene_indices.add(completed_scene_idx)
cinema/checkpoint.py:100:            "completed_scene_indices": sorted(self._runstate.completed_scene_indices),
cinema/checkpoint.py:155:        completed = state.get("completed_scene_indices", [])
cinema/checkpoint.py:191:        completed = set(state.get("completed_scene_indices", []))
cinema/checkpoint.py:192:        self._runstate.completed_scene_indices = completed
cinema_pipeline.py:1004:            if scene_idx in completed_scene_indices:
cinema_pipeline.py:1068:            self._save_checkpoint(completed_scene_idx=scene_idx)
cinema/services.py:122:    completed = state.get("completed_scene_indices", [])
```

Target: `shot_audio`.

```text
$ rg -n "self\.shot_audio\[[^]]+\]\s*=|self\._runstate\.shot_audio\s*=|shot_audio\s*=\s*\{" cinema_pipeline.py cinema/runstate.py tests/unit/test_discovery_checkpoint_xfail.py
cinema_pipeline.py:198:        self._runstate.shot_audio = value
cinema_pipeline.py:609:            self.shot_audio[shot_id] = output_path
cinema_pipeline.py:623:            self.shot_audio[shot_id] = output_path
tests/unit/test_discovery_checkpoint_xfail.py:105:    rs.shot_audio = {"shot-1": "/audio/shot1.wav", "shot-2": "/audio/shot2.wav"}
```

Target: `project_id`.

```text
$ rg -n "\"project_id\"|saved_project_id|current_project_id" cinema/checkpoint.py
cinema/checkpoint.py:96:            "project_id": self.project["id"],
cinema/checkpoint.py:176:        saved_project_id = state.get("project_id")
cinema/checkpoint.py:177:        current_project_id = self.project.get("id")
cinema/checkpoint.py:178:        if saved_project_id and current_project_id and saved_project_id != current_project_id:
```

## Rule 13: Sibling Audit

Shared state: checkpoint JSON save, restore, resume summary, and HTTP checkpoint summary.

```text
$ rg -n "state\.get\(|state\[|json\.dump|json\.load|_load_checkpoint|resume_info|checkpoint_info" cinema/checkpoint.py cinema/services.py
cinema/checkpoint.py:114:                json.dump(state, f, indent=2, ensure_ascii=False, default=str)
cinema/checkpoint.py:121:    def _load_checkpoint(self) -> dict:
cinema/checkpoint.py:150:    def resume_info(self) -> dict:
cinema/checkpoint.py:155:        completed = state.get("completed_scene_indices", [])
cinema/checkpoint.py:172:        state = self._load_checkpoint()
cinema/checkpoint.py:176:        saved_project_id = state.get("project_id")
cinema/checkpoint.py:184:        self._runstate.scene_clips = state.get("scene_clips", {})
cinema/checkpoint.py:185:        self._runstate.scene_audio = state.get("scene_audio", {})
cinema/checkpoint.py:186:        self._runstate.shot_audio = state.get("shot_audio", {})
cinema/checkpoint.py:191:        completed = set(state.get("completed_scene_indices", []))
cinema/services.py:100:def checkpoint_info(project_id: str) -> dict:
cinema/services.py:122:    completed = state.get("completed_scene_indices", [])
```

Audit result:
- `resume_info()` and `checkpoint_info()` already read `completed_scene_indices`, so saving/restoring the populated set updates both summaries.
- `shot_audio` has runtime writers in `_ensure_shot_audio`; save/restore now mirrors `scene_audio` and `scene_foley`.
- `project_id` is already saved; restore now fails closed on mismatch before assigning any runstate fields.
- Deferred siblings remain intentionally outside this cluster: NaN token encoding, `scene_clips` rebuild overwrite, and progress-pointer restore.

## Fix

Files in the implementation scope:
- `cinema/checkpoint.py`
- `cinema_pipeline.py`
- `tests/unit/test_discovery_checkpoint_xfail.py`
- `ARCHITECTURE.md` and `docs/PROGRAM-MANUAL.md` mechanical anchor refreshes required by `scripts/ci_smoke.py`

Changes:
- `_save_checkpoint(completed_scene_idx=...)` records completed scene indices before serializing state.
- checkpoint state now saves and restores `RunState.shot_audio`.
- `_restore_from_checkpoint()` compares saved `project_id` against the active project id and raises `ValueError` on mismatch before mutating runstate.
- `CinemaPipeline.generate(resume=True)` uses the restored completed-scene set to skip completed scenes and saves each scene completion with `completed_scene_idx=scene_idx`.
- The three fixed checkpoint pins became ordinary regression tests; deferred checkpoint pins remain strict xfail.

## Verification

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_sceneidx_populated_at_runtime tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_shotaudio_survives_round_trip tests/unit/test_discovery_checkpoint_xfail.py::test_ckpt_projectid_crosscheck_on_restore --runxfail -q --tb=short
3 passed in 0.03s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_checkpoint_xfail.py --runxfail -q --tb=short
3 failed, 3 passed in 2.41s
Remaining failures are deferred checkpoint rows: ckpt-nan-json-token, ckpt-sceneclips-dead, ckpt-stage-notrestored.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_cross_controller.py tests/unit/test_spent_usd_resume.py -q --tb=short
41 passed in 3.00s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 20, 'open': 7, 'fixed': 3}
PRODUCT ORACLE BLOCKER: missing logs/product-oracle-*.json
PYTEST summary: 9 failed, 58 passed
```

## Residual Risks

- Operator2 GO is still required; this brief does not mark rows verified.
- The production scope includes `cinema_pipeline.py` because scene-index runtime population needs the caller. This is the main Lane V scope concern.
- Wave 2 remains UNMET for unrelated HTTP/postprocess rows, the product-oracle artifact, and deferred checkpoint pins.
- `docs/REMEDIATION-INVENTORY.md` had concurrent dirty edits marking these rows `fixed`; director2 did not rely on that as verified state.
