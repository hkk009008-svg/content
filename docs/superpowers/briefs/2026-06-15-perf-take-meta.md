# R-BRIEF: perf-take-meta - include performance takes in final-take metadata lookup

PRIORITY: MEDIUM        LANE: B (video/assembly/audio)
CROSS-CUTTING: no (does not touch auto_approve.py, cinema/context.py, core.py, or web_server.py)

## The defect

`CinemaPipeline._approved_take_metadata()` looks up
`approved_final_take_id` only in `motion_takes` and
`postprocess_variants`. `ReviewController.approve_take(..., "final")` can also
approve a `performance_takes` entry as the final take. When that happens, the
assembler sees `{}` instead of the take metadata, misses
`audio_embedded` / `dialogue_audio_in_clip`, and may mux standalone scene TTS
over a performance take that already carries the actor voice.

## Rule #12 - grep-the-writes

TARGET SYMBOLS: `performance_takes` and `approved_final_take_id`.

```text
$ rg -n "performance_takes|approved_final_take_id" cinema/shots/controller.py cinema/review/controller.py cinema_pipeline.py
cinema/shots/controller.py:951:          performance_takes:          appended-to (one take per call)
cinema/shots/controller.py:1142:            project_shot.setdefault("performance_takes", []).append(take)
cinema/review/controller.py:666:                if collection_name == "motion_takes":
cinema/review/controller.py:683:                if collection_name != "performance_takes":
cinema/review/controller.py:689:                motion_take_id = take_id if collection_name == "motion_takes" else _resolve_motion_source(shot, take)
cinema/review/controller.py:692:                shot["approved_final_take_id"] = take_id
cinema_pipeline.py:700:        take_id = shot.get("approved_final_take_id", "")
cinema_pipeline.py:703:        for collection in ("motion_takes", "postprocess_variants"):
```

Production write site confirmed: `generate_performance_take()` appends
`performance_takes`; `approve_take(..., "final")` writes
`approved_final_take_id` for non-keyframe take collections, including
`performance_takes`.

## Rule #13 - symmetric / sibling audit

SHARED STATE: the approved final take metadata consumed by assembly.

```text
$ rg -n "motion_takes|postprocess_variants|performance_takes" cinema_pipeline.py cinema/review/controller.py cinema/shots/controller.py
cinema/shots/controller.py:546:        for collection_name in ("keyframe_takes", "performance_takes", "motion_takes", "postprocess_variants"):
cinema/shots/controller.py:1142:            project_shot.setdefault("performance_takes", []).append(take)
cinema/shots/controller.py:1465:            project_shot.setdefault("motion_takes", []).append(take)
cinema/shots/controller.py:2513:                project_shot.setdefault("postprocess_variants", []).append(variant)
cinema/review/controller.py:692:                shot["approved_final_take_id"] = take_id
cinema_pipeline.py:703:        for collection in ("motion_takes", "postprocess_variants"):
```

Fold now:

- Search `performance_takes` in `_approved_take_metadata()` alongside the two
  existing final-video take collections.
- Preserve existing order for motion/postprocess behavior where possible; only
  add the missing approved-performance case.

Defer:

- `lipsync-veto` remains a separate `auto_approve.py` row and still requires
  the cross-cutting lock path. Do not fold it into this lane-only assembler fix.

## Full-shape pattern reference

MIRROR:

- Existing `_approved_take_metadata(shot)` helper shape in
  `cinema_pipeline.py`: static, read-only, returns `{}` on missing id or
  missing metadata, and returns `take.get("metadata") or {}` for a matching
  take.
- Existing final approval semantics in `cinema/review/controller.py`: final
  approval excludes keyframes but permits performance, motion, and postprocess
  takes.

## The fix

Expected scope:

- `cinema_pipeline.py`: update the helper docstring and collection tuple to
  include `performance_takes`.
- `tests/unit/test_postprocess_audio_siblings_xfail.py`: remove strict xfail
  from `test_performance_take_as_final_metadata_is_resolved` and update stale
  comments so it becomes a live regression. Leave the `lipsync-veto` strict
  xfail in place.
- `docs/REMEDIATION-INVENTORY.md`: mark `perf-take-meta` fixed with operator
  Lane V owed.

The change is small and tightly coupled, so director2 implements directly.

## Verification the operator/CI will run

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py::test_performance_take_as_final_metadata_is_resolved -q
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py -q
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_postprocess_audio_siblings_xfail.py::test_performance_take_as_final_metadata_is_resolved --runxfail -q --tb=short
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Expected:

- the performance metadata test passes as a live regression;
- the module still has the separate `lipsync-veto` xfail;
- the former pin under `--runxfail` passes;
- smoke remains OK.
