# Performance-Capture Phase — Implementation Handoff

**Branch:** any feature branch off `refactor/architecture-cleanup` (suggested: `feature/performance-capture`).
**Audience:** the next Claude session working in the local repo, picking up from a clean smoke (`docs/REFACTOR_HANDOFF.md §0`).
**Goal:** insert a **Performance Capture** stage between `keyframe_render` and `motion_render` that conditions video generation on a *driving performance* (face + body), so motion comes from a real human reference instead of the video model's defaults.

> One-line frame: the only remaining technical gap between this pipeline and the boutique-studio AI cinema tier (Promise Studios / Asteria / Solo Films) is **performance**. LoRAs are in. Storyboard is in. Resolve sits on the back end. This slice closes the loop.

---

## 1. Why this matters (the WHY before the WHAT)

Pure text-to-video models guess what "acting" is. They average over every actor in their training set. The result is the unmistakable AI-video tell: dead eye lines, wrong beat timing, gesture drift, broken hands. No prompt fix solves it — the model has no performance *target*, only a description.

A driving video gives the model a target. The keyframe defines *who* (PuLID + LoRA already does this), the driving video defines *how they move*. The combination is the boutique-tier deliverable.

Visible deltas after this lands:

- Eye lines that actually land on the other character in dialogue 2-shots
- Beat timing — pauses before lines, lean-ins, head-cocks
- Body-language continuity across cuts of the same character
- Hand gestures that don't break (the #1 AI-tell)
- Lip sync that passes the squint test (especially when chained with the existing `lip_sync.py` polish pass)

The user has 25 years of music production and 3 years of cinema. They will *hear and see* the difference immediately on the first dialogue shot.

---

## 2. Where the phase fits in the pipeline

Current order (from `cinema_pipeline.py:generate()` around line 695–768):

```
… → audio → keyframe_render → KEYFRAME_REVIEW gate → motion_render → REVIEW gate → assembly → …
```

New order:

```
… → audio → keyframe_render → KEYFRAME_REVIEW gate →
    performance_capture → PERFORMANCE_REVIEW gate →
    motion_render → REVIEW gate → assembly → …
```

`PERFORMANCE_REVIEW` is the new operator gate where you preview the driving-video / animated face and either approve, re-record (upload a new driving video), or skip (fall back to pure text-to-video). The gate is critical — the whole upside of this phase comes from the operator being able to *direct* the performance.

---

## 3. Per-shot routing — which engine for which shot

This phase is **optional per shot**. The router decides:

| Shot type / signal | Engine | Driving video source | Notes |
|---|---|---|---|
| Has `dialogue` non-empty, classified `portrait` or `medium` | **Runway Act-One** | Auto-generated from TTS audio + keyframe via SadTalker/Hedra OR operator upload | Best dialogue tool on the market right now. Already have `RUNWAYML_API_SECRET` configured. |
| Has `dialogue` non-empty, close-up only, on a budget | **LivePortrait (ComfyUI)** | Same TTS-driven driving face as above | Free on existing Railway A100. Cheaper than Act-One when running many shots. |
| No dialogue, character action (`action` shot type) | **Viggle** | Operator-uploaded iPhone reference of the movement | Full-body retargeting. Needs operator to actually act it out. |
| `wide` or `landscape` shot type | **SKIP** | n/a | Character is too small in frame for performance to matter. Mark `performance_required = False`. |
| `wide` shot with dialogue (rare) | **SKIP** | n/a | Same — face is sub-100px. Save the spend. |

**Routing table lives in `domain/performance.py:route_performance_engine(shot, scene)`.** Mirrors the pattern from `workflow_selector.WORKFLOW_TEMPLATES`.

### Driving-video sourcing modes

Three modes for where the driving video *comes from*. The phase tries them in order until it has one:

- **Mode A — Operator upload.** Web UI exposes a file slot at `projects/{pid}/performance_inputs/{shot_id}/driving.mp4`. If present, use it. Best for hero shots, action beats, anything where the operator has 30 seconds to act it out on a phone.
- **Mode B — TTS-driven auto-generation.** For dialogue shots with no operator upload, call SadTalker (open source, ComfyUI node) or Hedra (API) with `audio_path = shot["audio_line_path"]` + `image_path = approved_keyframe_path`. Produces a driving face video that lip-syncs the TTS. ~$0.05–0.10/shot via Hedra, free via SadTalker on Railway.
- **Mode C — Skip.** If shot is wide/landscape or operator explicitly skipped via the gate, leave `approved_performance_take_id = ""` and let `motion_render` fall through to its current text-to-video path.

Default for first ship: **Mode B for all dialogue shots, Mode A optional via UI, Mode C for everything else.** Get the autopilot path lit up first, then add the operator-upload UI in a follow-up slice.

---

## 4. Data structure additions

### `make_shot()` in `domain/project_manager.py`

Add four new fields. Match the existing `keyframe_takes` / `motion_takes` pattern exactly:

```python
"performance_takes": [],                # list[take dict] — make_take(kind="performance", ...)
"approved_performance_take_id": "",     # like approved_keyframe_take_id
"performance_engine": "",               # "ACT_ONE" | "LIVE_PORTRAIT" | "VIGGLE" | "SKIP" | ""
"driving_video_path": "",               # operator-uploaded reference, if any
```

Also update the migration in `domain/project_manager.py` around line 423–445 (the block that fills missing keys on legacy projects) to add the same four keys with safe defaults — same shape as the existing `approved_keyframe_take_id` migration.

### Take payload (`make_take` already supports this)

`make_take(kind="performance", source_take_id=approved_keyframe_id, metadata={"engine": ..., "scene_id": ..., "shot_id": ..., "driving_source": "upload"|"tts_auto", "audio_path": ..., "duration_s": ...})`.

### Project-level

No new fields needed. Performance routing is per-shot.

---

## 5. New module layout

Place pure logic under top-level domain packages, **not** under `cinema/phases/` (per `REFACTOR_HANDOFF.md §6 Step 2`). Phase wrappers live in `cinema/phases/`.

```
domain/performance.py                  # Pure routing logic. route_performance_engine(), should_capture(), shot_needs_driving_video().
performance/                           # New top-level package, sibling of audio/, llm/, identity/.
  __init__.py
  _router.py                           # Dispatch by engine name → adapter. Mirrors phase_c_ffmpeg.generate_ai_video().
  act_one.py                           # Runway Act-One adapter. generate_act_one_performance(image, audio, driving=None) -> mp4.
  live_portrait.py                     # ComfyUI LivePortrait adapter. Uses settings.comfyui_server_url.
  viggle.py                            # Viggle adapter (needs new VIGGLE_API_KEY).
  driving_video.py                     # Mode B helpers: synth_driving_face_from_audio() via SadTalker/Hedra.
cinema/phases/performance.py           # PerformanceCapturePhase — iterator phase wrapping ShotController.generate_performance_take().
```

Why a new top-level `performance/` package and not `audio/performance.py` or `cinema/performance.py`:
- It's a **new domain** (performance retargeting), not an audio submodule and not a phase wrapper.
- Sibling-package shape matches the established pattern (`audio/`, `llm/`, `identity/`, `domain/`) — see `CLAUDE.md` package layout table.
- Keeps `cinema/phases/performance.py` as the thin Phase wrapper that imports from `performance.*`, identical to how `cinema/phases/keyframe_render.py` is a thin loop around `ShotController.generate_keyframe_take()`.

---

## 6. Engine adapters — concrete API contracts

Each adapter is a pure function that takes the inputs and returns a path to a generated mp4 (or `None` on failure). No state, no cross-import — match the shape of `phase_c_ffmpeg.generate_ai_video()`.

### `performance/act_one.py`

```python
def generate_act_one_performance(
    keyframe_path: str,
    audio_path: str,
    output_mp4: str,
    *,
    driving_video_path: str | None = None,
    duration_s: float = 5.0,
    character_id: str = "",
) -> str | None:
    """
    Runway Act-One: condition the keyframe character on a driving performance.

    If driving_video_path is None, Runway will auto-generate from audio
    (Act-One has audio→performance mode). If provided, the driving video
    takes priority and audio is used only for lip-sync alignment.

    Auth: settings.runwayml_api_secret (already configured).
    Endpoint: POST https://api.dev.runwayml.com/v1/character_performance
    Polling: GET /v1/tasks/{id} until status == "SUCCEEDED" | "FAILED".
    Cost: log via cost_tracker.log_api(provider="runway", model="act_one",
          operation="performance_capture", cost_usd≈0.05*duration_s).
    """
```

Runway's Act-One docs: https://docs.dev.runwayml.com (search "character performance"). Confirm exact endpoint when implementing — the API has been moving. Their Python SDK is `runwayml`. If the SDK exposes Act-One directly, prefer the SDK over raw POST.

### `performance/live_portrait.py`

```python
def generate_live_portrait_performance(
    keyframe_path: str,
    driving_video_path: str,
    output_mp4: str,
    *,
    duration_s: float = 5.0,
) -> str | None:
    """
    LivePortrait via ComfyUI on the existing Railway A100.

    Requires the ComfyUI-LivePortraitKJ custom node (free, MIT). Build the
    workflow JSON the same way comfyui_workflow_gen.py builds the keyframe
    workflow. Pattern from RAILWAY_GUIDE.md "Phase 3: The Python Bridge".

    Driving video is mandatory for this engine. If you only have audio,
    pre-synth a driving face via driving_video.synth_driving_face_from_audio().

    Cost: log as provider="comfyui", model="live_portrait", with
    Railway GPU-minute cost (~$0.02–0.04 per 5s shot).
    """
```

LivePortrait paper & weights: https://liveportrait.github.io. ComfyUI node: `ComfyUI-LivePortraitKJ` (Kijai's port — most reliable).

### `performance/viggle.py`

```python
def generate_viggle_performance(
    keyframe_path: str,
    driving_video_path: str,
    output_mp4: str,
    *,
    background_mode: str = "white",  # "white" | "green" | "transparent"
) -> str | None:
    """
    Viggle: full-body motion retargeting. Driving video shows a human
    performing the motion; Viggle maps it onto the character in the
    keyframe.

    Auth: new env var VIGGLE_API_KEY (add to Settings + .env.example).
    Cost: $0.10–0.25 per clip. Log as provider="viggle".
    """
```

### `performance/driving_video.py` (Mode B helpers)

```python
def synth_driving_face_from_audio(
    audio_path: str,
    keyframe_path: str,
    output_mp4: str,
    *,
    engine: str = "sadtalker",  # "sadtalker" | "hedra"
) -> str | None:
    """
    Generate a driving face video from TTS audio + a still keyframe.

    Used as an intermediate step when no operator-uploaded driving
    video exists for a dialogue shot. Output feeds into Act-One or
    LivePortrait as the driving_video_path argument.

    SadTalker:  free, runs on Railway via ComfyUI node ComfyUI-SadTalker.
    Hedra:      API, ~$0.05/shot, better lip motion. Add HEDRA_API_KEY env.
    """
```

---

## 7. ShotController integration

Add **one** new method to `cinema/shots/controller.py`, modeled exactly on `generate_motion_take` (line 366) and `generate_keyframe_take` (line 257). Same precondition pattern, same mutator pattern, same progress events.

```python
def generate_performance_take(self, scene_id: str, shot_id: str) -> dict:
    """
    Per-shot performance capture.

    Precondition: approved_keyframe_take_id must be set.
    Effect: writes a new entry to shot["performance_takes"] + updates
            shot["approved_performance_take_id"] (auto-approved on first
            successful generation; operator can reject via gate).

    Routes via domain.performance.route_performance_engine(shot, scene).
    If the router returns "SKIP", returns success with empty take and
    sets performance_engine = "SKIP" so motion_render falls through.
    """
```

Skeleton (~80 LOC, follow the existing pattern verbatim):

1. Resolve scene + shot via `self._find_shot`.
2. Guard: `plan_status == "approved"` and `approved_keyframe_take_id` non-empty (matches `generate_motion_take` lines 371–375).
3. Call `domain.performance.route_performance_engine(shot, scene)` → engine name.
4. If `"SKIP"`: mutate shot to set `performance_engine = "SKIP"`, return `{"success": True, "skipped": True}`.
5. Resolve driving video: check `shot["driving_video_path"]` first (Mode A), else synth via `performance.driving_video.synth_driving_face_from_audio()` (Mode B).
6. Call the engine adapter from `performance/_router.py:dispatch(engine, ...)`.
7. Build a take with `make_take(kind="performance", source_take_id=approved_keyframe_take_id, metadata={...})`.
8. Mutate shot: append to `performance_takes`, set `approved_performance_take_id = take["id"]`, set `performance_engine = engine`.
9. Save checkpoint, emit `PERFORMANCE_READY` progress event.
10. Return `{"success": True, "take": stored_take, "video": final_vid}`.

Add delegate wires in `cinema_pipeline.py` around line 263–267 (next to `generate_motion_take`):

```python
def generate_performance_take(self, *args, **kwargs):
    return self._shot_ctrl.generate_performance_take(*args, **kwargs)
```

---

## 8. `MotionRenderPhase` and `generate_motion_take` integration

The motion stage now needs to consume the approved performance take if one exists.

In `cinema/shots/controller.py:generate_motion_take` (line 424–435), the call site is:

```python
temp_vid = generate_ai_video(
    source_image,
    shot.get("camera", "zoom_in_slow"),
    target_api,
    vid_path,
    pacing="calculated",
    character_id=cc.get("primary_character", ""),
    multi_angle_refs=cc.get("multi_angle_refs", []),
    negative_prompt=shot.get("negative_constraints", ""),
    shot_type=resolved_shot_type,
    video_fallbacks=video_fallbacks,
)
```

Add one new kwarg, `driving_video_path`, sourced from the approved performance take:

```python
performance_take_id = shot.get("approved_performance_take_id", "")
driving_video_path = ""
if performance_take_id:
    driving_video_path = self._host._resolve_take_path(shot, performance_take_id) or ""

temp_vid = generate_ai_video(
    source_image,
    shot.get("camera", "zoom_in_slow"),
    target_api,
    vid_path,
    pacing="calculated",
    character_id=cc.get("primary_character", ""),
    multi_angle_refs=cc.get("multi_angle_refs", []),
    negative_prompt=shot.get("negative_constraints", ""),
    shot_type=resolved_shot_type,
    video_fallbacks=video_fallbacks,
    driving_video_path=driving_video_path,  # NEW
)
```

Then in `phase_c_ffmpeg.generate_ai_video` (line 130), add `driving_video_path: str = ""` to the signature, and pipe it through to the native handlers (Veo / Sora / Kling) that support image-to-video with a reference. Practical mapping:

- **Veo 3.1 native**: supports up to 4 reference images and a "reference video" — pass `driving_video_path` as reference video.
- **Sora 2 native**: supports `init_video` parameter — wire there.
- **Kling native**: supports `tail_image` and `start_image`. Driving video is not a first-class input, but can be used as a frame sequence via Kling's "Motion Brush" if you decode and re-encode. Skip for v1; fall through to no driving when target is Kling.
- **Runway Gen-4**: supports motion references natively — wire directly.
- **LTX**: keyframe-interpolation engine; doesn't take a driving video. Skip.

If the target engine doesn't accept a driving video, fall through silently (don't fail). The text-to-video path is still the baseline.

---

## 9. New phase: `cinema/phases/performance.py`

Copy `cinema/phases/motion_render.py` verbatim, rename the class, change the inner call. ~90 LOC. Identical cancellation + on_failure semantics.

```python
"""PerformanceCapturePhase — per-shot performance retargeting.

Sits between KeyframeRenderPhase and MotionRenderPhase. Iterates all
shots that have an approved keyframe but no approved performance take,
generates a driving performance via ShotController.generate_performance_take(),
and stores the result on the shot. Shots routed to SKIP are no-ops.

Same shape as KeyframeRenderPhase and MotionRenderPhase.
"""

from __future__ import annotations
import time
from typing import Callable, Optional
from cinema.phases.base import PhaseResult


class PerformanceCapturePhase:
    name = "performance_capture"

    def __init__(self, shot_generator=None, project=None, on_failure=None):
        self._gen = shot_generator
        self._project = project
        self._on_failure = on_failure or (lambda scene_id, shot_id, error: None)

    def run(self, ctx) -> PhaseResult:
        start = time.time()
        if self._gen is None or self._project is None:
            return PhaseResult(ok=False,
                message="PerformanceCapturePhase requires shot_generator and project",
                elapsed_s=0.0)

        ok = skip = fail = 0
        for scene in self._project.get("scenes", []):
            if ctx.lifecycle.is_cancelled():
                return PhaseResult(ok=False,
                    message=f"cancelled (ok={ok}, skip={skip}, fail={fail})",
                    elapsed_s=time.time() - start)
            for shot in scene.get("shots", []):
                if ctx.lifecycle.is_cancelled():
                    return PhaseResult(ok=False,
                        message=f"cancelled (ok={ok}, skip={skip}, fail={fail})",
                        elapsed_s=time.time() - start)
                if shot.get("approved_performance_take_id"):
                    skip += 1
                    continue
                if not shot.get("approved_keyframe_take_id"):
                    skip += 1  # no keyframe → nothing to drive
                    continue
                result = self._gen.generate_performance_take(scene["id"], shot["id"])
                if result.get("success"):
                    ok += 1
                else:
                    fail += 1
                    self._on_failure(scene["id"], shot["id"], result.get("error", ""))

        return PhaseResult(ok=True,
            message=f"performance: {ok} new, {skip} skipped, {fail} failed",
            elapsed_s=time.time() - start)
```

---

## 10. Wire into `cinema_pipeline.CinemaPipeline.generate()`

Insert between the current `KEYFRAME_REVIEW` gate (line 727) and the motion render call (line 743). Pattern is identical to the existing `KeyframeRenderPhase` + `MotionRenderPhase` blocks:

```python
# After KEYFRAME_REVIEW gate passes:
project = self._refresh_project_snapshot() or self.project

def _on_performance_fail(scene_id: str, shot_id: str, error: str):
    self.failed_shots.append(shot_id)
    self.progress("SHOT_FAILED", error or "Performance capture failed", 60,
                  scene_id=scene_id, shot_id=shot_id)

performance_result = PerformanceCapturePhase(
    shot_generator=self,
    project=project,
    on_failure=_on_performance_fail,
).run(ctx)
self.progress("PERFORMANCE_DONE", performance_result.message, 65)
if self.lifecycle.is_cancelled():
    self.progress("CANCELLED", "Pipeline cancelled by user", 0)
    return None

if not self._wait_for_gate("PERFORMANCE_REVIEW",
                           "Approve performance takes (or skip) to continue", 68):
    self.progress("CANCELLED", "Pipeline cancelled during performance review", 0)
    return None

project = self._refresh_project_snapshot() or self.project
# ... existing MotionRenderPhase block continues here ...
```

Adjust the progress percentages downstream (motion 80 → 78, etc.) so the bar still ends at 100.

Add the import at the top:

```python
from cinema.phases.performance import PerformanceCapturePhase
```

---

## 11. Settings (env vars)

Add to `config/settings.py:Settings` dataclass (alpha-ish order matching existing fields):

```python
# Performance capture
viggle_api_key: str
hedra_api_key: str
```

Add to `from_env()`:

```python
viggle_api_key=_env("VIGGLE_API_KEY"),
hedra_api_key=_env("HEDRA_API_KEY"),
```

Add to `.env.example` with one-line comments. Document in `CLAUDE.md` if you maintain an env table there.

Runway key (`RUNWAYML_API_SECRET`) already exists.

---

## 12. Cost tracking

Add the new operations to `cost_tracker.PRICING` as needed (Hedra has token pricing — currently $5/min audio, ~$0.05/shot at 6s). For per-API calls use `log_api()`, not `log_llm()`:

```python
tracker.log_api(
    provider="runway", model="act_one",
    operation="performance_capture",
    cost_usd=0.05 * duration_s,
    shot_id=shot_id, video_id=video_id,
)
```

For free engines (LivePortrait, SadTalker on existing Railway): log a small fixed cost (~$0.02) representing GPU-minute amortization, so the cost breakdown stays honest. Don't log $0 — that breaks the per-second analysis in `get_cost_per_second()`.

---

## 13. Slice plan (follows `REFACTOR_HANDOFF.md §6` five-step playbook)

One commit per slice. Identity-check + smoke at each step.

| # | Slice | Touches | LOC | Risk |
|---|---|---|---|---|
| 1 | Settings + .env.example + PRICING entries | `config/settings.py`, `.env.example`, `cost_tracker.py` | ~20 | none |
| 2 | `domain/performance.py` — pure router | new file | ~120 | none, no imports beyond stdlib |
| 3 | `performance/` package — engine adapters (3 files + router) | new package | ~400 | medium (real APIs) |
| 4 | `performance/driving_video.py` — Mode B synth | new file | ~150 | medium (SadTalker/Hedra) |
| 5 | `domain/project_manager.make_shot()` field additions + migration | `domain/project_manager.py` | ~25 | low — additive only |
| 6 | `ShotController.generate_performance_take()` + delegate | `cinema/shots/controller.py`, `cinema_pipeline.py` | ~120 | medium |
| 7 | `cinema/phases/performance.py` — `PerformanceCapturePhase` | new file | ~80 | low (mirrors existing phase) |
| 8 | Wire phase + gate in `cinema_pipeline.generate()` | `cinema_pipeline.py` | ~40 | medium — adjust progress %s |
| 9 | `generate_ai_video()` accepts `driving_video_path`; wire to Veo/Sora/Runway natives | `phase_c_ffmpeg.py`, `veo_native.py`, `sora_native.py`, `runway` adapter | ~100 | medium |
| 10 | Web UI gate `PERFORMANCE_REVIEW`: preview clip + upload slot + skip button | `web_server.py`, `web/` frontend | ~250 | medium-high, async |
| 11 | Quality tracker — new `performance_score` field, validator pass | `quality_tracker.py`, `identity/validator.py` | ~80 | low |
| 12 | Update §0 smoke block to include new phase class + identity invariants | `docs/REFACTOR_HANDOFF.md` | ~15 | none |
| 13 | Tests: unit for `domain.performance.route_performance_engine`, integration for engine adapters | `tests/unit/`, `tests/integration/` | ~200 | low |

**Ship order recommendation:** slices 1–9 give an end-to-end autopilot path (Mode B only, no UI). Run a real video, validate the lift. *Then* do slice 10 (UI) once you've confirmed the gain. Don't build the gate UI before you've seen the output improve — that's the right kind of conservative.

---

## 14. New invariants for `REFACTOR_HANDOFF.md §0` smoke block

After slice 7 lands:

```python
# 9. Performance capture invariants
from cinema.phases.performance import PerformanceCapturePhase
assert isinstance(PerformanceCapturePhase(), Phase), "PerformanceCapturePhase doesn't conform"
print('OK PerformanceCapturePhase conforms to Phase protocol')

from domain.performance import route_performance_engine
# Spot-check the router: a portrait shot with dialogue → ACT_ONE; landscape → SKIP
mock_shot_dlg = {"shot_type": "portrait", "dialogue": "test", "characters_in_frame": ["c1"]}
mock_shot_land = {"shot_type": "landscape", "dialogue": "", "characters_in_frame": []}
assert route_performance_engine(mock_shot_dlg, {}) == "ACT_ONE"
assert route_performance_engine(mock_shot_land, {}) == "SKIP"
print('OK domain.performance router')

# Identity check — phase wrapper does not duplicate engine code
import performance.act_one, performance._router
assert performance._router.dispatch.__module__ == 'performance._router'
print('OK performance package layout')
```

Add slice 7's identity check in the slice commit message body, same shape as previous slices.

---

## 15. Quality / validation hooks

Once shots are coming through with performance takes, extend the existing identity validator (`identity/validator.py`) to *also* score performance retention: how well the driving motion was preserved vs. the keyframe identity.

Two metrics, both computable from frames already sampled by `validate_shot`:

- **Identity retention** — already computed. Should stay flat or improve (driving video locks face position, helps face stay on-model).
- **Motion fidelity** — new. Compare optical flow between driving video and final motion clip. High correlation = the driving motion was followed. Use OpenCV's Farneback or a small embedding model. Save as `take["metadata"]["motion_fidelity"]`.

Feed both into `LearningPhase` (`cinema/phases/learning.py`) for the `shorts_experiments` table — record `performance_engine`, `motion_fidelity`, `identity_score` per shot so the system *learns* which engine wins for which shot type. After ~20 videos the workflow_selector can be retrained with this data — the existing pattern from `quality_tracker.QualityTracker.get_top_workflows()`.

---

## 16. Testing

### Unit (in `tests/unit/`)

- `test_performance_router.py` — table-driven test of `route_performance_engine` across {shot_type × has_dialogue × has_characters}. ~15 cases.
- `test_performance_shot_fields.py` — `make_shot()` returns all 4 new fields with safe defaults; legacy-shot migration adds them.
- `test_performance_phase_protocol.py` — `PerformanceCapturePhase()` conforms to `Phase`; no-arg returns `ok=False` with sensible message.

### Integration (in `tests/integration/`)

- `test_act_one_smoke.py` — hits real Runway Act-One with a small keyframe + 2s of audio, asserts a non-empty mp4 comes back. Gate behind `RUNWAYML_API_SECRET` env presence.
- `test_live_portrait_smoke.py` — same, against the Railway ComfyUI endpoint.

Follow the existing `tests/integration/` pattern — skip if env vars not present rather than failing.

---

## 17. Pricing implication (for context, not for code)

Closing this gap brings the pipeline into legitimate boutique-studio territory. Freelance rates after this lands (vs. pre-performance):

| Package | Pre-performance | Post-performance |
|---|---|---|
| Single custom short | $1,500 – $2,500 | **$2,500 – $4,000** |
| Branded / commercial | $3,500 – $5,000 | **$5,000 – $8,500** |
| Series of 4 (mo retainer) | $6,000 – $9,000 | **$10,000 – $15,000** |
| Agency white-label | $10k – $15k/mo | **$18k – $25k/mo** |

Anchor: **$3,000 / video** once performance capture is in. The ceiling above that is portfolio, not capability.

---

## 18. What NOT to do in this slice

- **Don't rebuild lip_sync.py.** The existing module stays — it runs *after* assembly as a polish pass. Act-One already does lip sync at the source; the post-pass becomes redundant for Act-One shots and a fallback for non-Act-One shots. That's fine. Leave it.
- **Don't change the `cinema_pipeline.py` mixin structure.** Just add the new method on `ShotController` and the new phase. The mixin refactor (slices 1–4 of `cinema_pipeline.py` migration) is orthogonal.
- **Don't bypass the gate.** The whole point is operator-in-the-loop direction. If you find yourself adding "auto-approve performance takes" logic, stop — you've reverted the value.
- **Don't try to do Kling driving-video in v1.** Kling's input shape doesn't accept it cleanly. Fall through to text-to-video when target is Kling. Address in a follow-up if/when Kling exposes a motion-brush API.
- **Don't write a unified "performance abstraction" upfront.** Three concrete adapters first. Pattern emerges. *Then* extract — same lesson as `audio/` decomposition (§7 Pattern G in REFACTOR_HANDOFF).

---

## 19. Open questions to resolve before slice 1

1. **Hedra vs SadTalker for Mode B default.** Hedra is paid but the lip-sync quality is noticeably better; SadTalker is free but coarser. Recommend Hedra for first ship since the whole pricing premise is "max settings"; SadTalker as fallback.
2. **Where do operator-uploaded driving videos live in the file tree?** Proposal: `projects/{pid}/performance_inputs/{scene_id}/{shot_id}/driving.mp4`. Mirrors `projects/{pid}/characters/{char_id}/`.
3. **Does the operator record one driving video per shot, or one per scene with timing markers?** Per-shot is simpler. Per-scene-with-markers is more efficient for the operator. Ship per-shot in v1.
4. **Should `PERFORMANCE_REVIEW` gate auto-skip if all shots are wide/landscape?** Yes — if all shots in the project route to `SKIP`, fast-forward through the gate. Don't make the operator click through nothing.

Resolve these before starting slice 1. Default if no operator input: Hedra, per-shot, projects/{pid}/performance_inputs/, auto-skip empty gate.

---

## 20. Done criteria

A green run with performance capture is:

1. §0 smoke block passes with the 9th invariant added.
2. End-to-end pipeline runs a real 60s short and produces final mp4.
3. At least 3 dialogue shots in the output show `performance_engine = "ACT_ONE"` in `shot.metadata`.
4. Side-by-side: same project run pre-/post-performance shows visibly better eye lines and beat timing on dialogue shots. (Eyeball test, not metric.)
5. `cost_tracker.get_summary()` shows the new `performance_capture` operation line and the total per-video cost is in the expected band ($60–$80 for max settings).
6. `quality_tracker` rows for the run include `motion_fidelity` scores.

When all six tick, ship it.

---

**End of handoff.** Next session: read §0 smoke, confirm green, start slice 1.
