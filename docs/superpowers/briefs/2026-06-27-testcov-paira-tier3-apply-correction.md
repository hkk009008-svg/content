# R-BRIEF: testcov-paira-tier3-apply-correction - ShotController correction orchestration coverage

PRIORITY: MEDIUM        LANE: A (image/identity)
CROSS-CUTTING: no

No lock is claimed. This is test-only coverage for
`cinema/shots/controller.py`; it does not touch the lock modules
`auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`.
Co-sign is N/A.

## The Coverage Gap

Coordinator route:
`coordination/mailbox/sent/2026-06-26T23-10-00Z-coordinator-to-all-coordination.md`
assigns Pair-A Tier 3 orchestration coverage after Pair-A Tier 1 is stable.
Operator GO for Pair-A Tier 1 is committed as `f3f85b1f`.

Target from `docs/TEST-COVERAGE-ANALYSIS-2026-06-14.md`:

```text
$ sed -n '152,168p' docs/TEST-COVERAGE-ANALYSIS-2026-06-14.md
| `cinema/shots/controller.apply_correction` | `cinema/shots/controller.py:2331` | Operator-facing correction orchestration (face-swap/upscale/RIFE/grade) -- indirect only |
```

Current source has moved; the live method starts at `controller.py:2441`.

```text
$ nl -ba cinema/shots/controller.py | sed -n '2441,2624p'
2441 def apply_correction(...)
2469 if action == "regenerate_image":
2477 if action == "regenerate_video":
2487 if action == "face_swap":
2608 def _mutator(...)
2609     project_shot.setdefault("postprocess_variants", []).append(variant)
2612 stored_variant = self._mutate_shot(shot_id, _mutator)
2613 self._host._rebuild_review_clips()
2614 self._host._save_checkpoint()
2615 self.progress("POSTPROCESS_READY", ...)
```

The old analysis is partially stale: several sibling tests now cover audio flag
propagation and one guided-pipeline color-grade persistence path. This brief
therefore targets the remaining controller-orchestration contract: direct
regenerate dispatch and successful face-swap postprocess bookkeeping.

## Rule #12 - grep-the-writes

TARGET SYMBOL: `postprocess_variants` write through `apply_correction`.

```text
$ rg -n "postprocess_variants|generate_keyframe_take\\(|generate_motion_take\\(|face_swap_enabled|characters_in_frame|_rebuild_review_clips|_save_checkpoint|POSTPROCESS_READY" cinema/shots/controller.py tests/unit/test_postprocess_audio_propagation.py tests/unit/test_guided_pipeline.py tests/unit/test_phase_c_vision.py tests/unit/test_iterate_endpoint.py
cinema/shots/controller.py:2470:                return self.generate_keyframe_take(
cinema/shots/controller.py:2478:                return self.generate_motion_take(scene_id, shot_id)
cinema/shots/controller.py:2492:                if not _settings.get("face_swap_enabled", True):
cinema/shots/controller.py:2496:                chars = shot.get("characters_in_frame", []) or scene.get("characters_present", [])
cinema/shots/controller.py:2609:                project_shot.setdefault("postprocess_variants", []).append(variant)
cinema/shots/controller.py:2613:            self._host._rebuild_review_clips()
cinema/shots/controller.py:2614:            self._host._save_checkpoint()
cinema/shots/controller.py:2616:                "POSTPROCESS_READY",
tests/unit/test_guided_pipeline.py:139:        self.assertEqual(len(updated_shot["postprocess_variants"]), 1)
tests/unit/test_postprocess_audio_propagation.py:250:        "postprocess_variants": [],
tests/unit/test_postprocess_audio_propagation.py:281:        return fake_shot["postprocess_variants"][-1]
tests/unit/test_phase_c_vision.py:1093:            result = self._pipeline.apply_correction(self._shot_id, "face_swap", {})
```

Runtime write confirmed: `project_shot.setdefault("postprocess_variants",
[]).append(variant)` at `cinema/shots/controller.py:2609` is the production
write site. The new tests must observe this write through `apply_correction`,
not by mutating a test fixture directly.

## Rule #13 - Sibling Audit

SHARED STATE: correction action dispatch and postprocess variant persistence.

Sibling coverage already present:

```text
$ nl -ba tests/unit/test_postprocess_audio_propagation.py | sed -n '234,405p'
234 _make_correction_ctrl(...)
278 def _capture_mutate(...)
293 class TestApplyCorrectionFlagPropagation:
295 test_color_grade_variant_inherits_audio_embedded
310 test_speed_variant_inherits_dialogue_audio_in_clip
324 test_strip_variant_without_audio_gets_no_flag
360 test_lip_sync_variant_sets_dialogue_audio_in_clip_directly
378 test_lip_sync_variant_records_namespaced_lipsync_cost

$ nl -ba tests/unit/test_guided_pipeline.py | sed -n '118,145p'
125 fake_color_grade(...)
130 with mock.patch.object(phase_c_ffmpeg, "apply_color_grade", ...)
139 self.assertEqual(len(updated_shot["postprocess_variants"]), 1)
141 self.assertNotEqual(variant["id"], motion_take["id"])
142 self.assertEqual(variant["source_take_id"], motion_take["id"])

$ nl -ba tests/unit/test_phase_c_vision.py | sed -n '1060,1115p'
1093 result = self._pipeline.apply_correction(self._shot_id, "face_swap", {})
```

Fold into this slice:

- `regenerate_image` dispatches to `generate_keyframe_take` with positive and
  negative prompts and does not create a postprocess variant.
- `regenerate_video` dispatches to `generate_motion_take` with the scene and shot
  ids and does not create a postprocess variant.
- successful `face_swap` uses `characters_in_frame` before scene-level fallback,
  writes a `postprocess` variant with `source_take_id`, rebuilds review clips,
  saves a checkpoint, and emits `POSTPROCESS_READY` progress.

Deferred as already covered:

- audio flag inheritance and lip-sync cost recording are covered in
  `tests/unit/test_postprocess_audio_propagation.py`.
- persisted color-grade variant behavior is covered in
  `tests/unit/test_guided_pipeline.py`.
- face-swap cascade `None` error surface is covered in
  `tests/unit/test_phase_c_vision.py`.

## Full-Shape Pattern Reference

MIRROR:

- `tests/unit/test_postprocess_audio_propagation.py:234` constructs a minimal
  real `ShotController` and stubs only host, storage, and the transform boundary.
- `tests/unit/test_iterate_endpoint.py:104` stubs direct controller dispatch to
  assert orchestration arguments without running the full media pipeline.
- `tests/unit/test_guided_pipeline.py:118` verifies a postprocess variant appends
  instead of overwriting source motion takes.

No HTTP endpoint is added, so R-PID is N/A.

## The Fix

Add a focused tests-only module:
`tests/unit/test_shot_controller_apply_correction.py`.

Expected tests:

1. `test_regenerate_image_dispatches_prompts_to_keyframe_generation`
2. `test_regenerate_video_dispatches_to_motion_generation`
3. `test_face_swap_success_uses_in_frame_character_and_records_postprocess_variant`

Bounded files:

- create `tests/unit/test_shot_controller_apply_correction.py`
- no production file changes expected
- no network, pod, paid API, dependency, lock, or push side effects

Implementation mode: direct director implementation. The slice is small and
tightly coupled, below R-ORCH thresholds.

## Verification

Director preflight:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_shot_controller_apply_correction.py -q
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_shot_controller_apply_correction.py tests/unit/test_postprocess_audio_propagation.py tests/unit/test_guided_pipeline.py tests/unit/test_phase_c_vision.py::TestApplyCorrectionFaceSwapReason -q
```

Operator Lane V should independently run the focused module and inspect that the
tests are test-only, load-bearing, and scoped to this brief.

Director local preflight:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_shot_controller_apply_correction.py -q
... [100%]
3 passed in 1.47s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_shot_controller_apply_correction.py tests/unit/test_postprocess_audio_propagation.py tests/unit/test_guided_pipeline.py tests/unit/test_phase_c_vision.py::TestApplyCorrectionFaceSwapReason -q
.................................................. [100%]
50 passed in 3.57s
```
