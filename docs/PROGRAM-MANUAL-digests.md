# Content — AI Cinema Pipeline · Subsystem Research Digests (companion)

*The raw, per-subsystem research behind [PROGRAM-MANUAL.md](PROGRAM-MANUAL.md). 12 subagents each mapped one subsystem directly against the live source and returned a dense `file:line`-cited digest. These are more granular and `file:line`-exhaustive than the synthesized manual — reach for them when you need per-function detail. Generated 2026-05-30 via the read-only deep-research workflow (CLAUDE.md Rule #17). Accurate at HEAD `910f393`; if a line number drifts, grep the symbol — the function/class is the load-bearing reference, not the line. Each digest may carry minor inter-digest disagreements; where this companion and `PROGRAM-MANUAL.md` differ, the manual is the reconciled view and `ARCHITECTURE.md` is canonical truth.*

## Contents
- [1. macro-spine — Macro Orchestration Spine](#1-macro-spine-macro-orchestration-spine)
- [2. user-entry/web — Web Server & API Surface](#2-user-entryweb-web-server-api-surface)
- [3. phase-system — Phase Abstraction](#3-phase-system-phase-abstraction)
- [4. review/gates/screening — Review / Gates / Auto-Approve / Screening / Checkpoints](#4-reviewgatesscreening-review-gates-auto-approve-screening-checkpoints)
- [5. data-model/state — Domain Data Model & Persistence](#5-data-modelstate-domain-data-model-persistence)
- [6. creative-LLM — Creative LLM / Direction Layer](#6-creative-llm-creative-llm-direction-layer)
- [7. script->scenes/dialogue/research — Script → Scenes → Shots (+ Dialogue & Research Augmentation)](#7-script-scenesdialogueresearch-script-scenes-shots-dialogue-research-augmentation)
- [8. video-gen/API-cascade — Video Generation, Shot-Type Routing, and API Fallback Cascade](#8-video-genapi-cascade-video-generation-shot-type-routing-and-api-fallback-cascade)
- [9. keyframe/image-gen/max-tier — Image/Keyframe Generation and Quality Tiers](#9-keyframeimage-genmax-tier-imagekeyframe-generation-and-quality-tiers)
- [10. identity/continuity/coherence — Character Consistency — Identity Validation, Continuity, Coherence, Characters & Locations](#10-identitycontinuitycoherence-character-consistency-identity-validation-continuity-coherence-characters-locations)
- [11. post-proc/assembly/audio — Post-Processing & Final Assembly (Phase C + Audio)](#11-post-procassemblyaudio-post-processing-final-assembly-phase-c-audio)
- [12. cost/report/docs/config — Cross-cutting services + CONFIG/OPERATION surface](#12-costreportdocsconfig-cross-cutting-services-configoperation-surface)


---

## 1. macro-spine — Macro Orchestration Spine

*Subsystem key: `orchestration`*

### Purpose (2-4 sentences)

`cinema_pipeline.CinemaPipeline` is the sole run driver for the AI cinema pipeline. It owns the ordered gate sequence — STYLE → SCENE_DECOMPOSE → PLAN_REVIEW → KEYFRAME_RENDER → KEYFRAME_REVIEW → PERFORMANCE_CAPTURE → PERFORMANCE_REVIEW → MOTION_RENDER → REVIEW → ASSEMBLY → SCREENING → COMPLETE — and is constructed by `web_server.py` for every project run request. Long-lived project dependencies (services, models, directories) live on `PipelineCore`; per-run mutable state lives on `RunState`; pause/cancel/gate-wait/progress mechanics live on `ThreadedLifecycle`. The three controllers (`ShotController`, `ReviewController`, `CheckpointStore`) are composed into the orchestrator and share the single `RunState` reference.

### Modules

| Path | Role | LOC |
|---|---|---|
| `cinema_pipeline.py` | Orchestrator — owns `generate()` main loop, assembly (`_assemble_final`), scene-level helpers (`_ensure_scene_audio`, `_ensure_scene_foley`, `_ensure_bgm`), checkpointing delegation, and all backward-compat property forwarders | 1529 |
| `cinema/runstate.py` | `RunState` dataclass — canonical single home for per-run mutable state shared between orchestrator and all three controllers | 154 |
| `cinema/lifecycle.py` | `LifecycleService` Protocol + `NullLifecycle` (no-op) + `ThreadedLifecycle` (event-backed interactive implementation) | 208 |
| `cinema/core.py` | `PipelineCore` dataclass + `build_pipeline_core()` factory — long-lived services (project dict, dirs, `ContinuityEngine`, `ChiefDirector`, `CostTracker`, `LLMEnsemble`) | 115 |
| `cinema/context.py` | `PipelineContext` dataclass — typed shared state passed INTO phase `.run()` calls; also exposes `get_project_setting()` canonical helper | 176 |
| `cinema/pipeline.py` | `CinemaPipeline` (SEPARATE thin class) — generic list-of-Phase iterator, not the main orchestrator; used by callers wanting a typed phase-executor without the full orchestrator | 114 |
| `pipeline_context.py` | `PIPELINE_CONTEXT` string constant — loads `config/prompts/pipeline_context.md` and is injected into LLM system prompts (SceneDecomposer, ChiefDirector, DialogueWriter, StyleDirector) | 15 |
| `cinema/phases/base.py` | `Phase` Protocol + `PhaseResult` dataclass — minimal contract every phase implements | 81 |
| `cinema/phases/keyframe_render.py` | `KeyframeRenderPhase` — iterates all shots, calls `shot_generator.generate_keyframe_take()` for each unapproved shot | 109 |
| `cinema/phases/performance.py` | `PerformanceCapturePhase` — iterates shots with approved keyframe but no performance take, calls `generate_performance_take()`; skips SKIP-routed shots | 89 |
| `cinema/phases/motion_render.py` | `MotionRenderPhase` — iterates shots, calls `generate_motion_take()`; has a storyboard batch path (Kling Native, 2-6 shots, all keyframes present) | 412 |

### Key functions & classes (THE MICRO LEVEL)

**`CinemaPipeline.__init__`** — `cinema_pipeline.py:44`
Constructs `PipelineCore` (or accepts one), builds `ThreadedLifecycle(progress_callback)`, creates `RunState(headless=headless)`, and composes `ShotController`, `ReviewController`, `CheckpointStore` — all sharing the SAME `RunState` reference. `headless=True` makes `ReviewController._wait_for_gate` raise `GateNotSatisfiedError` instead of blocking.

**`CinemaPipeline.generate`** — `cinema_pipeline.py:844`
The main production method. `resume=True` triggers `_restore_from_checkpoint()`. Returns path to `final_cinema.mp4` or `None`. Ordered phases in code:
1. `_refresh_project_snapshot()` — reload project dict from disk
2. `generate_style_rules()` + persist via `mutate_project`
3. `_ensure_bgm(settings)` — generate BGM upfront
4. Scene loop: `competitive_decompose_scene()` / `decompose_scene()` → `director.validate_shot_prompts()` → `record_director_review_on_shots()` → `update_scene_shots()` → `_ensure_scene_audio()` → `_save_checkpoint()`
5. `_wait_for_gate("PLAN_REVIEW", ...)` — blocks until all shot plans approved
6. `KeyframeRenderPhase(...).run(ctx)` — generates keyframes
7. `_wait_for_gate("KEYFRAME_REVIEW", ...)` — blocks until keyframes approved
8. `PerformanceCapturePhase(...).run(ctx)` — performance retargeting
9. Conditional `_wait_for_gate("PERFORMANCE_REVIEW", ...)` — skipped if all shots routed to SKIP
10. `MotionRenderPhase(...).run(ctx)` — generates motion clips
11. `_wait_for_gate("REVIEW", ...)` — blocks until all final takes approved
12. `assemble_approved_takes()` → final output

**`CinemaPipeline.assemble_approved_takes`** — `cinema_pipeline.py:755`
Full assembly path: calls `_assemble_approved_takes_core()`, then conditionally waits on SCREENING gate (env `CINEMA_SCREENING_STAGE`, default ON), then runs cleanup, logs cost summary, clears checkpoint, emits COMPLETE at 100%.

**`CinemaPipeline._assemble_approved_takes_core`** — `cinema_pipeline.py:685`
Steps 1-5 of assembly: refresh snapshot → REVIEW gate check → `_build_scene_packages()` → per-scene preview generation → `_assemble_final()`. Used directly by the S21 re-assemble endpoint to avoid deadlock (the SCREENING gate-wait would deadlock a Flask request thread during screening iteration).

**`CinemaPipeline._assemble_final`** — `cinema_pipeline.py:1184`
1. Collects clips in scene order from `scene_data`. 2. Normalizes each to 1920×1080@30fps via ffmpeg (`scale + pad + fps`, `libx264 crf=20`, `aac 192k`). 3. Stitches: hard-cut concat (default) OR `xfade_concat` cross-dissolve per scene boundary (`scene_transitions=True`). 4. Color grading via `apply_color_grade()` (mood-to-preset map). 5. Audio tri-mix: voice (1.0) + BGM (0.12) + foley (0.20), with standalone-dialogue path when motion engine doesn't embed audio. Falls back: 3-input → 2-input → BGM-only → copy-as-is. 6. `_apply_final_loudnorm()` two-pass EBU R128. Returns `exports/final_cinema.mp4`.

**`CinemaPipeline._refresh_project_snapshot`** — `cinema_pipeline.py:425`
`load_project(project_id)` → validates via `Project.model_validate(latest)` BEFORE swapping `self.project` (the validate-before-swap ordering is a critical correctness fix: if validation fails, `self.project` stays coherent). Then rebuilds `continuity.character_tracker.characters` and `continuity.location_persistence.locations` typed-id-keyed dicts. Called 6+ times through `generate()` at gate boundaries.

**`CinemaPipeline._build_scene_packages`** — `cinema_pipeline.py:608`
Iterates scenes → resolves `approved_final_take_id` paths → collects `scene_audio`, `scene_foley` per scene → returns `(scene_packages, missing_shots)`. Handles "all-shots-embedded" detection: when every approved shot has `metadata.audio_embedded=True`, suppresses standalone TTS to avoid double-voice from Veo/Omnihuman.

**`CinemaPipeline._ensure_scene_audio`** — `cinema_pipeline.py:481`
Generates per-scene dialogue MP3 via `generate_dialogue_voiceover()`. Uses `PipelineContext(global_settings=...)` to thread project settings. Caches in `self.scene_audio[scene_id]`. Returns path or `None`.

**`CinemaPipeline._ensure_scene_foley`** — `cinema_pipeline.py:548`
Aggregates `shot.scene_foley` descriptors across a scene, calls `generate_stability_foley()`, caches in `self.scene_foley[scene_id]` and appends to `self.foley_audio_paths`. Non-critical: exceptions emit `logger.warning` and return `""`.

**`CinemaPipeline._ensure_bgm`** — `cinema_pipeline.py:526`
Generates BGM via `generate_fal_bgm(music_mood, ..., duration=47)`, then optionally masters via `master_music(..., preset=music_mastering)`. Non-critical: mastering failure logs WARNING.

**`build_pipeline_core`** — `cinema/core.py:75`
Factory: `load_project(project_id)` → mkdir `temp/` + `exports/` → constructs `PipelineCore(project, dirs, ContinuityEngine(project), ChiefDirector(project), CostTracker(budget_usd), LLMEnsemble(settings))`. Raises `ValueError` if project not found.

**`ThreadedLifecycle`** — `cinema/lifecycle.py:110`
`_cancelled: bool` + `_paused: bool` + `_resume_event: threading.Event` (starts SET=unpaused) + `_gate_events: Dict[str, threading.Event]` (lazily created). `cancel()` sets flag and signals all gate events. `wait_for_gate(name, predicate, poll_interval=0.5)` loops until cancelled or predicate is True, with explicit `signal_gate(name)` as early-wake. `check_pause()` blocks on `_resume_event.wait()`.

**`ReviewController._wait_for_gate`** — `cinema/review/controller.py:507`
Runs `_run_auto_approve_pass(gate)` first (pre-screen via `auto_approve.check_gate()`), then calls `_lifecycle.wait_for_gate(gate, predicate)` where predicate = `_gate_satisfied(gate)`. In headless mode (`RunState.headless=True`), raises `GateNotSatisfiedError` with a diagnostic message from `_gate_block_details()` if auto-approve cannot clear.

**`ReviewController._gate_satisfied`** — `cinema/review/controller.py:224`
PLAN_REVIEW: all shots have `shot_plan_approved=True`. KEYFRAME_REVIEW: all shots have `approved_keyframe_take_id`. PERFORMANCE_REVIEW: each shot either has `approved_performance_take_id` OR `performance_engine=="SKIP"` OR lacks keyframe. REVIEW: all shots have `approved_final_take_id`.

**`ReviewController.GateNotSatisfiedError`** — `cinema/review/controller.py:93`
`RuntimeError` subclass raised by `_wait_for_gate` in headless mode when auto-approve cannot clear a gate. Includes `_gate_block_details()` diagnostic (veto rule names for PLAN_REVIEW, unapproved shot IDs for others).

**`CheckpointStore._save_checkpoint`** — `cinema/checkpoint.py:87`
Atomically writes `temp/checkpoint.json` via `tempfile.mkstemp` + `os.replace`. Serializes: `current_stage/scene_id/shot_id`, `completed_scene_indices`, `scene_clips`, `scene_audio`, `scene_foley`, `foley_audio_paths`, `shot_results`, `failed_shots`. Called after each scene loop iteration and after each audio generation step.

**`CheckpointStore._restore_from_checkpoint`** — `cinema/checkpoint.py:163`
Reads `checkpoint.json`, rehydrates `RunState` fields wholesale, validates referenced files still exist (marks as `"lost"` if gone). Returns `set` of completed scene indices.

**`RunState`** — `cinema/runstate.py:60`
`@dataclass` with all per-run fields: `shot_results: dict`, `review_clips: dict`, `scene_clips: dict`, `scene_audio: dict`, `scene_foley: dict`, `foley_audio_paths: list`, `failed_shots: list`, `current_stage/scene_id/shot_id: str`, `headless: bool`, `completed_scene_indices: set`. Single instance created per `CinemaPipeline.__init__`, shared by all controllers.

**`PipelineContext`** — `cinema/context.py:49`
`@dataclass` bridging phases: `topic`, `language`, `master_image_seed`, `global_settings: dict` (all UI knobs), `lifecycle: LifecycleService` (default: `NullLifecycle`), `script_data`, `production_blueprint`, audio fields, output paths, `prev_shot_latent` (max-tier LatentBlend), `char_lora_paths`, `style_reference_paths`. Dict-compat layer (`__getitem__`, `__setitem__`, `.get()`, `.update()`) keeps legacy `def f(ctx: dict)` phases working.

**`get_project_setting(ctx, key, default)`** — `cinema/context.py:151`
Canonical read path for per-project UI knobs. Reads `ctx.global_settings[key]`. CRITICAL: must be used instead of `config.settings.Settings` for any user-tunable setting (TTS provider, foley provider, lipsync mode, language, etc.).

**`AutoApproveConfig`** — `cinema/auto_approve.py:71`
Reads from `project.global_settings.auto_approve`. Fields: `enabled`, `plan_require_approved`, `plan_reject_on_violations`, `image_min_composite` (0.97), `image_min_composite_fallback` (0.78), `image_veto_on_fallback`, `image_max_spent_multiplier` (1.5), `motion_min_identity` (0.85), `motion_min_motion_score` (0.7), `motion_veto_on_fallback`, `final_min_lipsync` (0.8), `final_require_human_if_upstream_auto` (safety net).

**`record_director_review_on_shots`** — `cinema/auto_approve.py:235`
Writes ChiefDirector verdict onto each shot dict — this populates the field that `_rules_for_plan` reads. Without this call, PLAN_REVIEW auto-approve always vetoes (director_review absent) and a headless run hangs forever at the gate.

**`cinema/pipeline.CinemaPipeline`** — `cinema/pipeline.py:80`
NOT the same as `cinema_pipeline.CinemaPipeline`. A generic thin `run()` loop over a `list[Phase]`. Iterates in order, short-circuits on `ok=False`. Used by callers that want to compose a phase list manually. This class is NOT used by the main orchestrator.

**`KeyframeRenderPhase.run`** — `cinema/phases/keyframe_render.py:68`
Iterates `project["scenes"][*]["shots"]`. Skips shots with `approved_keyframe_take_id`. Calls `self._gen.generate_keyframe_take(scene_id, shot_id)`. Failure on any single shot routes through `on_failure` callback but does NOT fail the phase (`ok=True` returned always). Polls `ctx.lifecycle.is_cancelled()` at scene and shot boundaries.

**`MotionRenderPhase.run`** — `cinema/phases/motion_render.py` (line ~100+)
Same shape as Keyframe. Optionally takes a storyboard batch path: if `global_settings.api_engines.KLING_NATIVE.storyboard_mode=True` AND scene has 2-6 unapproved shots AND all have keyframes → calls `KlingNativeAPI.generate_storyboard()` once + `split_video_into_segments()` + per-segment `_finalize_motion_take(record_cost=False)`. Falls through to normal per-shot loop on any storyboard failure.

### Data IN -> OUT

**IN:**
- `project_id: str` → loaded project dict (scenes, characters, locations, settings, shots)
- `project.global_settings` → all user-tunable knobs (aspect_ratio, music_mood, language, competitive_generation, style_rules, auto_approve thresholds, api_engines, scene_transitions, transition_duration, music_mastering, budget_limit_usd)
- `progress_callback` → SSE queue callback from web_server
- `headless: bool` → run-mode flag
- `resume: bool` → checkpoint-resume flag
- ChiefDirector LLM review decisions (APPROVED / MODIFIED / REJECTED)
- Operator gate approvals via web API (shot plan, keyframe, performance, final take)
- Generated media files: keyframe PNGs, motion MP4s, performance takes, per-scene MP3s, foley MP3s, BGM MP3

**OUT:**
- `exports/final_cinema.mp4` — the assembled final film
- `temp/checkpoint.json` — incremental resume state
- `temp/stitched.mp4`, `temp/graded.mp4`, `temp/*.norm.mp4` — intermediate assembly artifacts
- `temp/audio_<scene_id>.mp3`, `temp/bgm_*.mp3`, `temp/foley_<scene_id>.mp3` — per-scene audio
- Progress events emitted via `lifecycle.report_progress()` → SSE stream to UI
- Persisted project mutations: shot fields (`approved_keyframe_take_id`, `approved_final_take_id`, `director_review`, `shot_plan_approved`, `auto_approve_audit`), style_rules, screening_approved

### Connects to (which OTHER subsystems it touches, and HOW)

| Subsystem | How |
|---|---|
| `web_server.py` | Direct construction: `CinemaPipeline(pid, core=..., progress_callback=...)`. `web_server` calls `pipeline.generate()`, `assemble_approved_takes()`, `_assemble_approved_takes_core()`, `cancel()`, `pause()`, `resume()`, and exposes `lifecycle.signal_gate(SCREENING_STAGE_NAME)` | 
| `domain/project_manager.py` (via shim `project_manager.py`) | `load_project()` + `mutate_project()` — all project persistence reads and writes | 
| `domain/scene_decomposer.py` (via shim) | `decompose_scene()`, `competitive_decompose_scene()`, `update_scene_shots()` — scene-to-shots decomposition |
| `domain/continuity_engine.py` | Via `PipelineCore.continuity` (`ContinuityEngine`); rebuilt on every `_refresh_project_snapshot()` |
| `llm/chief_director.py` | Via `PipelineCore.director` (`ChiefDirector`); `director.validate_shot_prompts(shots, scene)` called per scene |
| `llm/style_director.py` | `generate_style_rules(project_name, mood, ...)` called once at run start |
| `domain/dialogue_writer.py` (via shim) | `generate_dialogue()` called from `_ensure_scene_audio` |
| `audio/dialogue.py` | `generate_dialogue_voiceover()` called from `_ensure_scene_audio` |
| `audio/music.py` | `generate_fal_bgm()` + `master_music()` in `_ensure_bgm` |
| `audio/foley.py` | `_build_foley_prompt()` + `generate_stability_foley()` in `_ensure_scene_foley` |
| `cinema/shots/controller.py` (`ShotController`) | Composed — all shot-gen calls (`generate_keyframe_take`, `generate_motion_take`, `generate_performance_take`, `regenerate_shot`, etc.) delegate here |
| `cinema/review/controller.py` (`ReviewController`) | Composed — all gate/review calls (`_wait_for_gate`, `_gate_satisfied`, `_rebuild_review_clips`, `approve_shot_plan`, `approve_take`) delegate here |
| `cinema/checkpoint.py` (`CheckpointStore`) | Composed — `_save_checkpoint`, `_restore_from_checkpoint`, `has_checkpoint`, `resume_info` |
| `cinema/auto_approve.py` | Used by `ReviewController._run_auto_approve_pass`; `record_director_review_on_shots()` called directly in `generate()` |
| `cinema/screening.py` | `_screening_stage_enabled()`, `is_screening_approved()` called in `assemble_approved_takes`; `mark_screening_approved()` called from web endpoint |
| `phase_c_ffmpeg.py` | `xfade_concat()`, `apply_color_grade()`, `two_pass_loudnorm()` called in `_assemble_final` / `_apply_final_loudnorm` |
| `pipeline_context.py` (top-level) | `PIPELINE_CONTEXT` string injected into LLM prompts of ChiefDirector, SceneDecomposer, DialogueWriter, StyleDirector |
| `cost_tracker.py` | Via `PipelineCore.cost_tracker`; `get_video_cost()` called at run end |
| `cleanup.py` | `cleanup_project(pid, aggressive=False)` called post-SCREENING in `assemble_approved_takes` |

### User-facing surface & capability knobs

All knobs live in `project.global_settings` (read via `get_project_setting(ctx, key, default)`) or environment variables.

**`project.global_settings` (per-project UI knobs):**

| Key | Type | Effect | Default |
|---|---|---|---|
| `style_rules` | dict | Pre-baked style rules (skips LLM call if present) | `{}` (auto-generated) |
| `music_mood` | str | BGM mood + style rule mood input | `"suspense"` / `"cinematic"` |
| `color_palette` | str | Color palette for style rule generation | `""` |
| `aspect_ratio` | str | Passed to style director | `"16:9"` |
| `language` | str | Dialogue voiceover language | `"English"` |
| `competitive_generation` | bool | Run competitive decompose (higher quality) | `True` |
| `scene_transitions` | bool | Cross-dissolve between scenes (ffmpeg xfade) | `False` |
| `transition_duration` | float | xfade duration seconds | `0.5` |
| `music_mastering` | str | `master_music` preset (e.g. `"cinema_master"`) | `"cinema_master"` |
| `budget_limit_usd` | float | `CostTracker` budget cap | `None` |
| `mood` | str | Color grade preset selector | `"cinematic"` |
| `auto_approve.enabled` | bool | Enable auto-approve gate logic | `True` |
| `auto_approve.image_min_composite` | float | PuLID composite threshold for keyframe auto-approve | `0.97` |
| `auto_approve.image_min_composite_fallback` | float | Non-PuLID fallback composite threshold | `0.78` |
| `auto_approve.motion_min_identity` | float | Motion gate identity_score floor | `0.85` |
| `auto_approve.motion_min_motion_score` | float | Motion gate motion_score floor | `0.7` |
| `auto_approve.final_min_lipsync` | float | Final gate lipsync_score floor | `0.8` |
| `auto_approve.final_require_human_if_upstream_auto` | bool | Force human review at REVIEW gate if any earlier gate was auto-approved | `True` |
| `api_engines.KLING_NATIVE.storyboard_mode` | bool | Enable Kling storyboard batch for 2-6 shot scenes | `False` |

**Environment variables:**

| Var | Effect | Default |
|---|---|---|
| `CINEMA_SCREENING_STAGE` | `0` to skip SCREENING gate; any other value = ON | ON |
| `CINEMA_AUTO_APPROVE_MOTION` | truthy (`1`/`true`/`yes`) to enable PERFORMANCE_REVIEW auto-approve | OFF |
| `CINEMA_STRICT_SCHEMA` | Enables strict Pydantic validation at project load boundaries (used across web_server mutators; not pipeline-local) | OFF |

**To maximize quality/capability:**
- Set `competitive_generation=True` (default; uses `competitive_decompose_scene`)
- Lower `auto_approve.*` thresholds to `0` to force human review at every gate
- Set `auto_approve.enabled=False` to require full operator review at all gates
- Set `api_engines.KLING_NATIVE.storyboard_mode=True` for coherent multi-shot scenes
- Set `scene_transitions=True` for cinematic cross-dissolves
- Set `budget_limit_usd` to cap spend; `CostTracker` vetoes generation when exceeded
- Edit `config/prompts/pipeline_context.md` to update ALL LLM system prompts globally (injected via `PIPELINE_CONTEXT`)

### Control & data flow (how a run moves through this subsystem, step by step)

```
web_server.py
  └─ CinemaPipeline(pid, core=PipelineCore, progress_callback=SSE_queue_cb)
       └─ RunState(headless=False)
       └─ ShotController(core, lifecycle, host=self, runstate)
       └─ ReviewController(core, lifecycle, host=self, runstate)
       └─ CheckpointStore(core, lifecycle, runstate)

pipeline.generate(resume=False)
│
├─ _refresh_project_snapshot()                     # load_project → model_validate → swap in-place
├─ [resume=True: _restore_from_checkpoint()]
│
├─ generate_style_rules() → mutate_project()       # STYLE phase, 2%
├─ _ensure_bgm(settings)                           # pre-generate BGM upfront
│
├─ for scene in scenes:                            # SCENE DECOMPOSE loop
│   ├─ [if no shots] competitive_decompose_scene() or decompose_scene()
│   ├─ director.validate_shot_prompts(shots, scene) → APPROVED/MODIFIED/REJECTED
│   ├─ record_director_review_on_shots(shots, review)  # critical: writes director_review
│   ├─ update_scene_shots(project, scene_id, shots)
│   ├─ _save_checkpoint()
│   └─ _ensure_scene_audio(scene, chars)           # per-scene TTS/dialogue
│
├─ _wait_for_gate("PLAN_REVIEW", ...)              # BLOCKS (25%)
│   └─ ReviewController._run_auto_approve_pass("PLAN_REVIEW")
│      └─ auto_approve.check_gate() per shot
│   └─ lifecycle.wait_for_gate("PLAN_REVIEW", predicate=_gate_satisfied)
│      [headless: raises GateNotSatisfiedError if not cleared]
│
├─ PipelineContext(lifecycle, global_settings, language)
│
├─ KeyframeRenderPhase(shot_generator=self, project).run(ctx)  # KEYFRAME, 50%
│   └─ for each shot: generate_keyframe_take(scene_id, shot_id)
│      └─ ShotController → image gen API → PuLID/ComfyUI → identity validation
│         → _save_checkpoint()
│
├─ _wait_for_gate("KEYFRAME_REVIEW", ...)          # BLOCKS (55%)
│
├─ PerformanceCapturePhase(shot_generator=self, project).run(ctx)  # PERFORMANCE, 62%
│   └─ for each shot: generate_performance_take()
│      └─ ShotController → ACT_ONE / LIVE_PORTRAIT / VIGGLE / SKIP
│
├─ [if not all SKIP] _wait_for_gate("PERFORMANCE_REVIEW", ...)  # BLOCKS (65%)
│
├─ MotionRenderPhase(shot_generator=self, project).run(ctx)  # MOTION, 80%
│   ├─ [storyboard_mode] generate_storyboard() → split_video_into_segments()
│   │      → _finalize_motion_take(record_cost=False) per segment
│   └─ per-shot: generate_motion_take()
│      └─ ShotController → Kling/Veo/Runway/LTX → face-swap/RIFE/upscale
│         → _save_checkpoint()
│
├─ _rebuild_review_clips(project)
├─ _save_checkpoint()
├─ _wait_for_gate("REVIEW", ...)                   # BLOCKS (82%)
│
└─ assemble_approved_takes()
    ├─ _assemble_approved_takes_core()
    │   ├─ _refresh_project_snapshot()
    │   ├─ _gate_satisfied("REVIEW")               # guard
    │   ├─ _ensure_bgm(settings)
    │   ├─ _build_scene_packages(project)
    │   │   ├─ _resolve_take_path() per shot → collect clips
    │   │   ├─ _ensure_scene_audio() per scene     # TTS (unless all embedded)
    │   │   └─ _ensure_scene_foley() per scene
    │   ├─ generate_scene_preview() per scene
    │   └─ _assemble_final(scene_data, bgm_path, settings)
    │       ├─ normalize clips: ffmpeg scale/pad/fps → _norm.mp4
    │       ├─ stitch: ffmpeg concat demuxer → stitched.mp4
    │       │   [scene_transitions=True: xfade_concat() between scenes]
    │       ├─ color grade: apply_color_grade(mood_preset) → graded.mp4
    │       ├─ tri-mix audio: voice(1.0) + BGM(0.12) + foley(0.20)
    │       │   [voice source: [0:a] if embedded, else standalone dialogue mp3]
    │       │   [amix duration=longest if standalone, first if embedded]
    │       └─ two_pass_loudnorm() EBU R128 → final_cinema.mp4
    │
    ├─ [CINEMA_SCREENING_STAGE=ON] wait_for_gate("SCREENING", ...)  # BLOCKS (95%)
    │   └─ polls is_screening_approved(project) with _refresh_project_snapshot()
    │
    ├─ cleanup_project(pid, aggressive=False)
    ├─ cost_tracker.get_video_cost() → log
    ├─ _clear_checkpoint()
    └─ progress("COMPLETE", final_path, 100%)
```

### Gotchas, divergences & doc-drift

1. **`cinema/pipeline.CinemaPipeline` vs `cinema_pipeline.CinemaPipeline` — two different classes with the same name.** `cinema/pipeline.py:80` is a generic thin phase-list driver; `cinema_pipeline.py:38` is the real orchestrator. The skill doc and any doc referring to "CinemaPipeline" without a path is ambiguous. The real orchestrator is always `cinema_pipeline.CinemaPipeline`.

2. **Top-level shims vs domain/ canonical modules.** `scene_decomposer.py`, `dialogue_writer.py`, `project_manager.py` at repo root are pure re-export shims (`from domain.X import *`). They exist to preserve legacy import surfaces post-Phase-8 move. New code should import from `domain.*` directly. The shim pattern is not documented prominently; callers that grep for `import scene_decomposer` will find two modules.

3. **`pipeline_context.py` (top-level) vs `cinema/context.py` — different things with confusingly similar names.** `pipeline_context.py` is a 15-line LLM prompt string loader. `cinema/context.py` is the typed `PipelineContext` dataclass passed to phases. The orchestrator uses BOTH.

4. **`headless=True` does NOT use `NullLifecycle`.** The docstring comment in `cinema/lifecycle.py:70` is clear: `NullLifecycle` was the former CLI's lifecycle (for the now-deleted `main.py`). `headless=True` still uses `ThreadedLifecycle` — it just makes `ReviewController._wait_for_gate` raise `GateNotSatisfiedError` instead of polling forever. Any doc or skill claiming headless uses `NullLifecycle` is wrong.

5. **`NullLifecycle.wait_for_gate` returns `True` even when predicate is false.** `cinema/lifecycle.py:98`: "return True to let the phase proceed." This means tests/callers using `NullLifecycle` will silently skip gate enforcement. The only correct non-interactive path is `CinemaPipeline(headless=True)` with `ThreadedLifecycle`.

6. **PLAN_REVIEW gate hangs headless runs unless `record_director_review_on_shots` is called.** `cinema_pipeline.py:959`: the comment explicitly states this. `_rules_for_plan` reads `shot["director_review"]`; if it's absent (shots loaded from project without running through decompose), the veto fires and headless runs raise `GateNotSatisfiedError`. Cycle-17 fix: `record_director_review_on_shots` is now called unconditionally after `validate_shot_prompts`.

7. **MODIFIED verdict auto-clears the plan gate** (`138d7c7`, user decision, 2026-05-30). This was a deliberate change — previously MODIFIED caused the headless dead-end. Any stale doc describing MODIFIED as a blocking condition is wrong.

8. **`_refresh_project_snapshot` must validate BEFORE swapping `self.project`** (cycle-11 I-1 fix). The validate-before-swap ordering is critical for tracker coherence: if validation raises, `self.project` stays intact. Prior ordering (clear → update → validate) created a partial-state window.

9. **`_assemble_approved_takes_core` vs `assemble_approved_takes` split (S21).** The re-assemble endpoint (`/api/projects/<pid>/assemble/re-assemble`) calls `_assemble_approved_takes_core()` directly, bypassing SCREENING gate-wait + cleanup + cost summary. Calling `assemble_approved_takes()` from a Flask request thread during screening DEADLOCKS because the gate predicate polls `is_screening_approved()` which is False by design, and the Flask request's fresh `CinemaPipeline` is not the one that `signal_gate` will unblock.

10. **Audio tri-mix voice source depends on motion engine.** Veo and Omnihuman embed dialogue audio into the MP4; Kling Native image2video does not. `_build_scene_packages` detects `metadata.audio_embedded=True` on approved takes. If all shots in a scene are embedded → suppress standalone TTS. If mixed → keep TTS for non-embedded shots. The C-B2 fix (`_assemble_final`) ensures the filtergraph voice label binds to the right input index dynamically.

11. **`music_mastering` setting is read from `project.global_settings`**, not from `config.Settings`. Must use `get_project_setting(ctx, "music_mastering", "cinema_master")` — not `settings.music_mastering` — consistent with all other per-project UI knobs (the multi-month `tts_provider` pattern bug was caused by reading the wrong source).

12. **`storyboard_mode` flag is at `global_settings.api_engines.KLING_NATIVE.storyboard_mode`**, a nested path two levels deep. `_get_storyboard_mode()` in `cinema/phases/motion_render.py:45` handles the nesting. Accessing `global_settings.storyboard_mode` directly would silently return `None`.

13. **Auto-generated delegate methods** (`cinema_pipeline.py:146-324`) are generated by `tools/gen_delegates.py`. The comment says "DO NOT EDIT BY HAND." If new `RunState` fields are added or `ShotController`/`ReviewController` methods are added, the delegate block must be regenerated.

14. **`CINEMA_STRICT_SCHEMA` is a web_server mutator flag, not a pipeline flag.** References in `cinema_pipeline.py:434` are comments/annotations about what pattern to follow, not actual runtime checks in the orchestrator. The flag controls mutator-scope validation inside web_server route handlers.

### Citations

- `cinema_pipeline.py:1-8` — module docstring, orchestrated phase sequence
- `cinema_pipeline.py:38-105` — `CinemaPipeline.__init__` full constructor
- `cinema_pipeline.py:44-92` — `headless` parameter, `RunState`, controller composition
- `cinema_pipeline.py:74` — `build_pipeline_core(project_id)` call
- `cinema_pipeline.py:82-84` — `ThreadedLifecycle` construction
- `cinema_pipeline.py:91` — `RunState(headless=headless)` construction
- `cinema_pipeline.py:96-104` — three controller constructions sharing `_runstate`
- `cinema_pipeline.py:146-324` — generated delegate block for RunState, ShotController, ReviewController, CheckpointStore
- `cinema_pipeline.py:367-408` — lifecycle property proxies (`cancelled`, `paused`, `pause`, `resume`, `_check_pause`, `progress`)
- `cinema_pipeline.py:410-423` — `get_state()` UI state snapshot
- `cinema_pipeline.py:425-463` — `_refresh_project_snapshot()` + validate-before-swap fix
- `cinema_pipeline.py:481-524` — `_ensure_scene_audio()`
- `cinema_pipeline.py:526-546` — `_ensure_bgm()`
- `cinema_pipeline.py:548-590` — `_ensure_scene_foley()`
- `cinema_pipeline.py:592-606` — `_approved_take_metadata()`
- `cinema_pipeline.py:608-673` — `_build_scene_packages()` + all-embedded detection
- `cinema_pipeline.py:685-753` — `_assemble_approved_takes_core()` + deadlock rationale
- `cinema_pipeline.py:755-838` — `assemble_approved_takes()` + SCREENING gate + cleanup + cost summary
- `cinema_pipeline.py:774-800` — SCREENING gate machinery, `_screening_stage_enabled`, `is_screening_approved`
- `cinema_pipeline.py:844-1096` — `generate()` main loop, full ordered phase sequence
- `cinema_pipeline.py:855-893` — style rules generation + `mutate_project` persist
- `cinema_pipeline.py:897-962` — scene decompose loop, `competitive_decompose_scene`, `validate_shot_prompts`, `record_director_review_on_shots`
- `cinema_pipeline.py:959` — PLAN_REVIEW auto-approve gate contract comment
- `cinema_pipeline.py:964` — `_wait_for_gate("PLAN_REVIEW", ...)` call site
- `cinema_pipeline.py:978-998` — `PipelineContext` construction, `KeyframeRenderPhase.run(ctx)`
- `cinema_pipeline.py:1004` — `_wait_for_gate("KEYFRAME_REVIEW", ...)` call site
- `cinema_pipeline.py:1024-1031` — `PerformanceCapturePhase.run(ctx)`
- `cinema_pipeline.py:1037-1058` — PERFORMANCE_REVIEW gate, all-SKIP bypass
- `cinema_pipeline.py:1071-1076` — `MotionRenderPhase.run(ctx)`
- `cinema_pipeline.py:1084` — `_wait_for_gate("REVIEW", ...)` call site
- `cinema_pipeline.py:1102-1116` — `_apply_final_loudnorm()` two-pass EBU R128
- `cinema_pipeline.py:1118-1146` — `_concat_foley_track()`
- `cinema_pipeline.py:1148-1182` — `_concat_dialogue_track()`
- `cinema_pipeline.py:1184-1500` — `_assemble_final()` full assembly: normalize, stitch, color grade, tri-mix audio, fallback cascade
- `cinema_pipeline.py:1338-1426` — audio tri-mix filtergraph, embedded vs standalone voice source, amix duration logic
- `cinema_pipeline.py:1505-1528` — `run_cinema_pipeline()` CLI entry point
- `cinema/runstate.py:59-154` — `RunState` dataclass, all fields, `update_progress_pointer()`
- `cinema/lifecycle.py:33-67` — `LifecycleService` Protocol
- `cinema/lifecycle.py:70-107` — `NullLifecycle` (no-op; NOT used by headless `CinemaPipeline`)
- `cinema/lifecycle.py:110-208` — `ThreadedLifecycle` full implementation
- `cinema/lifecycle.py:165-169` — `signal_gate(name)` for explicit gate wake
- `cinema/lifecycle.py:183-198` — `wait_for_gate()` predicate+poll+signal loop
- `cinema/core.py:62-73` — `PipelineCore` dataclass fields
- `cinema/core.py:75-115` — `build_pipeline_core()` factory
- `cinema/context.py:49-143` — `PipelineContext` dataclass + dict-compat layer
- `cinema/context.py:146-176` — `get_project_setting()` canonical knob reader
- `cinema/pipeline.py:80-114` — `cinema.pipeline.CinemaPipeline` (thin phase iterator, NOT the orchestrator)
- `pipeline_context.py:1-15` — `PIPELINE_CONTEXT` LLM system prompt string loader
- `cinema/phases/base.py:39-57` — `PhaseResult` dataclass
- `cinema/phases/base.py:60-81` — `Phase` Protocol
- `cinema/phases/keyframe_render.py:31-109` — `KeyframeRenderPhase`
- `cinema/phases/performance.py:19-89` — `PerformanceCapturePhase`
- `cinema/phases/motion_render.py:45-54` — `_get_storyboard_mode()` nested-path reader
- `cinema/phases/motion_render.py:57-` — `MotionRenderPhase` + storyboard batch path
- `cinema/review/controller.py:93-98` — `GateNotSatisfiedError`
- `cinema/review/controller.py:224-255` — `_gate_satisfied()` per-gate predicates
- `cinema/review/controller.py:253-281` — `_run_auto_approve_pass()`
- `cinema/review/controller.py:507-559` — `_wait_for_gate()` + headless raise path
- `cinema/checkpoint.py:87-115` — `_save_checkpoint()` atomic write
- `cinema/checkpoint.py:117-134` — `_load_checkpoint()` + file validity check
- `cinema/checkpoint.py:163-` — `_restore_from_checkpoint()` RunState rehydration
- `cinema/auto_approve.py:71-160` — `AutoApproveConfig` fields + `from_project()` + defaults
- `cinema/auto_approve.py:170-200` — `_rules_for_plan()`
- `cinema/auto_approve.py:202-245` — `record_director_review_on_shots()`
- `cinema/auto_approve.py:582-693` — `check_gate()` + `summarize_audit()`
- `cinema/screening.py:65-66` — `SCREENING_STAGE_NAME`, `SCREENING_APPROVED_KEY`
- `cinema/screening.py:84-127` — `_screening_stage_enabled()`
- `cinema/screening.py:275-284` — `is_screening_approved()`
- root `scene_decomposer.py` — 9-LOC re-export shim for `domain/scene_decomposer.py`
- root `dialogue_writer.py` — 9-LOC re-export shim for `domain/dialogue_writer.py`
- root `project_manager.py` — 9-LOC re-export shim for `domain/project_manager.py`

---

## 2. user-entry/web — Web Server & API Surface

*Subsystem key: `web-api`*

### Purpose

`web_server.py` is the sole entry point for human interaction with the pipeline. It is a Flask HTTP server (port 8080) that serves the React frontend, exposes the full REST API for project/character/location/scene CRUD and pipeline control, and streams real-time generation progress to browsers via Server-Sent Events (SSE). `web_services.py` is a narrow companion module (97 LOC) that holds the pure, reusable SSE-event-shaping helper factored out of the server for unit-testability.

### Modules

| Path | Role | Verified LOC |
|---|---|---|
| `web_server.py` | Flask app, all routes, module-level state, concurrency guards | 2587 |
| `web_services.py` | Pure SSE-callback builder (`make_progress_callback`) | 97 |

### Key functions & classes (THE MICRO LEVEL)

**Module-level state (process-singleton, never cleared on project reload):**

- `_progress_queues: dict[str, queue.Queue]` — web_server.py:71. One `queue.Queue` per project-id while a generation run is in flight. Created by `_ensure_progress_queue`, consumed by `api_stream`, popped under `_pipelines_lock` at run completion.
- `_running_pipelines: dict[str, CinemaPipeline]` — web_server.py:72. Maps pid → live `CinemaPipeline` instance (or `_PIPELINE_PENDING` sentinel during constructor window). Single truth source for "is generation active?" logic.
- `_PIPELINE_PENDING = object()` — web_server.py:80. Sentinel placed atomically in `_running_pipelines` while `CinemaPipeline.__init__` runs outside the lock (avoids serializing heavy ctor).
- `_GATE_STAGES = frozenset({"PLAN_REVIEW", "KEYFRAME_REVIEW", "PERFORMANCE_REVIEW", "REVIEW", "SCREENING"})` — web_server.py:93. Stages where the pipeline worker is blocked in `lifecycle.wait_for_gate`; gate-acting endpoints bypass the busy fence.
- `_running_cores: dict[str, PipelineCore]` — web_server.py:108. Cache of expensive long-lived services (ContinuityEngine, ChiefDirector, LLMEnsemble, trackers). Lifetime = process. Not invalidated on settings.json edits.
- `_reassembly_in_flight: set[str]` — web_server.py:124. Guards the re-assembly endpoint against re-entrant calls; separate from `_running_pipelines` because re-assembly runs while the SCREENING gate-waiter occupies `_running_pipelines`.

**Helper functions:**

- `_get_or_build_core(pid)` — web_server.py:128. Thread-safe (`_cores_lock`) get-or-create of `PipelineCore`; raises `ValueError` if pid is invalid.
- `_get_running_pipeline(pid)` — web_server.py:144. Single safe reader of `_running_pipelines`; returns `None` for sentinel or absent. All code that needs the pipeline object MUST use this.
- `_ensure_progress_queue(pid)` — web_server.py:161. Under `_pipelines_lock`, creates and caches a `queue.Queue` if absent.
- `_make_progress_cb(pid, q=None)` — web_server.py:170. Resolves the queue (explicit arg or module-state lookup), delegates to `web_services.make_progress_callback`.
- `_get_stage_pipeline(pid)` — web_server.py:183. Returns the live pipeline if present; otherwise constructs a per-request `CinemaPipeline` sharing the cached core. Used by all gate/take/shot endpoints.
- `_locate_shot(project, shot_id)` — web_server.py:193. Linear scan of `project["scenes"][*]["shots"]`; returns `(scene, shot)` or `(None, None)`.
- `_reject_if_project_busy(pid)` — web_server.py:225. Returns 409 if pid is in `_running_pipelines` (including sentinel).
- `_pipeline_at_gate_stage(pid)` — web_server.py:231. Returns True if the running pipeline's `current_stage` is in `_GATE_STAGES`.
- `_reject_if_project_busy_outside_gate(pid)` — web_server.py:256. Gate-bypass variant of busy fence: allows calls through when pipeline is parked at a review gate. Used by iterate, screening approve, re-assemble.
- `_project_lock_guard` — web_server.py:276. Decorator that catches `ProjectLockError` and returns 409 `project_locked`.

**`make_progress_callback(progress_queue)` (web_services.py:28):**
Returns a callable `progress_cb(stage, detail, percent, scene_id, shot_id, image_url, identity_score, director_review, coherence_score, motion_score, shot_type, failure_reason, quality_metrics, video_url, take_id, take_kind, gate_status, **kwargs)`. Shapes an event dict with only non-empty/non-negative fields, then calls `progress_queue.put(event)`. If `progress_queue` is `None`, the callback is a no-op (tests/headless). This is the interface `CinemaPipeline` receives as `progress_callback`.

### Data IN -> OUT

**IN:**
- HTTP requests from the React SPA (JSON bodies, multipart for file uploads)
- Binary file uploads: character reference images (multipart), location reference images, style board images, driving video (mp4)
- Project configuration JSON (name, `global_settings` dict with aspect ratio, language, mood, style rules, etc.)
- DirectorialIntent JSON for iterate endpoint

**OUT:**
- JSON responses (project objects, shot lists, take results, cost estimates, pipeline state)
- SSE stream (`text/event-stream`): dicts with `{stage, detail, percent, [scene_id, shot_id, image_url, video_url, take_id, take_kind, identity_score, director_review, coherence_score, motion_score, shot_type, failure_reason, quality_metrics, gate_status]}`
- Served static files: React SPA at `/`, media files via `/api/projects/<pid>/file?path=<abs>`, final video download via `/api/projects/<pid>/export`, scene preview via `/api/projects/<pid>/preview/<sid>`

**SSE terminal events:**
- `{stage: "DONE", detail: result, percent: 100}` — successful completion
- `{stage: "ERROR", detail: str(e), percent: 0}` — pipeline exception
- `{stage: "END", detail: "Stream closed", percent: 100}` — sentinel `None` from queue
- `{stage: "HEARTBEAT", detail: "waiting", percent: -1}` — 30 s queue timeout keepalive

### Connects to (which OTHER subsystems it touches, and HOW)

| Subsystem | Contact point | How |
|---|---|---|
| `cinema_pipeline.CinemaPipeline` | web_server.py:55, 1478, 2020, 2404 | Direct construction + method calls. All shot/take/gate/assemble ops delegate to pipeline methods which delegate to `_shot_ctrl` / `_review_ctrl`. |
| `cinema.core.PipelineCore` / `build_pipeline_core` | web_server.py:56, 128–141 | Cached in `_running_cores`; passed to every `CinemaPipeline` constructor. Holds ContinuityEngine, ChiefDirector, LLMEnsemble, trackers. |
| `cinema.services.state_snapshot` / `checkpoint_info` | web_server.py:57, 1520, 1976 | Direct call for lightweight pipeline-state + checkpoint reads without constructing CinemaPipeline. |
| `domain.project_manager` (via shim `project_manager`) | web_server.py:40–47 | `mutate_project`, `load_project`, `create_project`, `delete_project`, `list_projects`, `add_character`, etc. — all project state reads/writes go through here. |
| `domain.character_manager` (via shim `character_manager`) | web_server.py:48 | `create_character_with_images`, `VOICE_POOL` — character creation with image processing. |
| `domain.location_manager` (via shim `location_manager`) | web_server.py:49 | `create_location_with_images` — location creation with image processing. |
| `domain.scene_decomposer` / `scene_decomposer` | web_server.py:50,52 | `decompose_scene`, `update_scene_shots`, config enumerables (`CAMERA_MOTIONS`, `VISUAL_EFFECTS`, `TARGET_APIS`, `API_REGISTRY`, `MUSIC_MOODS`, `PURPOSE_TAGS`, `PURPOSE_API_RANKING`, `BILLING_PROVIDERS`, `estimate_short_cost`). |
| `dialogue_writer` (shim → `domain.dialogue_writer`) | web_server.py:53 | `generate_dialogue` called synchronously on `/scenes/<sid>/generate-dialogue`. |
| `llm.style_director` | web_server.py:54 | `generate_style_rules` — LLM call for style rule generation. |
| `workflow_selector.WORKFLOW_TEMPLATES` | web_server.py:58 | Dict of workflow template configs surfaced via `/api/config`. |
| `web_services.make_progress_callback` | web_server.py:59 | SSE builder; called through `_make_progress_cb` wrapper. |
| `config.settings.settings` | web_server.py:60 | Env-var-driven settings: `web_bind_host`, `web_cors_origins`. |
| `cinema.screening` | web_server.py:2155, 2229, 2342 | `_screening_stage_enabled`, `_build_timeline_manifest`, `mark_screening_approved`, `get_needs_reassembly`, `estimate_reassembly_cost`, `clear_needs_reassembly`. |
| `cinema.shots.controller._directorial_iteration_enabled` | web_server.py:1714 | Feature flag check before iterate endpoint executes. |
| `prep.lora_training` | web_server.py:711 | `train_character_lora`, `get_lora_status` — invoked in background thread. |
| `cost_tracker.CostTracker` | web_server.py:2509 | Direct SQLite query via cached core's tracker for live cost reporting. |
| `cleanup` module | web_server.py:2483, 2494, 2529 | `cleanup_project`, `get_project_disk_usage`, `cleanup_all_projects`. |
| `domain.language_defaults` | web_server.py:413 | `merge_language_defaults_into_settings`, `recommended_voices_for_language`, `get_language_defaults`. |

### User-facing surface & capability knobs

**Environment variables (highest priority — set before server start):**

| Env var | Default | Effect |
|---|---|---|
| `WEB_BIND_HOST` | `127.0.0.1` | Set to `0.0.0.0` for LAN access |
| `WEB_CORS_ORIGINS` | localhost:8080 + localhost:5173 | Set to `*` for wide-open, or comma-separated origins |
| `CINEMA_DIRECTORIAL_ITERATION` | ON (truthy) | Set to `0`/`false`/`no` to disable iterate endpoint |
| `CINEMA_SCREENING_STAGE` | ON (truthy) | Set to `0`/`false`/`no` to disable all three screening endpoints |
| `CINEMA_STRICT_SCHEMA` | OFF | Enables strict Pydantic validation mode project-wide |

**Project-level `global_settings` knobs (set via `PUT /api/projects/<pid>`):**

| Field | Effect |
|---|---|
| `aspect_ratio` | `"16:9"`, `"9:16"`, `"1:1"`, `"21:9"`, `"4:3"` |
| `pacing` | `"relaxed"`, `"moderate"`, `"calculated"`, `"fast"` |
| `music_mood` | from `MUSIC_MOODS` enum |
| `color_palette` | free text or preset key |
| `color_grade` | `"warm_cinema"`, `"cool_noir"`, `"vibrant"`, `"desaturated"`, `"golden_hour"`, `"moonlight"`, `"high_contrast"`, `"pastel"` |
| `language` | passed to `generate_dialogue` and `apply-language-defaults` |
| `style_rules` | dict — written by `/style-rules`, controls LLM prompt conditioning |
| `style_reference_paths` | list of abs paths — written by `/style-board`, drives FLUX Redux |
| `char_lora_paths` | dict `{cid: path}` — written by LoRA training completion |
| `location_research` | bool — enables auto-research on location add (default OFF) |
| `img2img_denoise` | 0.2–0.6 (default 0.35) — continuity strength |
| `identity_threshold` | 0.4–0.8 (default 0.55) — face similarity threshold |
| `ip_adapter_weight` | 0.5–1.0 (default 0.85) — PuLID face-lock strength (per-character AND per-object) |
| `lip_sync_mode` | `"auto"`, `"overlay"`, `"generation"`, `"skip"` |
| `cost_optimization_level` | `"quality_first"`, `"balanced"`, `"budget_conscious"` |
| `creative_llm` | `"auto"`, `"claude-sonnet"`, `"gpt-4o"` |
| `quality_judge` | `"auto"`, `"claude-opus"`, `"gpt-4o"`, `"gemini-pro"` |

**Per-shot knobs (set via `PUT /api/projects/<pid>/shots/<shot_id>`):** `target_api`, `camera`, `visual_effect`, `prompt`, `scene_foley`, `negative_constraints`, `continuity_constraints`, `intent_notes`.

**Quality maximization levers:** set `ip_adapter_weight=1.0` + `identity_threshold=0.55` + `img2img_denoise=0.2` for maximum character consistency; use `quality_first` cost tier; set `creative_llm=claude-opus` + `quality_judge=claude-opus` for best LLM quality (note: `claude-opus` in the option label; runtime routing maps this); upload 25–50 character reference images before LoRA training.

### Control & data flow (how a run moves through this subsystem, step by step)

1. **Create project:** `POST /api/projects` → `create_project(name)` in `domain/project_manager.py` → returns project JSON with id (pid).
2. **Configure:** `PUT /api/projects/<pid>` with `global_settings` dict. Characters added via `POST /api/projects/<pid>/characters` (multipart with reference images → `create_character_with_images`). Locations via `POST .../locations`. Style board via `POST .../style-board`. Scenes via `POST .../scenes`.
3. **Prepare scenes:** `POST .../scenes/<sid>/generate-dialogue` → synchronous LLM call → returns `dialogue_lines`. `POST .../scenes/<sid>/decompose` → `decompose_scene` → `update_scene_shots` → returns shot array. `POST .../style-rules` → LLM → persists `style_rules` into `global_settings`.
4. **Start generation:** `POST /api/projects/<pid>/generate` with optional `{"resume": true}`.
   - Under `_pipelines_lock`: checks not already running; places `_PIPELINE_PENDING` sentinel; releases lock.
   - Creates `queue.Queue` via `_ensure_progress_queue`.
   - Spawns daemon thread calling `run_pipeline()`.
   - Thread: constructs `CinemaPipeline(pid, core=_get_or_build_core(pid), progress_callback=cb)`; replaces sentinel with real pipeline; calls `pipeline.generate(resume=resume)`.
   - Returns immediately: `{"started": true, "resume": ..., "message": "..."}`.
5. **Stream progress:** Client opens `GET /api/projects/<pid>/stream` → Flask generator yields `data: <json>\n\n` events from the queue. Heartbeat every 30 s of silence. Stream terminates on `None` sentinel (run complete or errored). Only one SSE client can drain the queue (no fan-out; second subscriber would starve).
6. **Review gates:** At each gate (PLAN_REVIEW, KEYFRAME_REVIEW, etc.) the pipeline worker blocks in `lifecycle.wait_for_gate`. User acts on review UI:
   - Shot plan: `POST .../shots/<shot_id>/plan/approve` or `.../plan/reject` → `pipeline.approve_shot_plan(shot_id, approved, reason)`.
   - Keyframe take: `POST .../keyframes/<take_id>/approve` → `pipeline.approve_take(shot_id, take_id, "keyframe")`.
   - Performance take: `POST .../performance/<take_id>/approve` → `pipeline.approve_take(..., "performance")`.
   - Final take: `POST .../final/<take_id>/approve` → `pipeline.approve_take(..., "final")`.
   - During any gate: `POST .../takes/<take_id>/iterate` with DirectorialIntent body → `pipeline.regenerate_with_intent(scene_id, shot_id, take_id, intent, project_id=pid)`. Uses gate-bypass busy fence.
7. **Assemble:** `POST /api/projects/<pid>/assemble` (alias: `/proceed-assembly`) → calls `pipeline.proceed_to_assembly()` if pipeline running, else constructs fresh pipeline and calls `assemble_approved_takes()`.
8. **Screening (Surface B):** `POST .../assemble/screen` → returns `assembled_mp4_path`, `timeline_manifest`, `needs_reassembly`, `cost_estimate_seconds`. Pipeline parks at SCREENING gate. Operator previews, optionally iterates shots (iterate-during-SCREENING enabled by gate-bypass). `POST .../assemble/re-assemble` → constructs fresh `CinemaPipeline` with no-op progress callback; calls `pipeline._assemble_approved_takes_core()` directly (bypasses SCREENING gate-wait). `POST .../screening/approve` → `mark_screening_approved(pid)` + nudges lifecycle event → pipeline unblocks and terminates.
9. **Retrieve output:** `GET /api/projects/<pid>/export` → streams `exports/final_cinema.mp4`. `GET /api/projects/<pid>/preview/<sid>` → streams per-scene preview. `GET .../file?path=<abs>` → security-checked send_file.
10. **Cleanup/termination:** `POST .../cancel` → `pipeline.cancel()`. `POST .../pause` → `pipeline.pause()`. `POST .../resume` → `pipeline.resume()`. At run completion/error/cancel: thread pops pid from `_running_pipelines` and `_progress_queues` under lock; puts `None` into queue to close SSE stream.

### Gotchas, divergences & doc-drift

1. **Single SSE consumer:** `api_stream` has no fan-out mechanism. A second browser tab connecting to the same `/stream` would drain events from the shared queue, causing both tabs to miss events. web_server.py:1526–1541.

2. **SSE queue lifecycle race:** The queue is created before `_PIPELINE_PENDING` is replaced, but popped from `_progress_queues` only after run completion. Between the `q.put(None)` sentinel and the next `_ensure_progress_queue` call, a race client could get `None` and terminate. The `if _progress_queues.get(pid) is q` identity check (web_server.py:1501) prevents clobbering a replacement queue from a concurrent new run.

3. **`_running_cores` not invalidated on settings change:** A project's `PipelineCore` is cached per process restart. Editing `settings.json` out-of-band (e.g., manually) does NOT reload the core. Server restart required. Documented at web_server.py:104–107.

4. **Re-assembly no-op progress callback:** `api_assemble_reassemble` passes `lambda *args, **kwargs: None` as progress callback (web_server.py:2407) to avoid leaking SCENE_PREVIEW/ASSEMBLY events backward into the SCREENING-stage SSE stream. If a progress UI needs re-assembly progress, this is the hard limit.

5. **`api_assemble_reassemble` calls `_assemble_approved_takes_core` directly:** Must NOT call `assemble_approved_takes()` which appends the SCREENING gate-wait — calling the full public method from the re-assemble endpoint would deadlock (the approve signal targets the original pipeline, not the fresh CinemaPipeline constructed here). web_server.py:2418.

6. **Dual-module shims:** `project_manager.py`, `character_manager.py`, `location_manager.py`, `scene_decomposer.py`, `dialogue_writer.py` at repo root are all 9-line `from domain.<X> import *` shims. Canonical implementations live in `domain/`. Import either; they resolve identically. Verified via `wc -l` above.

7. **No auth/permissions layer.** There is no authentication, API key validation, user session management, or rate limiting in the web server. CORS policy is the only access control. Wide-open config (`WEB_CORS_ORIGINS=*` + `WEB_BIND_HOST=0.0.0.0`) exposes all project data and LLM/video API triggers to any LAN device.

8. **`/api/projects/<pid>/shots/<shot_id>` PUT field allowlist:** Only `target_api`, `camera`, `visual_effect`, `prompt`, `scene_foley`, `negative_constraints`, `continuity_constraints`, `intent_notes` are accepted. Any other field in the body is silently dropped. web_server.py:1900–1910.

9. **`/api/projects/<pid>/shots/<shot_id>/reject-auto-approve` body:** Requires both `gate` (one of `plan|image|motion|final`) and `reason` (non-empty). Returns 400 if either missing. web_server.py:1812–1816.

10. **`/api/projects/<pid>/iterate` nested vs flat body:** Accepts both `{intent: {prose, ...}}` (nested) and `{prose, ...}` (flat). Nested wins on ambiguity. web_server.py:1747.

11. **`screening/approve` precondition:** Requires `exports/final_cinema.mp4` to exist on disk; returns 409 `cannot_approve_screening` if not. Added as V1 defence against URL-level callers skipping assembly. web_server.py:2258–2263.

12. **`CINEMA_DIRECTORIAL_ITERATION` and `CINEMA_SCREENING_STAGE` default ON** (both return 404 only when explicitly set to falsy values `"0"`, `"false"`, `"no"`, `"off"`, `""`). cinema/shots/controller.py:111, cinema/screening.py:127.

13. **`/api/projects/<pid>/assemble` has two routes:** Both `POST /api/projects/<pid>/assemble` and `/api/projects/<pid>/proceed-assembly` map to `api_proceed_assembly`. web_server.py:2105–2106.

14. **LoRA training thread tracking key:** `f"{pid}:{cid}"` not just `cid`. Allows training different characters on the same project simultaneously. web_server.py:708.

### Citations

| Claim | File:Line |
|---|---|
| Flask app creation | web_server.py:62 |
| CORS configuration | web_server.py:68 |
| `_progress_queues` declaration | web_server.py:71 |
| `_running_pipelines` declaration | web_server.py:72 |
| `_PIPELINE_PENDING` sentinel | web_server.py:80 |
| `_GATE_STAGES` frozenset | web_server.py:93–99 |
| `_running_cores` cache | web_server.py:108–109 |
| `_reassembly_in_flight` guard | web_server.py:124–125 |
| `_get_or_build_core` | web_server.py:128–141 |
| `_get_running_pipeline` | web_server.py:144–158 |
| `_ensure_progress_queue` | web_server.py:161–167 |
| `_make_progress_cb` | web_server.py:170–180 |
| `_get_stage_pipeline` | web_server.py:183–190 |
| `_locate_shot` | web_server.py:193–198 |
| `_reject_if_project_busy` | web_server.py:225–228 |
| `_pipeline_at_gate_stage` | web_server.py:231–253 |
| `_reject_if_project_busy_outside_gate` | web_server.py:256–273 |
| `_project_lock_guard` decorator | web_server.py:276–284 |
| `GET /api/config` | web_server.py:308–381 |
| `POST /api/projects/<pid>/apply-language-defaults` | web_server.py:384–445 |
| `POST /api/cost-estimate` | web_server.py:448–459 |
| `GET /api/projects` | web_server.py:466–468 |
| `POST /api/projects` | web_server.py:471–476 |
| `GET /api/projects/<pid>` | web_server.py:479–484 |
| `PUT /api/projects/<pid>` | web_server.py:487–513 |
| `DELETE /api/projects/<pid>` | web_server.py:516–525 |
| `POST .../characters` | web_server.py:532–573 |
| `PUT .../characters/<cid>` | web_server.py:574–655 |
| `DELETE .../characters/<cid>` | web_server.py:656–686 |
| `POST .../characters/<cid>/train-lora` | web_server.py:687–760 |
| `GET .../characters/<cid>/lora-status` | web_server.py:763–771 |
| `POST .../shots/<sid>/upload-driving-video` | web_server.py:774–835 |
| `DELETE .../shots/<sid>/performance` | web_server.py:838–875 |
| `POST .../style-board` | web_server.py:878–926 |
| `POST .../objects` | web_server.py:929–993 |
| `PUT .../objects/<oid>` | web_server.py:996–1072 |
| `DELETE .../objects/<oid>` | web_server.py:1073–1092 |
| `POST .../locations` | web_server.py:1093–1137 |
| `PUT .../locations/<lid>` | web_server.py:1140–1212 |
| `DELETE .../locations/<lid>` | web_server.py:1215–1227 |
| `POST .../scenes` | web_server.py:1234–1259 |
| `PUT .../scenes/<sid>` | web_server.py:1260–1276 |
| `DELETE .../scenes/<sid>` | web_server.py:1277–1291 |
| `POST .../scenes/reorder` | web_server.py:1292–1311 |
| `POST .../scenes/<sid>/generate-dialogue` | web_server.py:1312–1341 |
| `POST .../scenes/<sid>/decompose` | web_server.py:1348–1390 |
| `POST .../style-rules` | web_server.py:1397–1447 |
| `POST .../generate` (pipeline start) | web_server.py:1454–1508 |
| `GET .../checkpoint` | web_server.py:1511–1520 |
| `GET .../stream` (SSE) | web_server.py:1523–1541 |
| `POST .../cancel` | web_server.py:1544–1550 |
| `GET .../file` | web_server.py:1557–1571 |
| `POST .../shots/<shot_id>/plan/approve` | web_server.py:1574–1583 |
| `POST .../shots/<shot_id>/plan/reject` | web_server.py:1586–1596 |
| `POST .../shots/<shot_id>/keyframes/generate` | web_server.py:1599–1621 |
| `POST .../keyframes/<take_id>/approve` | web_server.py:1624–1633 |
| `POST .../performance/<take_id>/approve` | web_server.py:1635–1650 |
| `POST .../shots/<shot_id>/motion/generate` | web_server.py:1653–1669 |
| `POST .../final/<take_id>/approve` | web_server.py:1672–1680 |
| `POST .../takes/<take_id>/iterate` | web_server.py:1683–1783 |
| `POST .../shots/<shot_id>/reject-auto-approve` | web_server.py:1786–1855 |
| `PUT .../shots/<shot_id>/prompt` | web_server.py:1858–1891 |
| `PUT .../shots/<shot_id>` | web_server.py:1892–1938 |
| `POST .../pause` | web_server.py:1945–1952 |
| `POST .../resume` | web_server.py:1955–1962 |
| `GET .../pipeline-state` | web_server.py:1965–1976 |
| `POST .../shots/<shot_id>/restart` | web_server.py:1979–2024 |
| `POST .../shots/<shot_id>/regenerate` | web_server.py:2027–2071 |
| `POST .../shots/<shot_id>/correct` | web_server.py:2074–2091 |
| `POST .../shots/<shot_id>/diagnose` | web_server.py:2094–2102 |
| `POST .../assemble` (alias /proceed-assembly) | web_server.py:2105–2120 |
| `POST .../assemble/screen` | web_server.py:2127–2207 |
| `POST .../screening/approve` | web_server.py:2210–2297 |
| `POST .../assemble/re-assemble` | web_server.py:2299–2473 |
| `POST .../cleanup` | web_server.py:2480–2490 |
| `GET .../disk-usage` | web_server.py:2493–2497 |
| `GET .../cost-live` | web_server.py:2500–2523 |
| `POST /api/cleanup-all` | web_server.py:2526–2533 |
| `GET .../export` | web_server.py:2536–2542 |
| `GET .../preview/<sid>` | web_server.py:2545–2551 |
| `make_progress_callback` | web_services.py:28–97 |
| `state_snapshot` | cinema/services.py:61–97 |
| `checkpoint_info` | cinema/services.py:100–133 |
| project_manager shim | project_manager.py:9 |
| character_manager shim | character_manager.py:9 |
| `web_bind_host` / `web_cors_origins` settings | config/settings.py:96–97, 131–132 |
| `CINEMA_DIRECTORIAL_ITERATION` flag impl | cinema/shots/controller.py:101–111 |
| `CINEMA_SCREENING_STAGE` flag impl | cinema/screening.py:86–127 |
| Server bind port 8080 | web_server.py:2587 |

---

## 3. phase-system — Phase Abstraction

*Subsystem key: `phases`*

### Purpose (2-4 sentences)

The phase abstraction decouples the three main per-shot render loops (keyframe generation, performance capture, motion/video generation) from the `CinemaPipeline` orchestrator by wrapping each loop in a lightweight Protocol-conforming class. Each phase receives a shared `PipelineContext` (lifecycle + project settings), executes its loop over the project's shots, and returns a `PhaseResult` signalling success or cancellation — leaving gate logic and retry policy to the caller. `cinema/services.py` is a companion module that exposes two read-only helpers for web endpoints, allowing disk-state reads without constructing the full (heavy) `CinemaPipeline`. `cinema/pipeline.py` provides a generic `CinemaPipeline` driver (list-of-phases executor) available to any caller, distinct from the concrete `cinema_pipeline.CinemaPipeline` orchestrator that embeds the phase classes directly.

### Modules

| Path | Role | LOC |
|---|---|---|
| `cinema/phases/base.py` | `Phase` Protocol + `PhaseResult` dataclass — the entire contract | 81 |
| `cinema/phases/keyframe_render.py` | `KeyframeRenderPhase` — per-shot image generation loop | 109 |
| `cinema/phases/performance.py` | `PerformanceCapturePhase` — per-shot performance retargeting loop | 89 |
| `cinema/phases/motion_render.py` | `MotionRenderPhase` — per-shot image→video loop + storyboard batch path | 412 |
| `cinema/services.py` | Read-only disk-state helpers for web endpoints (`state_snapshot`, `checkpoint_info`) | 133 |
| `cinema/pipeline.py` | Generic `CinemaPipeline` driver (list-of-Phase executor, not the interactive pipeline) | 115 |

### Key functions & classes (THE MICRO LEVEL)

#### `cinema/phases/base.py`

**`PhaseResult`** (`base.py:39`) — `@dataclass` with three fields: `ok: bool` (gate-keeping signal), `message: str` (human-readable log, ignored on success in non-verbose mode), `elapsed_s: float` (wall-clock seconds for perf tracking). The orchestrator's only input is `ok`.

**`Phase`** (`base.py:60-81`) — `@runtime_checkable Protocol`. Requires `name: str` (used as key in logs, progress callbacks, per-phase config) and `run(self, ctx: PipelineContext) -> PhaseResult`. No inheritance required — any class with those two attributes satisfies `isinstance(x, Phase)`. Retry policy and fallback logic are explicitly NOT part of the phase contract.

#### `cinema/phases/keyframe_render.py`

**`KeyframeRenderPhase`** (`keyframe_render.py:31`) — class with `name = "keyframe_render"`.

**`KeyframeRenderPhase.__init__`** (`keyframe_render.py:36-66`) — params: `shot_generator` (duck-typed, must have `generate_keyframe_take(scene_id, shot_id)`; in production this is the `CinemaPipeline` instance which delegates to `ShotController`), `project: Optional[dict]` (raw project dict from `load_project()`), `on_failure: Optional[Callable[[str, str, str], None]]` (called with `(scene_id, shot_id, error)` on per-shot failure, defaults to no-op). All params default `None` so bare instantiation satisfies the smoke test — `run()` returns `ok=False` with "not configured" message in that case.

**`KeyframeRenderPhase.run`** (`keyframe_render.py:68-109`) — Iterates `project["scenes"][...]["shots"][...]`. Skips shots with `shot["approved_keyframe_take_id"]` truthy (skip_count). Calls `self._gen.generate_keyframe_take(scene_id, shot_id)` for each non-skipped shot. On success increments `ok_count`; on failure increments `fail_count` and calls `on_failure`. Cancellation polled at every scene boundary AND every shot boundary via `ctx.lifecycle.is_cancelled()`; returns `PhaseResult(ok=False, message="cancelled (...)")` with partial counts. Returns `PhaseResult(ok=True, ...)` even if `fail_count > 0` — **partial failures do NOT fail the phase** (matches legacy behavior where operators rework failed shots from the review UI). `elapsed_s` is wall-clock from `time.time()` at entry.

#### `cinema/phases/performance.py`

**`PerformanceCapturePhase`** (`performance.py:19`) — class with `name = "performance_capture"`. Identical shape to `KeyframeRenderPhase`.

**`PerformanceCapturePhase.__init__`** (`cinema/phases/performance.py:25-33`) — same three params; `shot_generator` must expose `generate_performance_take(scene_id, shot_id)`.

**`PerformanceCapturePhase.run`** (`cinema/phases/performance.py:35-89`) — Three skip conditions per shot: (1) `shot["approved_performance_take_id"]` is truthy; (2) `(shot["performance_engine"] or "").upper() == "SKIP"` (explicitly routed away by the domain router); (3) `not shot["approved_keyframe_take_id"]` (no anchor image yet — motion would also skip). Calls `self._gen.generate_performance_take(scene_id, shot_id)`. Also handles `result.get("skipped")` — a result can succeed but report itself as skipped (SKIP-engine path returns from within the ShotController). Always returns `ok=True`; partial failures do not fail the phase.

#### `cinema/phases/motion_render.py`

**`_get_storyboard_mode`** (`motion_render.py:45-54`) — module-level function. Reads `project["global_settings"]["api_engines"]["KLING_NATIVE"]["storyboard_mode"]`; returns `bool`, defaults `False` at every level. This is the entry point for the storyboard batch toggle.

**`MotionRenderPhase`** (`motion_render.py:57`) — class with `name = "motion_render"`.

**`MotionRenderPhase.__init__`** (`motion_render.py:62-72`) — same three params; `shot_generator` must expose `generate_motion_take(scene_id, shot_id)`.

**`MotionRenderPhase._scene_keyframes`** (`motion_render.py:78-94`) — helper for storyboard eligibility. Iterates a list of shots; for each, resolves the approved keyframe path via `self._gen._resolve_take_path(shot, kf_take_id)`. Returns `list[(shot, kf_path)]` if ALL shots have approved keyframes with files on disk; returns `None` if any is missing, blocking the batch path.

**`MotionRenderPhase._run_storyboard_scene`** (`motion_render.py:100-315`) — batch path. Dynamically imports `KlingNativeAPI`, `split_video_into_segments`, `make_take`. Builds per-shot prompt list (`motion_description` or `prompt` or `camera` or `"cinematic motion"`), durations, and `image_references` (keyframes of shots 1..N-1 for cross-shot consistency). Calls `kling.generate_storyboard(image_path=anchor_kf, shots=..., output_path=..., image_references=...)`. Records ONE batch cost via `self._gen.cost_tracker.record_api_call("KLING_NATIVE", ...)`. Calls `split_video_into_segments(source_path, durations, output_dir, stem)`. Registers each segment via `ctrl._finalize_motion_take(..., record_cost=False)`. On per-segment finalize failure: retries that shot via `self._gen.generate_motion_take(scene_id, shot_id)` (does NOT lose the batch; only the one segment falls back). Returns `(ok_count, fail_count, success: bool)`. On any import error, storyboard-generate-None, split-failure, or segment-count mismatch: returns `success=False`, leaving counters unchanged so per-shot fallback can accumulate.

**`MotionRenderPhase.run`** (`motion_render.py:321-412`) — Main run loop. Reads `_get_storyboard_mode(self._project)` once. Per scene: partitions shots into `approved` (skip, skip_count += len(approved)) and `unapproved`. If `storyboard_mode AND 2 <= len(unapproved) <= 6`: checks eligibility via `_scene_keyframes()`, then calls `_run_storyboard_scene()` if eligible; if `batch_ok=True`, skips the per-shot loop for that scene. Otherwise (storyboard off / ineligible / batch failed): per-shot loop calling `self._gen.generate_motion_take(scene_id, shot_id)`. Cancellation polled at scene boundary and shot boundary. Returns `PhaseResult(ok=True, ...)` always — partial failures do not fail the phase.

#### `cinema/services.py`

**`_iter_shots`** (`services.py:40-45`) — helper: flattens project scenes→shots into `List[(scene, shot_index, shot)]`.

**`_project_gate_status`** (`services.py:48-58`) — computes `{total_shots, plans_approved, keyframes_approved, motions_generated, finals_approved}` counts by scanning shot fields (`plan_status == "approved"`, `approved_keyframe_take_id`, `motion_takes`, `approved_final_take_id`). Mirrors the in-class implementation.

**`state_snapshot`** (`services.py:61-97`) — params: `project_id: str`. Calls `load_project(project_id)`. Returns a `pipeline-state`-shaped dict: `paused=False, cancelled=False, current_stage="", current_scene_id="", current_shot_id="", shot_results={}, failed_shots=[], scenes_completed=0, gate_status=_project_gate_status(project)`. In-memory fields (`current_stage`, `shot_results`, `failed_shots`) are always empty — they only exist on a live pipeline object. Used by `web_server.py:1976` for `/api/projects/<pid>/pipeline-state` when no run is in flight.

**`checkpoint_info`** (`services.py:100-133`) — params: `project_id: str`. Reads `<project_dir>/temp/pipeline_state.json` directly (no `CinemaPipeline` construction). Returns `{resumable: False}` if project absent or file missing/corrupt. Otherwise returns `{resumable: True, completed_scenes: N, total_scenes: N, stage: str, shots_done: N, shots_failed: N}`. `shots_done` excludes statuses `"failed"` and `"lost"`. Used by `web_server.py:1520` for `/api/projects/<pid>/checkpoint`.

#### `cinema/pipeline.py` (generic driver)

**`PipelineRunResult`** (`pipeline.py:57-77`) — `@dataclass`: `ok: bool`, `failed_phase: Optional[str]`, `failed_message: str`, `phase_results: List[Tuple[str, PhaseResult]]` (every phase that ran in order).

**`CinemaPipeline`** (`pipeline.py:80-114`) — generic driver (NOT the same as `cinema_pipeline.CinemaPipeline`). Constructed with `phases: List[Phase]`, `ctx: PipelineContext`, optional `progress_callback`. `run()` iterates phases in order, calls `phase.run(self.ctx)`, invokes progress callback, short-circuits on first `ok=False`. Does not retry, skip, or reorder. Returns `PipelineRunResult`.

### Data IN -> OUT

**IN to phase instances (constructor injection):**
- `project: dict` — raw project dict from `load_project()`, containing `scenes[].shots[]` with all per-shot state fields (`approved_keyframe_take_id`, `approved_final_take_id`, `approved_performance_take_id`, `performance_engine`, `motion_takes`, `duration`, `motion_description`, `prompt`, `camera`).
- `shot_generator` — duck-typed handle to `CinemaPipeline` (which delegates to `ShotController`); must expose `generate_keyframe_take`, `generate_performance_take`, `generate_motion_take`, `_resolve_take_path`, `_shot_ctrl`, `cost_tracker`.
- `on_failure: Callable[[scene_id, shot_id, error], None]` — back-channel to orchestrator's `failed_shots` list + SSE progress events.

**IN via `ctx: PipelineContext` at `run()` time:**
- `ctx.lifecycle` — `LifecycleService` exposing `is_cancelled() -> bool`. Phases poll this at scene and shot boundaries.
- `ctx.global_settings` — per-project UI settings dict (used upstream by audio/lipsync helpers that run outside phases; phases themselves do not read `ctx.global_settings` directly — `_get_storyboard_mode` reads from `self._project`, not `ctx`).

**OUT from phases:**
- `PhaseResult(ok, message, elapsed_s)` — primary return to orchestrator.
- Side-effects via `shot_generator` calls: each `generate_*_take` call persists take records to disk (via `ShotController._finalize_motion_take` etc.) and mutates the project JSON via `mutate_project`.
- `on_failure` callbacks: append shot_id to `CinemaPipeline.failed_shots`; emit `SHOT_FAILED` SSE progress event.
- `cost_tracker.record_api_call(...)` in storyboard batch path (`motion_render.py:187-198`).

**OUT from `cinema/services.py`:**
- `state_snapshot(pid) -> dict` — gate-status summary for web endpoint (no pipeline object).
- `checkpoint_info(pid) -> dict` — resume-info for web endpoint (no pipeline object).

### Connects to

| Subsystem | How |
|---|---|
| `cinema_pipeline.CinemaPipeline` (orchestrator) | Direct instantiation and `.run(ctx)` call at `cinema_pipeline.py:994,1024,1071`. Phases receive `self` (the pipeline) as `shot_generator`. |
| `cinema/shots/controller.ShotController` | Via `shot_generator.generate_keyframe_take/performance_take/motion_take` which are thin delegates (`cinema_pipeline.py:235-242`) forwarding to `self._shot_ctrl`. Direct access also via `self._gen._shot_ctrl` in `_run_storyboard_scene` for `_finalize_motion_take`. |
| `cinema/lifecycle.py` (`LifecycleService`) | Via `ctx.lifecycle.is_cancelled()` — polled per scene and per shot in all three phases. |
| `cinema/context.py` (`PipelineContext`) | Passed as `ctx` to every `run()` call. Phases read `ctx.lifecycle`; `PipelineContext` also carries `global_settings` and all script/audio/output fields used by surrounding non-phase code. |
| `kling_native.KlingNativeAPI` | Dynamic import inside `_run_storyboard_scene`; called as `kling.generate_storyboard(...)`. |
| `phase_c_ffmpeg.split_video_into_segments` | Dynamic import inside `_run_storyboard_scene`; splits the combined storyboard output. |
| `domain/project_manager.py` (`load_project`, `get_project_dir`, `make_take`) | `cinema/services.py` imports `load_project` and `get_project_dir` directly. `_run_storyboard_scene` dynamically imports `make_take` to construct a take record. |
| `workflow_selector.classify_shot_type` | Dynamic import in `_run_storyboard_scene` to resolve per-shot type for `_finalize_motion_take`. |
| `CinemaPipeline.cost_tracker` | Called in `_run_storyboard_scene` via `self._gen.cost_tracker.record_api_call(...)` to record batch cost. |
| `web_server.py` | Consumes `cinema.services.state_snapshot` at line 1976 and `cinema.services.checkpoint_info` at line 1520. |
| `cinema/pipeline.py` (`CinemaPipeline` generic driver) | Imports `Phase` and `PhaseResult` from `cinema/phases/base.py` (`pipeline.py:39`). Used as a standalone driver by any caller that wants a typed list-of-phases executor — currently not wired into `cinema_pipeline.CinemaPipeline`'s main `generate()` path (phases there are run directly with `.run(ctx)`). |

### User-facing surface & capability knobs

| Knob | Where set | Path in project dict | Effect |
|---|---|---|---|
| `storyboard_mode` | Web UI project settings → `global_settings.api_engines.KLING_NATIVE.storyboard_mode` (default `False`; initialized at `web_server.py:343`) | `project["global_settings"]["api_engines"]["KLING_NATIVE"]["storyboard_mode"]` | Enables Kling storyboard batch path in `MotionRenderPhase` for scenes with 2–6 unapproved shots (all with approved keyframes). ONE generation call per eligible scene instead of N. Improves cross-shot character/style consistency via `image_references`. Falls through to per-shot on any failure. |
| `performance_engine` per shot | Web UI / operator; initially set by `route_performance_engine()` | `shot["performance_engine"]` | `"ACT_ONE" | "LIVE_PORTRAIT" | "VIGGLE" | "SKIP" | ""`. `"SKIP"` causes `PerformanceCapturePhase` to skip that shot with no generation. PERFORMANCE_REVIEW gate lets operator re-route. |
| `headless=True` on `CinemaPipeline` | Caller (Python API / E2E scripts) | Constructor param | Gates raise `GateNotSatisfiedError` instead of blocking; enables unattended runs. Does not affect phase logic directly — affects how `ctx.lifecycle` responds. |
| Shot `duration` field | Project JSON per shot | `shot["duration"]` | Used by storyboard batch to set per-shot durations in the `shots_for_storyboard` list passed to `KlingNativeAPI.generate_storyboard`. Default `5.0` seconds (`motion_render.py:140`). |
| `motion_description` / `prompt` / `camera` per shot | Project JSON per shot (operator-authored) | `shot["motion_description"]`, `shot["prompt"]`, `shot["camera"]` | Storyboard batch uses first truthy among these as the per-shot motion prompt (`motion_render.py:135-139`). Quality of storyboard batch output directly depends on these. |

**To maximize quality/capability:**
- Enable `storyboard_mode` for dialogue/character-heavy scenes (2–6 shots) to get cross-shot image consistency via `image_references`.
- Write explicit `motion_description` per shot (most specific; fallback chain is `motion_description > prompt > camera > "cinematic motion"`).
- Ensure all shots have approved keyframes before the motion phase runs (missing keyframe → storyboard batch ineligible → falls back to per-shot which itself has the same precondition check in `ShotController`).
- Use `headless=True` + `CinemaPipeline` for E2E pipelines; gates auto-satisfy when pre-approved.

### Control & data flow

1. **Orchestrator (`cinema_pipeline.CinemaPipeline.generate()`) constructs `PipelineContext`** at `cinema_pipeline.py:978-982` with `lifecycle=self.lifecycle`, `global_settings` from the current project snapshot, `language`. This ctx is passed to all three phases.

2. **Keyframe phase** (`cinema_pipeline.py:994-998`): `KeyframeRenderPhase(shot_generator=self, project=project, on_failure=_on_keyframe_fail).run(ctx)`. Iterates all scenes/shots; skips already-approved; generates new keyframes via `ShotController`; persists takes to disk. Returns `PhaseResult`. Orchestrator emits `progress("KEYFRAME_DONE", ...)` at 50%.

3. **KEYFRAME_REVIEW gate** (`cinema_pipeline.py:1004-1006`): blocks (or raises in headless mode) until operator approves all keyframes. Not a phase — inline in orchestrator. Refreshes project snapshot after gate clears.

4. **Performance phase** (`cinema_pipeline.py:1024-1028`): `PerformanceCapturePhase(...).run(ctx)`. Three skip conditions per shot. Calls `ShotController.generate_performance_take()`. Orchestrator emits `progress("PERFORMANCE_DONE", ...)` at 62%.

5. **PERFORMANCE_REVIEW gate** (`cinema_pipeline.py:1044-1058`): auto-skipped if all shots are SKIP-routed or have no approved keyframe. Otherwise blocks for operator review. Not a phase.

6. **Motion phase** (`cinema_pipeline.py:1071-1075`): `MotionRenderPhase(...).run(ctx)`. Per scene: checks storyboard eligibility; either runs batch path (→ `KlingNativeAPI.generate_storyboard` → `split_video_into_segments` → N × `_finalize_motion_take`) or per-shot path (→ `ShotController.generate_motion_take`). Orchestrator emits `progress("MOTION_DONE", ...)` at 80%.

7. **REVIEW gate** (`cinema_pipeline.py:1084`): final approval before assembly. Not a phase.

8. **Assembly** (`cinema_pipeline.py:1091`): `assemble_approved_takes()`. Not a phase.

**`cinema/pipeline.py` driver** (alternative path, not used by `generate()`): instantiate `CinemaPipeline(phases=[...], ctx=...)`, call `run()`. Iterates phases in order, short-circuits on `ok=False`, invokes progress callback after each. No gates, no retry, no project-specific logic.

**`cinema/services.py` path** (web endpoints, no pipeline object): `state_snapshot(pid)` → `load_project(pid)` → `_project_gate_status(project)` → return shaped dict. `checkpoint_info(pid)` → `load_project(pid)` → read `<project_dir>/temp/pipeline_state.json` → return resume-info dict. Both are read-only; no phase classes involved.

### Gotchas, divergences & doc-drift

1. **Two unrelated classes named `CinemaPipeline`**: `cinema/pipeline.py:80` (generic list-of-phases driver) vs. `cinema_pipeline.CinemaPipeline:38` (the full interactive orchestrator). The generic driver is NOT used inside `generate()` — the three phases are instantiated and `.run(ctx)` called directly. The generic driver is available for external use. Doc claims about "the orchestrator" may conflate the two.

2. **`ctx.global_settings` is NOT used by phases directly**: The docstring at `cinema_pipeline.py:973-976` explains it's threaded in for audio/lipsync helpers called *outside* phases. `_get_storyboard_mode` reads from `self._project`, not `ctx`. `PerformanceCapturePhase` does not read `ctx.global_settings`. This is correct per design but easily misread.

3. **Storyboard eligibility is 2–6 shots**: `motion_render.py:359` — `2 <= len(unapproved) <= 6`. A single-shot scene or a 7+ shot scene always takes the per-shot path even with `storyboard_mode=True`. Not documented in ARCHITECTURE.md.

4. **`_run_storyboard_scene` accesses private `_shot_ctrl` and `_review_ctrl` internals**: `motion_render.py:153` uses `self._gen._shot_ctrl._take_output_path(...)` and `motion_render.py:230` uses `self._gen._shot_ctrl` directly. Phase isolation is broken — the phase is coupled to `CinemaPipeline`'s internal structure. The fallback path (`/tmp/storyboard_{pid}_{scene_id}.mp4`) guards against this in test stubs.

5. **All three phases always return `ok=True`** regardless of per-shot failure count. The orchestrator never terminates the pipeline due to a phase returning `ok=False` for failed shots. The only `ok=False` returns are: (a) missing constructor args, (b) cancellation. A scene where every single shot fails still produces `PhaseResult(ok=True, message="motion: 0 new, 0 pre-finalized, 5 failed")`. Callers must check `failed_shots` (accumulated via `on_failure` callbacks) to know about per-shot failures.

6. **`PerformanceCapturePhase` gate is auto-skipped only if ALL shots are SKIP**: `cinema_pipeline.py:1038-1043` — the predicate checks `performance_engine == "SKIP" OR not approved_keyframe_take_id`. A single shot that was supposed to get a performance but failed (and landed in `failed_shots`) would keep the gate open. Operator must manually handle.

7. **Internal planning terms "F2b" / "Tier F NEW-2"** appear as code comments (`cinema/phases/motion_render.py:17` "Storyboard batch path (F2b)"; `cinema/phases/motion_render.py:185` "Tier F NEW-2") — migration-slice terminology, not external API names.

8. **`cinema/services.py` was introduced as Slice 3b/Phase 7 (REFACTOR_HANDOFF §9.2)** — the module docstring mentions this provenance. The contract it implements (`state_snapshot` replaces `CinemaPipeline(pid).get_state()`; `checkpoint_info` replaces `CinemaPipeline(pid).resume_info()`) is stable but the old call-site pattern may appear in older docs.

9. **`check_doc_claims.py` misses prose/comment line-range anchors** (per memory entry): line shifts after edits invalidate line-anchor refs. The `cinema/phases/` files are relatively stable but any rebase or insertion shifts line numbers. The citations below are point-in-time.

### Citations

| Claim | File:line |
|---|---|
| `Phase` Protocol definition | `cinema/phases/base.py:60-81` |
| `PhaseResult` dataclass | `cinema/phases/base.py:38-57` |
| `KeyframeRenderPhase` class | `cinema/phases/keyframe_render.py:31-109` |
| Skip condition: `approved_keyframe_take_id` | `cinema/phases/keyframe_render.py:95-97` |
| Partial failures don't fail keyframe phase | `cinema/phases/keyframe_render.py:105-108` |
| Cancellation polling (scene+shot boundaries) | `cinema/phases/keyframe_render.py:82-93` |
| `PerformanceCapturePhase` class | `cinema/phases/performance.py:19-89` |
| Skip condition: `approved_performance_take_id` | `cinema/phases/performance.py:63-64` |
| Skip condition: `performance_engine == "SKIP"` | `cinema/phases/performance.py:67-68` |
| Skip condition: no approved keyframe | `cinema/phases/performance.py:71-72` |
| `_get_storyboard_mode` function | `cinema/phases/motion_render.py:45-54` |
| `storyboard_mode` read path | `cinema/phases/motion_render.py:48-54` |
| `MotionRenderPhase._scene_keyframes` | `cinema/phases/motion_render.py:78-94` |
| `MotionRenderPhase._run_storyboard_scene` | `cinema/phases/motion_render.py:100-315` |
| Storyboard cost recorded once | `cinema/phases/motion_render.py:187-198` |
| Segment finalize fallback to per-shot retry | `cinema/phases/motion_render.py:293-313` |
| Storyboard eligibility: 2–6 unapproved shots | `cinema/phases/motion_render.py:359` |
| Per-shot fallback loop | `cinema/phases/motion_render.py:394-406` |
| Phase imports in cinema_pipeline | `cinema_pipeline.py:27-29` |
| `PipelineContext` construction before phases | `cinema_pipeline.py:978-982` |
| `KeyframeRenderPhase.run(ctx)` call + progress at 50% | `cinema_pipeline.py:994-999` |
| KEYFRAME_REVIEW gate | `cinema_pipeline.py:1004-1006` |
| `PerformanceCapturePhase.run(ctx)` call + progress at 62% | `cinema_pipeline.py:1024-1029` |
| PERFORMANCE_REVIEW gate + all-skipped auto-bypass | `cinema_pipeline.py:1034-1058` |
| `MotionRenderPhase.run(ctx)` call + progress at 80% | `cinema_pipeline.py:1071-1076` |
| REVIEW gate | `cinema_pipeline.py:1084` |
| `generate_keyframe_take` delegate → `_shot_ctrl` | `cinema_pipeline.py:235-236` |
| `generate_performance_take` delegate | `cinema_pipeline.py:256-257` |
| `generate_motion_take` delegate | `cinema_pipeline.py:259-260` |
| `_resolve_take_path` delegate | `cinema_pipeline.py:317-318` |
| `cost_tracker` property | `cinema_pipeline.py:150-151` |
| `state_snapshot` function | `cinema/services.py:61-97` |
| `checkpoint_info` function | `cinema/services.py:100-133` |
| `_project_gate_status` helper | `cinema/services.py:48-58` |
| `state_snapshot` used in web endpoint | `web_server.py:1976` |
| `checkpoint_info` used in web endpoint | `web_server.py:1520` |
| `cinema.services` import in web_server | `web_server.py:57` |
| Generic `CinemaPipeline` driver | `cinema/pipeline.py:80-114` |
| `PipelineRunResult` dataclass | `cinema/pipeline.py:57-77` |
| Generic driver imports `Phase`, `PhaseResult` | `cinema/pipeline.py:39` |
| `PipelineContext` dataclass + dict-compat layer | `cinema/context.py:48-143` |
| `get_project_setting` helper | `cinema/context.py:146-176` |
| `storyboard_mode` default `False` in web_server defaults | `web_server.py:343` |
| `_shot_ctrl` private access in storyboard path | `cinema/phases/motion_render.py:153,230` |
| `motion_description > prompt > camera` fallback | `cinema/phases/motion_render.py:135-139` |
| `headless` param on `CinemaPipeline` | `cinema_pipeline.py:49,68-72` |

---

## 4. review/gates/screening — Review / Gates / Auto-Approve / Screening / Checkpoints

*Subsystem key: `review-gates`*

### Purpose

This subsystem enforces five mandatory operator review gates that punctuate the pipeline (PLAN_REVIEW, KEYFRAME_REVIEW, PERFORMANCE_REVIEW, REVIEW, SCREENING). At each gate, an auto-approve heuristic pre-approves shots that meet configured quality thresholds, reducing manual effort; any shot that fails heuristics must be approved by a human operator via the web UI. In headless (non-interactive) runs, ungated shots raise a diagnosable error instead of polling forever. A JSON checkpoint persists mutable run state to disk after every scene so a crashed run can be resumed; a post-assembly SCREENING gate lets the operator watch the assembled cut, iterate individual shots, and trigger incremental re-assembly before signing off.

### Modules

| Path | Role | LOC (verified) |
|---|---|---|
| `cinema/review/controller.py` | ReviewController: gate wait logic, auto-approve integration, per-shot approval mutations, review-clip manifest | 700 |
| `cinema/auto_approve.py` | Veto-rule engine: per-gate rule builders, `check_gate`, `record_director_review_on_shots`, audit helpers | 719 |
| `cinema/screening.py` | Post-assembly SCREENING stage: feature flag, timeline manifest builder, `screening_approved` flag, `needs_reassembly` dirty tracking, cost estimate | 578 |
| `cinema/checkpoint.py` | CheckpointStore: atomic JSON checkpoint save/load/restore into RunState | 185 |
| `cinema/runstate.py` | RunState dataclass: shared mutable per-run state (all controllers share one instance) | 154 |

### Key functions & classes (the micro level)

**cinema/runstate.py**

- `RunState` (dataclass) — `cinema/runstate.py:60`. Fields: `shot_results`, `review_clips`, `scene_clips`, `scene_audio`, `scene_foley`, `foley_audio_paths`, `failed_shots`, `current_stage/scene_id/shot_id`, `headless: bool`, `completed_scene_indices`. Instantiated once per `CinemaPipeline.__init__`, passed by reference to all three controllers (`cinema_pipeline.py:91`). `headless=True` is set by the caller; all gate code reads it.
- `update_progress_pointer(stage, scene_id, shot_id)` — `cinema/runstate.py:143`. Atomically sets all three progress-pointer fields. Called by ShotController during generation; orchestrator sets fields directly for single-field cases.

**cinema/review/controller.py**

- `GateNotSatisfiedError` (RuntimeError subclass) — `cinema/review/controller.py:93`. Raised by `_wait_for_gate` when `runstate.headless=True` and auto-approve didn't clear the gate. Carries human-readable per-shot details from `_gate_block_details`.
- `ReviewControllerHost` (Protocol) — `cinema/review/controller.py:104`. Declares the three cross-controller methods the host (CinemaPipeline) must provide: `_refresh_project_snapshot`, `_find_take`, `_mutate_shot`, `resume`.
- `ReviewController.__init__` — `cinema/review/controller.py:144`. Takes `(core, lifecycle, host, runstate)`. Does not own any mutable state directly; all state is on the shared `RunState`.
- `_gate_satisfied(gate, project)` — `cinema/review/controller.py:224`. Pure predicate for the four review gates. PLAN_REVIEW: all shots have `plan_status=="approved"`. KEYFRAME_REVIEW: all shots have `approved_keyframe_take_id`. PERFORMANCE_REVIEW: all shots are SKIP or have `approved_performance_take_id`. REVIEW: all shots have `approved_final_take_id`.
- `_run_auto_approve_pass(gate)` — `cinema/review/controller.py:253`. Iterates all shots; calls `check_gate` per shot; mutates approved shots via `_host._mutate_shot`; appends audit entry to `shot["auto_approve_audit"]` in all cases; never raises (belt-and-suspenders). Gate→key map: `PLAN_REVIEW→"plan"`, `KEYFRAME_REVIEW→"image"`, `REVIEW→"final"`, `PERFORMANCE_REVIEW→"motion"` (only if `CINEMA_AUTO_APPROVE_MOTION=1`).
- `_wait_for_gate(gate, detail, percent)` — `cinema/review/controller.py:507`. The core gate block. Sets `runstate.current_stage`, emits progress, then calls `_run_auto_approve_pass`. If `runstate.headless`: checks gate once, raises `GateNotSatisfiedError` if unsatisfied. Otherwise: calls `lifecycle.wait_for_gate(gate, predicate)` which polls at 0.5s until predicate returns True or run is cancelled. Returns True (opened) or False (cancelled).
- `_gate_block_details(gate, project)` — `cinema/review/controller.py:561`. For headless error messages: per-shot reasons, surfacing `auto_approve_audit[-1].rule_names` or `director_review.decision` for PLAN_REVIEW.
- `_rebuild_review_clips(project)` — `cinema/review/controller.py:606`. Builds the in-memory manifest (shot_id→{scene_id, prompt, image path, video path, take_id, status}), writes to `runstate.review_clips`. Called after motion render + on resume.
- `approve_shot_plan(shot_id, approved, reason)` — `cinema/review/controller.py:633`. Human approval for PLAN gate. Mutates `shot["plan_status"]` = "approved"/"rejected" and `shot["plan_rejection_reason"]`.
- `approve_take(shot_id, take_id, approval_kind)` — `cinema/review/controller.py:647`. Human approval for keyframe/performance/final gates. Approval kinds: `"keyframe"` → sets `approved_keyframe_take_id`; `"performance"` → sets `approved_performance_take_id`; `"final"` → sets `approved_final_take_id` (+ `approved_motion_take_id` by walking `source_take_id` chain). Validates collection membership (keyframes cannot be approved as final).
- `proceed_to_assembly()` — `cinema/review/controller.py:688`. Called by `POST /resume`. Verifies REVIEW gate satisfied, emits REVIEW_COMPLETE progress, calls `host.resume()` to unblock the pipeline thread.

**cinema/auto_approve.py**

- `AutoApproveConfig` (dataclass) — `cinema/auto_approve.py:71`. Holds all thresholds. Populated from `project["global_settings"]["auto_approve"]` via `from_project(project)`. Defaults: `enabled=True`, `image_min_composite=0.97` (PuLID) / `0.78` (fallback), `motion_min_identity=0.85`, `motion_min_motion_score=0.7`, `final_min_lipsync=0.8`, `final_require_human_if_upstream_auto=True`.
- `VetoRule` (frozen dataclass) — `cinema/auto_approve.py:41`. `name: str`, `predicate(ctx→bool)`, `reason_template: str`. Context dict keys: `shot_state`, `project`, `takes`.
- `AutoApproveDecision` (dataclass) — `cinema/auto_approve.py:58`. `auto_approved: bool`, `vetoes: list[str]`, `rule_names: list[str]`, `deferred: bool` (True = eval-error deferral, not real veto).
- `record_director_review_on_shots(shots, review)` — `cinema/auto_approve.py:235`. **The writer** for `shot["director_review"]`. Called at `cinema_pipeline.py:959` immediately after `ChiefDirector.validate_shot_prompts`. Normalises MODIFIED→APPROVED (cycle-17 decision to auto-clear so headless runs don't dead-end). Stores raw verdict in `chief_director_verdict`. **Critical**: this function's absence was the root cause of the cycle-17 headless plan-review-gate stall.
- `_rules_for_plan(config)` — `cinema/auto_approve.py:203`. Two veto rules: `plan_decision_not_approved` (fires if `shot["director_review"]["decision"] != "APPROVED"`); `plan_has_violations` (fires if `director_review["violations"]` non-empty).
- `_rules_for_image(config)` — `cinema/auto_approve.py:280`. Three rules: `image_composite_below_threshold` (dynamic: uses `image_min_composite_fallback` when any take has fallback engine, else `image_min_composite`); `image_cascade_fallback` (fires if any take has `cascade_metadata.fallback=True`); `image_over_budget` (fires if `shot.spent_usd > multiplier × per_shot_budget`).
- `_rules_for_motion(config)` — `cinema/auto_approve.py:340`. Three rules: `motion_identity_below_threshold`, `motion_score_below_threshold` (uses `motion_fidelity` or `motion_score` from metadata), `motion_cascade_fallback`.
- `_rules_for_final(config)` — `cinema/auto_approve.py:384`. Two rules: `final_lipsync_below_threshold` (dialogue-aware: returns 1.0 for non-dialogue shots, 1.0 for `audio_embedded=True` takes, 0.0 for dialogue with no score and no audio_embedded); `final_upstream_was_auto_approved` (safety net: if `plan_auto_approved`, `image_auto_approved`, or `motion_auto_approved` is True on the shot, require human at final).
- `check_gate(gate, *, shot_state, project, takes, config)` — `cinema/auto_approve.py:625`. Public entry point. Returns `AutoApproveDecision`. All exceptions caught; eval-error sets `deferred=True`. Returns `auto_approved=False` if `config.enabled=False`.
- `pick_best_take_by_composite(takes)` — `cinema/auto_approve.py:520`. Returns take with highest `metadata.composite`; falls back to `takes[-1]` if none have a score. Used by controller's image approval mutation.
- `pick_best_take_for_final(candidates)` — `cinema/auto_approve.py:551`. Prefers non-fallback takes first; then picks by composite score. Used by controller's final approval mutation.
- `is_motion_gate_enabled()` — `cinema/auto_approve.py:611`. Reads `CINEMA_AUTO_APPROVE_MOTION` env var (case-insensitive `1|true|yes`). Off by default.
- `summarize_audit(shot_state)` — `cinema/auto_approve.py:736`. Aggregates `shot["auto_approve_audit"]` into a Session-12 PostRunSummary dict (auto_approved_gates, vetoed_gates, per_rule_fire_counts).

**cinema/screening.py**

- `_screening_stage_enabled(project=None)` — `cinema/screening.py:104`. Feature flag. Priority: (1) `project["global_settings"]["screening_stage_enabled"]` (lenient bool/int/str parsing); (2) `CINEMA_SCREENING_STAGE` env var (falsy: `0|false|no`); (3) default ON. Default ON as of v5.1+ flag-flip.
- `_build_timeline_manifest(project, *, verify_files=False)` — `cinema/screening.py:177`. Walks scenes/shots with `approved_final_take_id`; builds list of `{shot_id, scene_id, start_s, end_s, approved_take_id, take_count}`. Duration: `take.metadata.duration_s` > `scene.duration_seconds` > 5.0. With `verify_files=True` (used by the `/assemble/screen` endpoint): also checks `os.path.exists(take.path)` before including a shot, mirroring `_assemble_final`'s inclusion rule.
- `is_screening_approved(project)` — `cinema/screening.py:295`. Reads `project.get("screening_approved", False)`.
- `mark_screening_approved(project_id)` — `cinema/screening.py:307`. Lazy-imports `mutate_project`; runs `Project.model_validate` inside mutator (P1-3 Variant 1 shape); sets `project["screening_approved"] = True`. Raises `ValueError` if project not found.
- `get_needs_reassembly(project)` — `cinema/screening.py:353`. Returns `project["needs_reassembly"]` as a list; defensive against non-list values.
- `mark_shot_needs_reassembly(project_id, shot_id)` — `cinema/screening.py:371`. Idempotent add to `project["needs_reassembly"]`. Called by `ShotController.regenerate_with_intent` when an iterate fires during SCREENING.
- `clear_needs_reassembly(project_id, only_shots=None)` — `cinema/screening.py:421`. With `only_shots=None`: wipes entire list. With `only_shots` list: only removes those shot_ids, preserving any concurrently added entries (Lane V #8 I3 close).
- `estimate_reassembly_cost(project)` — `cinema/screening.py:518`. Heuristic: `cost_s ≈ shot_count × 0.5 + total_duration_s × 0.09`, floor 5s. Returns `{seconds, shot_count, total_source_duration_s, breakdown}`.

**cinema/checkpoint.py**

- `CheckpointStore.__init__(core, lifecycle, runstate)` — `cinema/checkpoint.py:53`. No host protocol (removed V1.1 #5); accesses RunState directly.
- `_save_checkpoint(completed_scene_idx=-1)` — `cinema/checkpoint.py:87`. Serialises RunState fields (`current_stage`, `scene_clips`, `scene_audio`, `scene_foley`, `foley_audio_paths`, `shot_results`, `failed_shots`, `completed_scene_indices`) to JSON. Atomic write via `tempfile.mkstemp` + `os.replace`. File: `{temp_dir}/pipeline_state.json`.
- `_load_checkpoint()` — `cinema/checkpoint.py:117`. Reads JSON; validates that referenced `shot_results` image/video paths still exist; marks lost paths with `status="lost"`.
- `_restore_from_checkpoint()` — `cinema/checkpoint.py:163`. Wholesale-assigns restored dicts to `runstate` fields. Emits RESUME progress if scenes were completed.
- `_clear_checkpoint()` — `cinema/checkpoint.py:136`. Removes the checkpoint file after successful pipeline completion.
- `has_checkpoint()` — `cinema/checkpoint.py:142`. Lightweight existence check.
- `resume_info()` — `cinema/checkpoint.py:146`. Returns `{resumable, completed_scenes, total_scenes, stage, shots_done, shots_failed}`.

### Data IN -> OUT

**IN (consumed):**
- `project.json` (full project dict with scenes/shots/takes, `global_settings.auto_approve`, `global_settings.screening_stage_enabled`, `global_settings.budget_limit_usd`)
- `shot["director_review"]` dict (written by `record_director_review_on_shots` from ChiefDirector output before PLAN_REVIEW gate)
- `shot["keyframe_takes"]`, `shot["motion_takes"]`, `shot["postprocess_variants"]`, `shot["performance_takes"]` (take arrays with `metadata.composite`, `metadata.identity_score`, `metadata.motion_fidelity`, `metadata.lipsync_score`, `metadata.audio_embedded`, `cascade_metadata.fallback`)
- `shot["spent_usd"]` (cost tracking for budget veto)
- Env vars: `CINEMA_AUTO_APPROVE_MOTION`, `CINEMA_SCREENING_STAGE`
- `{temp_dir}/pipeline_state.json` (checkpoint file on disk)
- HTTP request bodies (operator approvals via web endpoints)

**OUT (produced):**
- `shot["plan_status"]` = "approved"/"rejected"
- `shot["approved_keyframe_take_id"]`, `shot["approved_performance_take_id"]`, `shot["approved_motion_take_id"]`, `shot["approved_final_take_id"]`
- `shot["auto_approve_audit"]` list (per-gate audit entries)
- `shot["plan_auto_approved"]`, `shot["image_auto_approved"]`, `shot["motion_auto_approved"]`, `shot["final_auto_approved"]` bool flags
- `shot["director_review"]` dict (written by `record_director_review_on_shots`)
- `runstate.review_clips` (in-memory manifest for web UI)
- `project["screening_approved"]` bool (persisted)
- `project["needs_reassembly"]` list (persisted)
- `{temp_dir}/pipeline_state.json` (checkpoint)
- SSE progress events (stage, detail, percent)
- HTTP JSON responses for all operator endpoints

### Connects to (other subsystems)

- **cinema_pipeline.py (orchestrator)**: calls `_wait_for_gate` at five points; calls `record_director_review_on_shots` at `cinema_pipeline.py:959`; delegates approval HTTP calls to `ReviewController`; calls `_save_checkpoint` after each scene + before each gate; calls `_clear_checkpoint` at end; instantiates all three controllers. Implements `ReviewControllerHost` protocol.
- **cinema/lifecycle.py (ThreadedLifecycle)**: `_wait_for_gate` delegates to `lifecycle.wait_for_gate(name, predicate, poll_interval=0.5)` for the blocking poll; `api_screening_approve` calls `pipeline.lifecycle.signal_gate(SCREENING_STAGE_NAME)` to wake the blocking waiter promptly (`web_server.py:2289`).
- **domain/project_manager.py (`mutate_project`)**: all approval mutations use `_mutate_shot` which calls `mutate_project` under the per-project lock; `mark_screening_approved` and `mark_shot_needs_reassembly` call `mutate_project` directly with P1-3 Variant 1 inner validate.
- **llm/chief_director.py (ChiefDirector)**: produces the `review` dict consumed by `record_director_review_on_shots`; the verdict (`APPROVED`/`MODIFIED`/`REJECTED`) feeds the PLAN gate veto rule.
- **cinema/shots/controller.py (ShotController)**: `regenerate_with_intent` calls `mark_shot_needs_reassembly` during SCREENING; keyframe/motion scores flow into take `metadata` consumed by auto-approve rules.
- **web_server.py**: exposes all operator-facing endpoints (approve/reject plan, approve keyframe/performance/final, reject-auto-approve, checkpoint, resume, assemble/screen, screening/approve, assemble/re-assemble); reads `runstate.review_clips` for the review UI.

### User-facing surface & capability knobs

| Knob | Location | Default | Effect |
|---|---|---|---|
| `CINEMA_AUTO_APPROVE_MOTION` env var | env | off | Enables auto-approve at PERFORMANCE_REVIEW gate. Set to `1`/`true`/`yes`. |
| `CINEMA_SCREENING_STAGE` env var | env | ON | Set to `0`/`false`/`no` to skip SCREENING after assembly. |
| `project.global_settings.screening_stage_enabled` | project JSON | (not set = env wins) | Project-level override of `CINEMA_SCREENING_STAGE`; takes priority over env. |
| `project.global_settings.auto_approve.enabled` | project JSON | `true` | Master switch for all auto-approve gates. `false` forces all to manual. |
| `project.global_settings.auto_approve.plan_require_approved` | project JSON | `true` | If false, disables the `plan_decision_not_approved` veto (dangerous — allows REJECTED plans through). |
| `project.global_settings.auto_approve.plan_reject_on_violations` | project JSON | `true` | If false, ignores ChiefDirector violation list. |
| `project.global_settings.auto_approve.image_min_composite` | project JSON | `0.97` | PuLID composite score threshold for keyframe auto-approve. Lower = more permissive. |
| `project.global_settings.auto_approve.image_min_composite_fallback` | project JSON | `0.78` | Composite threshold when fallback engine was used. |
| `project.global_settings.auto_approve.image_veto_on_fallback` | project JSON | `true` | If false, allows cascade-fallback keyframes through auto-approve. |
| `project.global_settings.auto_approve.image_max_spent_multiplier` | project JSON | `1.5` | Veto if shot cost > 1.5× per-shot budget. Set to 0 to disable budget veto. |
| `project.global_settings.auto_approve.motion_min_identity` | project JSON | `0.85` | Identity score threshold for motion auto-approve (requires `CINEMA_AUTO_APPROVE_MOTION=1`). |
| `project.global_settings.auto_approve.motion_min_motion_score` | project JSON | `0.7` | Motion fidelity threshold. |
| `project.global_settings.auto_approve.final_min_lipsync` | project JSON | `0.8` | Lipsync score threshold for final take auto-approve. |
| `project.global_settings.auto_approve.final_require_human_if_upstream_auto` | project JSON | `true` | Safety net: if any prior gate auto-approved this shot, force human at final. Set to `false` for fully unattended runs (removes last human gate). |
| `CinemaPipeline(headless=True)` | Python API | `False` | Non-interactive mode: gates fail fast (GateNotSatisfiedError) instead of polling. For E2E/script use. |

Config is written to `project.json` via `PUT /api/projects/<pid>` with body `{"global_settings": {"auto_approve": {...}}}` (`web_server.py:506-507`).

**To maximise unattended quality:** lower composite and lipsync thresholds gradually (track `auto_approve_audit` veto rates), disable `final_require_human_if_upstream_auto` only after the pipeline is well-calibrated, enable motion gate with `CINEMA_AUTO_APPROVE_MOTION=1` once motion scores are stable.

### Control & data flow (how a run moves through this subsystem, step by step)

1. **`CinemaPipeline.__init__`** (`cinema_pipeline.py:46`): creates `RunState(headless=...)`, constructs `ReviewController(core, lifecycle, host, runstate)` and `CheckpointStore(core, lifecycle, runstate)`.

2. **`generate(resume=False)`** (`cinema_pipeline.py:942`): if `resume=True`, calls `_restore_from_checkpoint()` which reads `pipeline_state.json` and wholesale-assigns all RunState fields back.

3. **Per-scene loop**: ChiefDirector runs `validate_shot_prompts`; result is immediately passed to `record_director_review_on_shots(shots, review)` (`cinema_pipeline.py:959`), which writes `shot["director_review"] = {decision, violations, chief_director_verdict}` (MODIFIED is normalised to APPROVED). `_save_checkpoint()` called after each scene.

4. **PLAN_REVIEW gate** (`cinema_pipeline.py:964`): calls `_wait_for_gate("PLAN_REVIEW", ..., 25)` → sets `runstate.current_stage="PLAN_REVIEW"` → calls `_run_auto_approve_pass("PLAN_REVIEW")` → for each unapproved shot, calls `check_gate("plan", ...)` which evaluates `_rules_for_plan`: if `director_review.decision=="APPROVED"` and no violations → `auto_approved=True` → mutates `shot["plan_status"]="approved"`, `shot["plan_auto_approved"]=True`, appends audit entry. If headless: checks predicate once, raises `GateNotSatisfiedError` with per-shot reasons if not all approved. If web: `lifecycle.wait_for_gate` polls at 0.5s; operator uses `POST /api/projects/<pid>/shots/<shot_id>/plan/approve` to approve remaining shots (calls `approve_shot_plan` → `_mutate_shot`).

5. **KeyframeRenderPhase** runs; `_wait_for_gate("KEYFRAME_REVIEW", ..., 55)`: auto-approve evaluates `_rules_for_image` on each shot's `keyframe_takes`; if approved, writes `approved_keyframe_take_id` = id of take with highest composite score (via `pick_best_take_by_composite`).

6. **PerformanceCapturePhase** runs; **PERFORMANCE_REVIEW gate** skipped entirely if all shots have `performance_engine=="SKIP"` (`cinema_pipeline.py:1038-1058`); otherwise same pattern (motion gate requires `CINEMA_AUTO_APPROVE_MOTION=1`).

7. **MotionRenderPhase** runs; `_rebuild_review_clips(project)` builds in-memory manifest; `_save_checkpoint()`; **REVIEW gate** (`cinema_pipeline.py:333`): auto-approve evaluates `_rules_for_final` on `postprocess_variants + motion_takes`; if approved, writes `approved_final_take_id` (and `approved_motion_take_id`) via `pick_best_take_for_final` (prefers non-fallback, then highest composite). `final_require_human_if_upstream_auto` veto fires if any earlier gate was auto-approved.

8. **Assembly**: `assemble_approved_takes()` stitches approved takes into mp4.

9. **SCREENING gate** (`cinema_pipeline.py:774-805`): only if `_screening_stage_enabled()`. Pipeline emits progress at 95%; calls `lifecycle.wait_for_gate("SCREENING", predicate)` where predicate reads `is_screening_approved(project)`. During wait: operator hits `POST /api/projects/<pid>/assemble/screen` to get the timeline manifest; may iterate shots (ShotController calls `mark_shot_needs_reassembly`); may call `POST /api/projects/<pid>/assemble/re-assemble` to re-stitch dirty shots (calls `clear_needs_reassembly(only_shots=...)`); finally calls `POST /api/projects/<pid>/screening/approve` → `mark_screening_approved` → `lifecycle.signal_gate("SCREENING")` → predicate wakes and returns True.

10. **CLEANUP / COMPLETE**: `_clear_checkpoint()` removes the checkpoint file; pipeline completes.

### Gotchas, divergences & doc-drift

1. **The headless stall bug (FIXED cycle-17)**: Before `record_director_review_on_shots` was added, `_rules_for_plan`'s `plan_decision_not_approved` predicate always fired because `shot["director_review"]` was never written. Result: PLAN_REVIEW auto-approve always vetoed → headless run polled forever. Fix: `record_director_review_on_shots` now called at `cinema_pipeline.py:959` immediately after ChiefDirector. MODIFIED verdicts auto-cleared (cycle-17 user decision) so a director-corrected scene doesn't dead-end.

2. **`NullLifecycle` is NOT used by CinemaPipeline**: `lifecycle.py:70` docstring says explicitly it is NOT wired into `CinemaPipeline`. Using `NullLifecycle` in a headless run would silently open all gates (gates return True immediately), bypassing the fail-fast behaviour. Correct headless pattern: `CinemaPipeline(headless=True)` which uses `ThreadedLifecycle` but checks `runstate.headless` in `_wait_for_gate` to raise instead of poll.

3. **PERFORMANCE_REVIEW auto-approve is opt-in via env var**: without `CINEMA_AUTO_APPROVE_MOTION=1`, the motion gate map entry is omitted (`cinema/review/controller.py:280-282`) and the PERFORMANCE_REVIEW gate is always manual. The `_rules_for_motion` function exists and is used when enabled, but the gate is silently not included by default.

4. **`final_require_human_if_upstream_auto=True` default blocks fully unattended runs**: even with all other auto-approve rules satisfied, if plan or image was auto-approved, the final gate fires `final_upstream_was_auto_approved` and forces human review. This is by design (safety net) but is the most common footgun for unattended E2E runs. Must be set to `false` via `global_settings.auto_approve` to allow fully headless completion.

5. **`image_veto_on_fallback=True` default**: any keyframe that used a cascade fallback engine is vetoed by both the composite threshold rule (which applies the lower fallback bar) AND the `image_cascade_fallback` rule. Both rules fire independently. For projects where fallback is acceptable, set both `image_veto_on_fallback=false` and lower `image_min_composite_fallback`.

6. **`clear_needs_reassembly(only_shots=...)` race guard**: the `only_shots` parameter closes a race where shots iterated during a long re-assembly window would be silently cleared. Callers MUST pass the list of shots that were actually re-assembled (not all dirty shots), not None, to preserve concurrently dirtied shots.

7. **`_rebuild_review_clips` is in-memory only**: `runstate.review_clips` is rebuilt on each run start (from checkpoint or from scratch). It is NOT persisted in the checkpoint. Web endpoints that read `review_clips` work only while the pipeline is running. After process restart, the checkpoint restores other RunState fields but NOT `review_clips` — the separate call `_rebuild_review_clips(project)` at `cinema_pipeline.py:308` handles this on resume.

8. **`pick_best_take_by_composite` falls back to `takes[-1]`**: if no take carries a `metadata.composite` score (e.g. non-PuLID engines), it silently returns the last take. This can approve a non-optimal take when composite scores are absent. The audit entry will show the approval but the reason will be composite-based, which is misleading.

9. **Checkpoint file lives at `{temp_dir}/pipeline_state.json`**: if `temp_dir` changes between runs (e.g. different OS temp path), `has_checkpoint()` returns False and the run starts fresh. `temp_dir` is derived from the project directory path via `PipelineCore`.

10. **`summarize_audit` is pre-staged but not yet wired to any endpoint**: it is defined at `cinema/auto_approve.py:736` for "Session 12's PostRunSummary modal" but no web endpoint calls it in the current codebase (unverified as of the files read — no grep result in web_server.py for `summarize_audit`).

### Citations

- `cinema/runstate.py:59` — RunState dataclass definition
- `cinema/runstate.py:127` — `headless` field
- `cinema/runstate.py:140` — `update_progress_pointer`
- `cinema/review/controller.py:93` — `GateNotSatisfiedError`
- `cinema/review/controller.py:103` — `ReviewControllerHost` Protocol
- `cinema/review/controller.py:144` — `ReviewController.__init__`
- `cinema/review/controller.py:224` — `_gate_satisfied`
- `cinema/review/controller.py:253` — `_run_auto_approve_pass`
- `cinema/review/controller.py:275-282` — gate-to-key map + motion gate opt-in
- `cinema/review/controller.py:507` — `_wait_for_gate`
- `cinema/review/controller.py:531` — `runstate.current_stage = gate`
- `cinema/review/controller.py:546` — headless fail-fast branch
- `cinema/review/controller.py:559` — `lifecycle.wait_for_gate` (web path)
- `cinema/review/controller.py:561` — `_gate_block_details`
- `cinema/review/controller.py:606` — `_rebuild_review_clips`
- `cinema/review/controller.py:633` — `approve_shot_plan`
- `cinema/review/controller.py:647` — `approve_take`
- `cinema/review/controller.py:688` — `proceed_to_assembly`
- `cinema/auto_approve.py:41` — `VetoRule`
- `cinema/auto_approve.py:58` — `AutoApproveDecision` (incl. `deferred` field)
- `cinema/auto_approve.py:71` — `AutoApproveConfig` with all defaults
- `cinema/auto_approve.py:107` — `from_project` deserialisation
- `cinema/auto_approve.py:170` — `_rules_for_plan`
- `cinema/auto_approve.py:202` — `record_director_review_on_shots` (MODIFIED normalisation at line 234)
- `cinema/auto_approve.py:247` — `_rules_for_image` (dynamic fallback threshold at line 255-268)
- `cinema/auto_approve.py:307` — `_rules_for_motion`
- `cinema/auto_approve.py:351` — `_rules_for_final`
- `cinema/auto_approve.py:425` — `_best_take_lipsync` (dialogue-aware, audio_embedded handling, F1b fix)
- `cinema/auto_approve.py:477` — `pick_best_take_by_composite`
- `cinema/auto_approve.py:508` — `pick_best_take_for_final`
- `cinema/auto_approve.py:555` — `_any_upstream_gate_auto_approved`
- `cinema/auto_approve.py:568` — `is_motion_gate_enabled`
- `cinema/auto_approve.py:582` — `check_gate` (main entry point)
- `cinema/auto_approve.py:693` — `summarize_audit`
- `cinema/screening.py:65` — `SCREENING_STAGE_NAME`, `SCREENING_APPROVED_KEY`
- `cinema/screening.py:81` — `NEEDS_REASSEMBLY_KEY`
- `cinema/screening.py:84` — `_screening_stage_enabled` (lookup order: project > env > default ON)
- `cinema/screening.py:157` — `_build_timeline_manifest` (verify_files flag at line 248)
- `cinema/screening.py:275` — `is_screening_approved`
- `cinema/screening.py:287` — `mark_screening_approved` (P1-3 Variant 1, lazy import)
- `cinema/screening.py:333` — `get_needs_reassembly`
- `cinema/screening.py:351` — `mark_shot_needs_reassembly`
- `cinema/screening.py:401` — `clear_needs_reassembly` (`only_shots` race guard)
- `cinema/screening.py:498` — `estimate_reassembly_cost`
- `cinema/checkpoint.py:43` — `CheckpointStore`
- `cinema/checkpoint.py:87` — `_save_checkpoint` (atomic write via mkstemp+replace)
- `cinema/checkpoint.py:117` — `_load_checkpoint` (lost-file detection)
- `cinema/checkpoint.py:163` — `_restore_from_checkpoint`
- `cinema/lifecycle.py:70` — `NullLifecycle` (explicitly NOT wired into CinemaPipeline)
- `cinema/lifecycle.py:110` — `ThreadedLifecycle`
- `cinema/lifecycle.py:165` — `signal_gate`
- `cinema/lifecycle.py:182` — `wait_for_gate` (0.5s poll + event signal wake)
- `cinema_pipeline.py:46-91` — `CinemaPipeline.__init__` (`headless` param, RunState instantiation)
- `cinema_pipeline.py:855-857` — checkpoint resume + `_rebuild_review_clips`
- `cinema_pipeline.py:959` — `record_director_review_on_shots` call site
- `cinema_pipeline.py:964` — PLAN_REVIEW gate call
- `cinema_pipeline.py:1004` — KEYFRAME_REVIEW gate call
- `cinema_pipeline.py:1038-1058` — PERFORMANCE_REVIEW all-SKIP bypass
- `cinema_pipeline.py:1084` — REVIEW gate call
- `cinema_pipeline.py:774-805` — SCREENING gate (inside `assemble_approved_takes`)
- `web_server.py:86-98` — `_SCREENING_BYPASS_STAGES` set (SCREENING exempted from busy-fence)
- `web_server.py:1511` — `GET /api/projects/<pid>/checkpoint` → `checkpoint_info`
- `web_server.py:1574-1595` — `POST /api/projects/<pid>/shots/<shot_id>/plan/approve` and `/reject`
- `web_server.py:1624` — `POST .../keyframes/<take_id>/approve`
- `web_server.py:1635` — `POST .../performance/<take_id>/approve`
- `web_server.py:1672` — `POST .../final/<take_id>/approve`
- `web_server.py:1786` — `POST .../reject-auto-approve`
- `web_server.py:1955` — `POST /api/projects/<pid>/resume`
- `web_server.py:2127` — `POST /api/projects/<pid>/assemble/screen`
- `web_server.py:2210` — `POST /api/projects/<pid>/screening/approve` (signal_gate at line 2289)
- `web_server.py:504-507` — `PUT /api/projects/<pid>` patches `global_settings.auto_approve`
- `cinema/services.py:100` — `checkpoint_info` (standalone, no CinemaPipeline construction)

---

## 5. data-model/state — Domain Data Model & Persistence

*Subsystem key: `domain-state`*

### Purpose (2-4 sentences)
This subsystem defines the canonical in-memory schema and all on-disk persistence for cinema projects. Every pipeline stage reads and writes through it; it is the shared state that unifies the LLM planning phases, image generation, video generation, performance capture, audio assembly, and final assembly. The persistence model is JSON-on-disk under `domain/projects/<pid>/project.json`, protected by per-project `filelock` for concurrent access, with atomic writes via temp-file-then-`os.replace`. The data flows as plain Python dicts through most of the pipeline, with Pydantic v2 used only at load/save boundaries as a warn-only validation net.

### Modules

| Path | Role | LOC |
|---|---|---|
| `domain/models.py` | Pydantic v2 schema definitions — validation-only, not the live data type | 179 |
| `domain/project_manager.py` | Canonical home: factory functions, normalization, CRUD, persistence, shot-package I/O | 1214 |
| `project_manager.py` | Shim — `from domain.project_manager import *`; exists solely for legacy import compat | 9 |
| `domain/shot_types.py` | Canonical shot-type constants + alias normalizer (`normalize_shot_type`) | 51 |
| `domain/performance.py` | Pure routing logic: decides performance-capture engine per shot based on shot type + dialogue | 185 |

### Key functions & classes (THE MICRO LEVEL)

#### `domain/models.py`

**`CascadeMetadata`** (line 26) — Pydantic model embedded in `TakeRecord.cascade_metadata`; fields: `engine: str`, `score/threshold/fallback/attempts` optional. Holds the cascade-selection bookkeeping for a take.

**`DirectorialIntent`** (line 38) — S15 substrate. Fields: `prose: str` (required), optional `verb`, `params: dict`, `refs: List[dict]`, `target_stage: Literal["keyframe","performance","motion"]`. Embedded in `TakeRecord.intent`. Orthogonal to `source_take_id`; tracks directorial iteration provenance, not postprocess derivation.

**`TakeRecord`** (line 62) — a single generation attempt. Key fields: `id: str`, `kind: Literal["keyframe","motion","performance","postprocess"]`, `path: str`, `source_take_id: str`, `status: str`, `created_at: str` (ISO-8601 kept as str for JSON safety), `metadata: dict`, optional `cascade_metadata`, `parent_take_id`, `intent: DirectorialIntent`, `revised_prompt`. All models use `extra="allow"`.

**`Shot`** (line 82) — core pipeline unit. Key fields: `id`, `prompt`, `camera`, `visual_effect`, `target_api`, `scene_foley`, `characters_in_frame: List[str]`, `primary_character`, `action_context`, `generated_image/video`, `plan_status`, `plan_rejection_reason`, four take lists (`keyframe_takes`, `motion_takes`, `postprocess_variants`, `performance_takes`), four approval-ID fields (`approved_keyframe_take_id`, `approved_motion_take_id`, `approved_final_take_id`, `performance_take_id`). NOTE: `Shot` Pydantic model does NOT include `objects_in_frame`, `primary_object`, `optimizer_cache`, `approved_performance_take_id`, `performance_engine`, `driving_video_path`, `auto_approve_audit`, `final_auto_approved` — these live in the raw dict via `extra="allow"` and are scaffolded by `normalize_shot_schema` and `make_shot`.

**`Scene`** (line 118) — fields: `id`, `order: int`, `title`, `location_id`, `characters_present: List[str]`, `action`, `dialogue`, `mood`, `camera_direction`, `duration_seconds: float`, `num_shots: int`, `shots: List[Shot]`.

**`Character`** (line 137) — fields: `id`, `name`, `description`, `voice_id`, `reference_image`, `gender: str`. NOTE: Pydantic model `reference_image` is a single string; raw dict from `make_character` uses `reference_images: List[str]` (plural) plus `canonical_reference`, `ip_adapter_weight`, `physical_traits`, `embedding_cache` — all extra-allow.

**`Location`** (line 155) — fields: `id`, `name`, `description`, `reference_image`. Raw dict from `make_location` adds `reference_images`, `prompt_fragment`, `lighting`, `time_of_day`, `weather`, `seed`.

**`Project`** (line 166) — top-level. Pydantic fields: `id`, `name`, `characters: List[Character]`, `locations: List[Location]`, `scenes: List[Scene]`. Raw dict from `make_project` additionally has `objects: List`, `global_settings: dict`, `screening_approved: bool` (from `cinema/screening.py`), `needs_reassembly: list[str]` — all extra-allow.

---

#### `domain/project_manager.py`

**`ProjectLockError`** (line 30) — raised when `filelock.Timeout` fires; carries `project_id` and `timeout`.

**`MutationResult`** (line 42) — dataclass `(value: Any, save: bool = True)`. Return from a mutator callback to suppress save when nothing changed (avoids unnecessary disk I/O).

**`new_id()`** (line 128) — `uuid4().hex[:12]` — 12-char hex ID used for projects (bare), characters (`char_` prefix), locations (`loc_` prefix), scenes (`scene_` prefix), takes (`take_` prefix). Objects use `obj_` prefix.

**`make_take(kind, path, *, source_take_id, status, metadata)`** (line 139) — factory for take dicts. `kind` in `{"keyframe","motion","performance","postprocess"}`. Returns dict with `id=f"take_{new_id()}"`, timestamp, metadata.

**`make_character(name, description, reference_images, voice_id, ip_adapter_weight, gender)`** (line 158) — factory. `id=f"char_{new_id()}"`. Has `reference_images: List[str]` (not `reference_image`), `canonical_reference`, `embedding_cache`.

**`make_object(name, description, brand, reference_images, material_traits, surface_type, branding_constraints, scale_reference, texture_anchor, ip_adapter_weight)`** (line 180) — ProductObject factory. `id=f"obj_{new_id()}"`. No Pydantic model exists for this type — purely a raw-dict extra-allow field on Project.

**`make_location(name, description, reference_images, lighting, time_of_day, weather)`** (line 215) — factory. `id=f"loc_{new_id()}"`, adds `prompt_fragment`, `seed: random.randint(100000,999999)`.

**`make_scene(title, location_id, characters_present, action, dialogue, mood, camera_direction, duration_seconds)`** (line 236) — factory. `id=f"scene_{new_id()}"`, `order=0`.

**`make_shot(prompt, camera, visual_effect, target_api, scene_foley, characters_in_frame, primary_character, objects_in_frame, primary_object, shot_id)`** (line 262) — factory. `id = shot_id or f"shot_{new_id()}"`. Scaffolds ALL take lists as `[]`, `plan_status="pending_review"`, `optimizer_cache={}`, `performance_takes`, `approved_performance_take_id`, `performance_engine`, `driving_video_path`.

**`make_project(name)`** (line 309) — factory. Top-level keys: `id=new_id()`, `name`, `characters`, `locations`, `objects`, `scenes`, `global_settings` (see operator knobs below).

**`_normalize_take_list(takes, kind)`** (line 360) — deduplicates take IDs, enforces `kind`, fills missing `path/status/source_take_id/created_at/metadata`. Returns `(normalized_list, changed_bool)`.

**`normalize_shot_schema(shot, *, scene_id, shot_index, seen_ids)`** (line 405) — mutates shot in place. Enforces unique shot ID (collision → `shot_{scene_id}_{shot_index}`). Fills defaults. Migrates legacy `approved/True` to `plan_status="approved"`. Migrates legacy `generated_image/video` into additive take history. Migrates all approval-ID fields. Returns `changed: bool`.

**`normalize_project_schema(project)`** (line 540) — calls `normalize_shot_schema` on every shot. Re-numbers scene `order`. Strips legacy VBench keys (`vbench_overall_threshold`, `temporal_flicker_tolerance`, `regression_sensitivity`). Returns `changed: bool`.

**`create_project(name)`** (line 605) — calls `make_project`, creates subdirs (`characters/`, `locations/`, `exports/`, `temp/`, `shots/`), calls `save_project`. Returns raw dict.

**`_validate_project(project, context)`** (line 620) — `Project.model_validate(project)`. Warn-only by default; raises on `CINEMA_STRICT_SCHEMA=1`. Belt-and-suspenders catches non-ValidationError too.

**`save_project(project, timeout=10)`** (line 667) — validates, acquires per-project `filelock`, atomic write via `tempfile.mkstemp + os.replace`. Lock path: `projects/<pid>/project.lock`.

**`load_project(project_id, timeout=10)`** (line 679) — acquires lock, reads `project.json`, calls `normalize_project_schema` (auto-saves if changed), validates. Returns `Optional[dict]`.

**`mutate_project(project_id, mutator, timeout=10, snapshot=None)`** (line 691) — the canonical RMW primitive. Acquires lock → loads unlocked → normalizes → calls `mutator(latest_project)` → saves if `MutationResult.save` or normalized. `snapshot` param: if provided, updates the caller's dict reference in-place after mutation via `_sync_project_snapshot`. Returns `mutator`'s value (or `MutationResult.value`).

**`delete_project(project_id, timeout=10)`** (line 728) — acquires lock then `shutil.rmtree` the project dir.

**`list_projects()`** (line 738) — lists all project dirs, loads each, sorts by `project.json` mtime DESC (newest first). Returns `[{"id": ..., "name": ...}]`.

**Entity helpers**: `add_character/remove_character/get_character` (lines 779-843), `add_object/remove_object/get_object` (lines 846-898), `add_location/remove_location/get_location` (lines 901-960), `add_scene/update_scene/remove_scene/reorder_scenes` (lines 963-1063). All entity mutators follow P1-3 pattern: outer `Project.model_validate(project)` boundary validate + inner mutator-scope validate under lock.

**Shot-package I/O**: `ensure_shot_package(pid, shot_id)` (line 1078) — creates `projects/<pid>/shots/<shot_id>/inputs/` and `outputs/`. `save_shot_spec/save_shot_output/save_shot_metrics/get_shot_package/list_shot_packages` (lines 1094-1214) — per-shot filesystem sidecar management. NOT locked — intended for single-writer phases.

---

#### `domain/shot_types.py`

**`normalize_shot_type(raw)`** (line 34) — lowercase + dealias. Input `"close-up"/"closeup"/"ecu"` → `"close_up"`. Unknown values pass through lowercased.

**`FACE_READABLE_SHOTS`** (line 47) — `frozenset({"close_up","portrait","medium"})`. Used by `domain/performance.py` for engine routing.

**Constants** (lines 16-21): `SHOT_TYPE_CLOSE="close_up"`, `SHOT_TYPE_PORTRAIT="portrait"`, `SHOT_TYPE_MEDIUM="medium"`, `SHOT_TYPE_WIDE="wide"`, `SHOT_TYPE_LANDSCAPE="landscape"`, `SHOT_TYPE_ACTION="action"`.

---

#### `domain/performance.py`

**`should_capture(shot, scene=None)`** (line 72) — pure gate. False if no characters, or landscape, or wide-no-dialogue. `scene` param reserved/unused.

**`route_performance_engine(shot, scene)`** (line 103) — returns one of `ENGINE_ACT_ONE`, `ENGINE_LIVE_PORTRAIT`, `ENGINE_VIGGLE`, `ENGINE_SKIP`. Decision: SKIP (no chars/wide) → ACT_ONE (dialogue + face-readable, unless `performance_budget_mode="budget"` → LIVE_PORTRAIT) → VIGGLE (action, no dialogue) → ACT_ONE (any remaining dialogue) → SKIP.

**`driving_video_source(shot)`** (line 145) — returns `"upload"/"tts_auto"/"none"`. "upload" when `shot.driving_video_path` is set; "tts_auto" when engine≠SKIP and has dialogue; "none" otherwise.

**`precondition_error(engine, audio_path, driving_video_path)`** (line 163) — pre-allocation guard. ACT_ONE requires `audio_path`; LIVE_PORTRAIT/VIGGLE require `driving_video_path`. Returns error string or None.

**`shot_needs_driving_video(shot)`** (line 94) — True when engine is LIVE_PORTRAIT or VIGGLE.

### Data IN -> OUT

**IN:** `name: str` (project creation), or `project_id: str` (load), or raw `project dict` + mutator callback (mutation). External inputs: disk JSON at `domain/projects/<pid>/project.json`.

**OUT:** raw Python `dict` representing the project (ALL pipeline stages operate on this dict, not on typed Pydantic instances). Side effects: writes `project.json` atomically, creates shot-package sidecar files (`shot.json`, `outputs/keyframe.png`, `outputs/video.mp4`, `outputs/metrics.json`). `list_projects()` returns `[{"id", "name"}]` sorted by recency.

### Connects to (which OTHER subsystems it touches, and HOW)

| Subsystem | How |
|---|---|
| `web_server.py` | Direct import of shim `project_manager` (lines 40-42); calls `create_project`, `load_project`, `mutate_project`, `delete_project`, `list_projects`, `MutationResult`, `ProjectLockError` on nearly every HTTP endpoint |
| `cinema_pipeline.py` | Imports via shim (line 17): `load_project`, `mutate_project`; refreshes project state mid-run (line 426); mutates plan/phase state (line 887) |
| `cinema/core.py` | `from domain.project_manager import load_project, get_project_dir` (line 50); reads `budget_limit_usd` from `global_settings` |
| `cinema/services.py` | `from domain.project_manager import load_project, get_project_dir` (line 34) |
| `cinema/shots/controller.py` | `from project_manager import MutationResult, mutate_project, make_take` (line 86); uses `mutate_project` for shot-state RMW; reads `prompt_optimizer_enabled`, `identity_strictness` from `global_settings` |
| `cinema/review/controller.py` | `from project_manager import MutationResult, mutate_project` (line 71) |
| `cinema/screening.py` | `from project_manager import MutationResult, mutate_project` (lines 308, 378, 434); writes `screening_approved` and `needs_reassembly` top-level keys on project dict |
| `cinema/auto_approve.py` | Reads `AutoApproveConfig` from `project.global_settings.auto_approve`; `record_director_review_on_shots` writes `shot["director_review"]`; `_rules_for_plan` reads it |
| `cinema/phases/motion_render.py` | `from domain.project_manager import make_take` (lazy, line 119) |
| `domain/performance.py` | Consumes shot dict fields directly; imports `domain.shot_types` |
| `workflow_selector.py` | Called by `domain/performance._shot_type` as fallback for `classify_shot_type` (lazy import, line 51); reads shot dict |
| `cleanup.py` | Imports `get_project_dir`, `list_projects` via shim |
| `llm/chief_director.py` | Reads `creative_llm` from `project.global_settings` (line 103) |
| `llm/ensemble.py` | Reads `quality_judge_llm` from `global_settings` (line 126) |
| `quality_max.py` | Reads `max_quality_parallel_workers`, `identity_strictness` (lines 137, 767) |
| `face_validator_gate.py` | Reads `identity_strictness` from project settings (line 133) |

### User-facing surface & capability knobs

All under `project.global_settings` (set via UI or API; read via `project["global_settings"]`):

| Knob | Default | Effect | Where consumed |
|---|---|---|---|
| `aspect_ratio` | `"16:9"` | Output video aspect | pipeline phases |
| `music_mood` | `"suspense"` | Music selection | audio phase |
| `master_seed` | random 6-digit | Reproducibility anchor | various |
| `budget_limit_usd` | `0` (unlimited) | Spend cap; `0` = no cap | `cinema/core.py:99`, `auto_approve.py:543` |
| `identity_strictness` | `0.60` | Face-similarity threshold for PuLID/identity gates | `face_validator_gate.py:185`, `cinema/shots/controller.py:504`, `quality_max.py:767` |
| `creative_llm` | `"auto"` | LLM model for direction/writing (e.g., `"claude-opus"`) | `llm/chief_director.py:114`, `llm/director.py:242` |
| `quality_judge_llm` | `"auto"` | LLM for quality evaluation | `llm/ensemble.py:126` |
| `competitive_generation` | `True` | Enables multi-take competition per shot | pipeline |
| `adaptive_pulid` | `True` | Adapts PuLID weight per shot type | `identity/__init__.py` |
| `coherence_check_enabled` | `True` | Cross-shot coherence gate | pipeline |
| `color_drift_sensitivity` | `0.3` | Threshold for color-drift detection | pipeline |
| `prompt_optimizer_enabled` | `True` | LLM-based shot-prompt rewrite before generation; caches to `shot["optimizer_cache"]` | `cinema/shots/controller.py:391` |
| `max_quality_parallel_workers` | `1` | Parallel best-of workers (up to 4) | `quality_max.py:631` |
| `auto_approve` | `AutoApproveConfig().to_dict()` | Per-gate auto-approve veto rules | `cinema/auto_approve.py` |
| `api_engines` | absent (opt-in) | Per-engine config (storyboard mode, duration, face consistency, etc.) | `cinema/phases/motion_render.py`, `phase_c_ffmpeg.py` |
| `dialogue_mode_enabled` | (from real project.json) | Enables dialogue track in audio phase | audio phases |
| `cascade_retry_limit` | (from real project.json) | Max retries in cascade fallback | pipeline |

**Environment variable:** `CINEMA_STRICT_SCHEMA=1` — elevates schema validation from warn to raise on `save_project`/`load_project`. Off by default.

**Per-shot operator knobs:** `performance_budget_mode="budget"` on a shot dict → routes engine to `LIVE_PORTRAIT` instead of `ACT_ONE`; `driving_video_path` on shot → Mode A (operator-uploaded driving video for performance capture).

**To maximize quality/capability:**
- Set `identity_strictness` higher (e.g., `0.80`) for stricter face fidelity gates
- Set `prompt_optimizer_enabled: True` (default) — LLM rewrites prompts for cinematographic precision
- Set `max_quality_parallel_workers: 4` for N=8 best-of parallel generation
- Set `competitive_generation: True` (default) for multi-take competition
- Set `budget_limit_usd: 0` (default) to remove spend cap

### Control & data flow (how a run moves through this subsystem, step by step)

1. **Project creation:** `web_server.py` calls `create_project(name)` → `make_project` builds raw dict → subdirs created → `save_project` writes `domain/projects/<pid>/project.json` atomically.

2. **Phase load:** Any pipeline entry point calls `load_project(pid)` → acquires `filelock` → reads JSON → `normalize_project_schema` (auto-saves on any migration) → `_validate_project` (warn-only) → returns raw `dict`.

3. **Shot-level mutation:** Phase code calls `mutate_project(pid, mutator)` → lock acquired → `_load_project_unlocked` reads fresh JSON → `normalize_project_schema` → `mutator(latest_project)` mutates in-place → `_save_project_unlocked` (atomic) → lock released → `_sync_project_snapshot` updates caller's reference.

4. **Take tracking:** After generation, phase calls `make_take(kind, path)` → appends to `shot["keyframe_takes"]` / `shot["motion_takes"]` / etc. → `mutate_project` persists.

5. **Shot ID assignment:** New shots from `make_shot` get `shot_{new_id()}` (12-hex). On `normalize_shot_schema`, collision or missing ID → `shot_{scene_id}_{shot_index}` (deterministic from scene ID + position). Real disk observation confirms scheme: `shot_scene_8617803ff3cf_0`.

6. **Shot packages:** `ensure_shot_package(pid, shot_id)` creates `projects/<pid>/shots/<shot_id>/inputs/outputs/`. `save_shot_spec/output/metrics` writes sidecar files. These are separate from the take-list entries in `project.json`.

7. **Screening state:** `cinema/screening.py` writes `project["screening_approved"]=True` and `project["needs_reassembly"]=[shot_ids]` directly on the project dict top-level via `mutate_project`. Not typed in Pydantic model; uses `extra="allow"`.

8. **Auto-approve:** `record_director_review_on_shots(shots, review)` writes `shot["director_review"]={"decision","violations"}` on each shot. `auto_approve._rules_for_plan` reads this field to decide if plan gate can self-approve.

### Gotchas, divergences & doc-drift

1. **`objects` not in Pydantic model.** `Project` Pydantic model (line 166) has no `objects` field — it's extra-allow. `make_project` and `make_object` scaffold it as `project["objects"]=[]`. `remove_object` uses `o["id"]` dict-style access (not typed iteration). Callers must use `.get("objects", [])` defensively.

2. **`Character.reference_image` (singular) vs `make_character` `reference_images` (plural).** Pydantic model has `reference_image: str = ""` (line 143); `make_character` produces `reference_images: List[str]` (line 167) + `canonical_reference`. This is the raw-dict vs typed model divergence; extra-allow swallows it silently.

3. **`Shot` Pydantic model missing several live fields.** `approved_performance_take_id`, `performance_engine`, `driving_video_path`, `objects_in_frame`, `primary_object`, `optimizer_cache`, `auto_approve_audit`, `final_auto_approved`, `director_review` all exist on real shot dicts but not in the `Shot` model. Pydantic validation will warn if strict mode enabled; extra-allow absorbs in default mode.

4. **`shot_id` collision hazard across projects.** Shot IDs follow `shot_{scene_id}_{shot_index}` on normalization. Scene IDs are `scene_{new_id()}` (12-hex). Two projects with identically-structured scenes COULD get matching shot IDs — this is the F1 CRITICAL from cycle-6/S13 that required pid-scoping on all HTTP endpoints. The shot ID is NOT globally unique; always pair with `project_id`.

5. **`screening_approved` and `needs_reassembly` live outside the Pydantic model.** Written directly to project dict top-level from `cinema/screening.py`. No schema enforcement. Real project.json confirmed: `"screening_approved"` key present at top level.

6. **`project_manager.py` (top-level) is a pure shim.** Canonical home is `domain/project_manager.py`. New code should import from `domain.project_manager`. Legacy callers (`web_server.py`, `cinema_pipeline.py`, `cinema/review/controller.py`, `cinema/screening.py`, `cinema/shots/controller.py`) still use the shim. Both are functionally identical.

7. **`save_project` inside the lock body must use `_save_project_unlocked`.** External callers that already hold a `project_lock()` context must use the unlocked variant to avoid deadlock. The public `save_project` acquires its own lock — nested calls will deadlock.

8. **`list_projects()` scans and loads all projects.** At large project counts (~2000), this is ~200-500ms. Not paginated. Landing-page fetch may be slow under heavy use.

9. **`PROJECTS_DIR` is anchored to `domain/` package directory.** `os.path.dirname(os.path.abspath(__file__))` with `/projects` suffix = `domain/projects/`. Verified on disk.

10. **`workflow_selector.classify_shot_type` import in `domain/performance.py` is lazy and fallible.** The `_shot_type` function (line 51) tries `from workflow_selector import classify_shot_type` in a bare `except Exception: return ""` — silent failure if `workflow_selector` is unavailable.

11. **`auto_approve_audit` accumulates across gates.** Each gate (`image_auto_approved`, `video_auto_approved`, `plan_auto_approved`) appends to `shot["auto_approve_audit"]` list and sets `shot[f"{gate}_auto_approved"]`. The field is not normalized by `normalize_shot_schema` — it grows unbounded with each re-approval cycle.

12. **`global_settings.api_engines` intentionally NOT scaffolded in `make_project`.** Operator-opt-in: merged only on UI settings-save from `web_server.py`'s `api_engine_defaults` catalog. All readers must safe-default its absence.

### Citations

- `domain/models.py:26` — `CascadeMetadata`
- `domain/models.py:38` — `DirectorialIntent`
- `domain/models.py:62` — `TakeRecord`
- `domain/models.py:82` — `Shot`
- `domain/models.py:118` — `Scene`
- `domain/models.py:137` — `Character`
- `domain/models.py:155` — `Location`
- `domain/models.py:166` — `Project`
- `domain/project_manager.py:27` — `PROJECTS_DIR` anchored to `domain/projects/`
- `domain/project_manager.py:30` — `ProjectLockError`
- `domain/project_manager.py:42` — `MutationResult`
- `domain/project_manager.py:69` — `_acquire_project_lock` (filelock, 10s timeout)
- `domain/project_manager.py:87` — `_save_project_unlocked` (atomic via `mkstemp + os.replace`)
- `domain/project_manager.py:102` — `_sync_project_snapshot`
- `domain/project_manager.py:110` — `project_lock` public context manager
- `domain/project_manager.py:128` — `new_id()` → `uuid4().hex[:12]`
- `domain/project_manager.py:139` — `make_take`
- `domain/project_manager.py:158` — `make_character` (reference_images plural)
- `domain/project_manager.py:180` — `make_object`
- `domain/project_manager.py:215` — `make_location`
- `domain/project_manager.py:236` — `make_scene`
- `domain/project_manager.py:262` — `make_shot` (objects_in_frame, optimizer_cache, performance fields)
- `domain/project_manager.py:309` — `make_project` (global_settings defaults)
- `domain/project_manager.py:338` — `prompt_optimizer_enabled: True` (F-B.2 closure note)
- `domain/project_manager.py:343` — `max_quality_parallel_workers: 1`
- `domain/project_manager.py:360` — `_normalize_take_list`
- `domain/project_manager.py:405` — `normalize_shot_schema` (ID collision → `shot_{scene_id}_{shot_index}`, line 418)
- `domain/project_manager.py:487` — legacy `generated_image` migration into `keyframe_takes`
- `domain/project_manager.py:540` — `normalize_project_schema` (VBench key stripping, line 565)
- `domain/project_manager.py:605` — `create_project` (subdirs: characters/, locations/, exports/, temp/, shots/)
- `domain/project_manager.py:620` — `_validate_project` (warn-only; `CINEMA_STRICT_SCHEMA` env var)
- `domain/project_manager.py:667` — `save_project`
- `domain/project_manager.py:679` — `load_project`
- `domain/project_manager.py:691` — `mutate_project`
- `domain/project_manager.py:738` — `list_projects` (mtime-sorted newest-first)
- `domain/project_manager.py:779-1063` — entity helpers (add/remove/get for character, object, location, scene)
- `domain/project_manager.py:1078` — `ensure_shot_package` (inputs/outputs subdirs)
- `domain/project_manager.py:1094-1214` — shot-package sidecar I/O
- `domain/shot_types.py:16-21` — constants
- `domain/shot_types.py:26-31` — `_ALIASES` table
- `domain/shot_types.py:34` — `normalize_shot_type`
- `domain/shot_types.py:47` — `FACE_READABLE_SHOTS = frozenset({"close_up","portrait","medium"})`
- `domain/performance.py:29` — imports from `domain.shot_types`
- `domain/performance.py:45` — `_shot_type` (lazy fallback to `workflow_selector.classify_shot_type`)
- `domain/performance.py:72` — `should_capture`
- `domain/performance.py:94` — `shot_needs_driving_video`
- `domain/performance.py:103` — `route_performance_engine` (decision matrix)
- `domain/performance.py:145` — `driving_video_source` (Mode A/B/C)
- `domain/performance.py:163` — `precondition_error`
- `domain/project_manager.py:9` — shim: `from domain.project_manager import *`
- `cinema/screening.py:66` — `SCREENING_APPROVED_KEY = "screening_approved"`
- `cinema/screening.py:81` — `NEEDS_REASSEMBLY_KEY = "needs_reassembly"`
- `cinema/auto_approve.py:202` — `record_director_review_on_shots` writes `shot["director_review"]`
- `web_server.py:40-42` — imports via shim
- `cinema_pipeline.py:17` — imports via shim

---

## 6. creative-LLM — Creative LLM / Direction Layer

*Subsystem key: `llm-brains`*

### Purpose

The creative LLM layer is the AI intelligence stack that converts operator intent and raw script fragments into precise, machine-executable shot specifications, enforces structural and identity hard-constraints pre-generation, translates operator iteration instructions into revised prompts post-generation, and orchestrates multi-provider LLM competition with judge-based winner selection. It is the "brain" layer that sits above image/video generation: nothing reaches a diffusion model or video API without passing through at least one of these modules. The subsystem has no persistent state of its own — it reads project dicts and writes back to shots in-place or via return values.

---

### Modules

| Path | One-line role | Verified LOC |
|---|---|---|
| `llm/chief_director.py` | Metacognitive overseer: validates shot prompts pre-gen (HC1–HC8) and diagnoses post-gen failures; sole writer of `director_review` on shots | 501 |
| `llm/director.py` | Permissive creative iteration translator: converts `DirectorialIntent` into `revised_prompt` + `params_delta` + `anchor_refs` for take regeneration | 432 |
| `llm/ensemble.py` | Multi-LLM parallel generation + judge-pick: Anthropic/OpenAI/Gemini providers, `build_anthropic_system_blocks` caching helper | 480 |
| `llm/prompt_optimizer.py` | UI-to-pipeline prompt translator: converts freeform operator text into a structured shot spec (image_prompt, video_prompt, purpose, APIs, camera, lighting, etc.) | 507 |
| `llm/style_director.py` | Per-project global style rules generator: produces cinematography, color grading, lighting, photorealism rules used by every scene | 193 |
| `llm/negative_prompts.py` | Failure-reason → negative-prompt phrase lookup table; keyed off `identity/types.FailureReason.value` | 49 |

---

### Key functions & classes (micro level)

#### `llm/chief_director.py`

**`ChiefDirector.__init__(self, project: dict)`** — `chief_director.py:52`
Stores project dict, initializes `diagnostic_log: List[Dict]`, calls `_init_client()`.

**`ChiefDirector._init_client()`** — `chief_director.py:57`
Tries Anthropic first (`settings.anthropic_api_key`), falls back to OpenAI. Sets `self.provider` to `"anthropic"` / `"openai"` / `None`. Returns client or None.

**`ChiefDirector._call_llm(system_prompt, user_prompt)`** — `chief_director.py:85`
Dispatches to Anthropic (`claude-sonnet-4-6` default, `max_tokens=4096`, uses `build_anthropic_system_blocks` for prompt caching) or OpenAI (`gpt-4o` default, `response_format={"type": "json_object"}`). Honors `project.global_settings.creative_llm` override but only if the model prefix matches the active provider (e.g., `claude-*` for Anthropic, `gpt-*`/`o1-*`/`o3-*`/`o4-*` for OpenAI); cross-family override is silently ignored with a log line.

**`ChiefDirector.SYSTEM_PROMPT`** — `chief_director.py:217`
Embedded class-level string constant. Contains HC1–HC8 hard constraints, the output schema (`APPROVED`/`REJECTED`/`MODIFIED` + violations + modifications + quality_score), tripwires T1–T9, quality upgrade rules, and the mutation strategy guide. Appends `PIPELINE_CONTEXT` (loaded from `config/prompts/pipeline_context.md`).

**`ChiefDirector.validate_shot_prompts(shots, scene)`** — `chief_director.py:296`
Primary pre-generation gate. Serializes shots to JSON, calls `_call_llm`. Implements a ≤1-retry loop for `json.JSONDecodeError` (first attempt fails → sends correction appended to user prompt → retries; second failure falls through to parse-fallback). Falls back to `{"decision": "APPROVED", "violations": [], "shots": shots}` on None client or parse failure (fail-safe-for-throughput). Applies in-place modifications to `shots[idx][field]` when `decision == "MODIFIED"`. Appends to `self.diagnostic_log`. Returns `{"decision", "violations", "shots"}`.

**`ChiefDirector.evaluate_generation_quality(image_path, reference_path, identity_result, identity_score, shot_prompt, scene_context, coherence_result)`** — `chief_director.py:406`
Post-generation evaluator. Implements a 2×2 decision matrix: (identity_passed × coherent) → ACCEPT; (fail × coherent) → identity_only mutation; (pass × incoherent) → style_only mutation; (fail × incoherent) → aggressive mutation. Calls a separate LLM (diagnosis system prompt, different from SYSTEM_PROMPT). Looks up `primary_reason_value` from the first failing character's `failure_reason` and appends the phrase from `get_negative_prompt_for_failure()` to the LLM's `prompt_mutation`. Appends to `diagnostic_log`. Returns `{"decision", "diagnosis", "prompt_mutation", "mutation_level", "mutation_focus"}`. **Note: no call sites found in the current codebase outside this file** — the method exists but is not wired into the active pipeline (verified by grep returning only the definition line). *(SUPERSEDED by T6, 2026-06-06: now wired via `diagnose_clip(deep=True)` at `cinema/shots/controller.py:1836` — `10a0eb4`.)*

**`ChiefDirector.get_diagnostic_summary()`** — `chief_director.py:653`
Returns multi-line string of all entries in `diagnostic_log`.

**`_strip_json_fences(raw)`** — `chief_director.py:27`
Strips ` ```json … ``` ` wrappers LLMs emit. Local copy (3rd copy total; others in `ensemble.py:18` and `prompt_optimizer.py:341`). Dedup tracked as P2/P3 follow-up (`ensemble.py:25`).

---

#### `llm/director.py`

**`CinemaDirector.__init__(self, project)`** — `director.py:204`
Stores project, calls `_init_client()`, sets `self._log_root = Path("data/intent_log")`.

**`CinemaDirector._init_client()`** — `director.py:209`
Same Anthropic-first, OpenAI-fallback pattern as ChiefDirector. Sets `self.provider`.

**`CinemaDirector._call_llm(user_prompt)`** — `director.py:230`
Anthropic: `claude-sonnet-4-6`, `max_tokens=2048`, uses `build_anthropic_system_blocks(SYSTEM_PROMPT)`. OpenAI: `gpt-4o`, `response_format={"type": "json_object"}`. Same `creative_llm` override logic. Returns raw text or `""`.

**`CinemaDirector.translate_intent(intent, take_context, scene_context)`** — `director.py:275`
Main entry point. Accepts `DirectorialIntent` Pydantic model or dict. Runs S18 verb DSL: extracts `intent.verb` + `intent.params`, builds a `verb_prefix` block (injected as user-prompt prefix, not system-prompt appendix, so the system block stays stable for caching). Falls back to freeform if verb is None or unknown. Calls `_call_llm`, parses JSON, returns `{"revised_prompt", "params_delta", "anchor_refs"}`. On LLM unavailable or parse failure, returns fallback using `intent.prose` or `take_context["prompt"]`. Calls `_log_intent_call` on all paths.

**`CinemaDirector._log_intent_call(...)`** — `director.py:353`
Writes a JSONL entry to `data/intent_log/{project_id}/{timestamp}.jsonl`. Non-fatal on failure. Designed for cycle-9+ verb DSL design (S18) data collection.

**`_build_verb_prefix(verb, params, scene_context)`** — `director.py:98`
Returns XML-delimited verb guidance block for `tighten_framing` (degree → percentage: subtle=10%, moderate=25%, strong=40%), `match_shot` (ref_shot_id lookup in `scene_context["approved_shots"]`; degrades gracefully if ref not found), `shift_emotion` (direction: soften/harden × target: subtle/strong). Returns `""` for unknown verbs.

**`KNOWN_VERBS`** — `director.py:95`
`frozenset({"tighten_framing", "match_shot", "shift_emotion"})`. Unknown verbs degrade to freeform with log line; no Pydantic `Literal` on `intent.verb` by design (future verbs land without schema migration).

**`intent_translator(intent, take_context, scene_context, *, project)`** — `director.py:418`
Module-level functional wrapper around `CinemaDirector.translate_intent`. Called by `cinema/shots/controller.py:1430`. Tests patch this symbol.

**`SYSTEM_PROMPT`** (module-level constant) — `director.py:47`
Defines CinemaDirector as PERMISSIVE (operator intent overrides HC firewalls). Output schema: `revised_prompt` + `params_delta` + `anchor_refs` + `reasoning`. Includes `params_delta` key guidance by `target_stage` (keyframe/performance/motion).

---

#### `llm/ensemble.py`

**`build_anthropic_system_blocks(text)`** — `ensemble.py:40`
Returns `[{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]`. Used by ChiefDirector, CinemaDirector, and ensemble's own Anthropic calls to activate Anthropic prompt caching. Callers must pass stable strings (no per-call interpolation) for cache hits.

**`LLMEnsemble.__init__(self, settings)`** — `ensemble.py:96`
Eagerly instantiates Anthropic + OpenAI clients. Gemini client is optional (only if `GEMINI_API_KEY` or `GOOGLE_API_KEY` configured). Reads `settings["competitive_generation"]` (bool, default True) and `settings["quality_judge_llm"]` (maps `"claude-opus"` → `"claude-opus-4-20250918"`, `"gpt-4o"` → `"gpt-4o"`, `"gemini-pro"` → `"gemini-2.5-pro"`).

**`LLMEnsemble.competitive_generate(task_type, system_prompt, user_prompt, models, judge_model, json_mode, tool_schema)`** — `ensemble.py:139`
Core public method. Dispatches all models in parallel via `ThreadPoolExecutor(max_workers=len(models))`. Preserves original model ordering after `as_completed`. Calls `_judge`. Returns `EnsembleResult(winner_index, winner_content, scores, candidates, models_used, judge_model, reasoning)`.

Default model rosters (`_DEFAULT_MODELS`, `ensemble.py:80`):
- `"script"`: `["claude-sonnet-4-6", "gpt-4o"]`
- `"decompose"`: `["gpt-4o", "claude-sonnet-4-6"]`
- `"default"`: `["claude-sonnet-4-6", "gpt-4o"]`
- Default judge: `"claude-sonnet-4-6"`

**`LLMEnsemble._generate_single(model, system_prompt, user_prompt, json_mode, tool_schema)`** — `ensemble.py:224`
Routes by model prefix: `claude*` → Anthropic, `gpt*`/`o4*` → OpenAI, `gemini*` → Gemini, else → OpenAI-compatible. Returns `(model, output)` or `(model, None)` on exception.

**`LLMEnsemble._generate_anthropic(...)`** — `ensemble.py:259`
Uses `build_anthropic_system_blocks`. Extracts `tool_use` blocks when `tool_schema` given. Logs cache hit/creation token counts. Returns `(model, text)`.

**`LLMEnsemble._generate_gemini(...)`** — `ensemble.py:325`
Uses `google-genai` SDK (`genai.Client.models.generate_content`). Supports `json_mode` via `response_mime_type="application/json"`. Raises `RuntimeError` if Gemini client not configured.

**`LLMEnsemble._judge(candidates, models, system_prompt, judge_model)`** — `ensemble.py:357`
Filters None candidates, auto-wins single valid candidate. Builds judging prompt (candidates truncated to 6000 chars each). Calls judge via 3-branch `_call_judge` nested helper (Claude/Gemini/OpenAI). ≤1-retry loop on `json.JSONDecodeError`. Broad `except Exception` fallback to first-valid candidate (intentionally preserved from Lane V CRITICAL finding). Returns `(winner_index, scores, reasoning)`.

**`EnsembleResult`** — `ensemble.py:65`
Dataclass: `winner_index, winner_content, scores, reasoning, candidates, models_used, judge_model`.

---

#### `llm/prompt_optimizer.py`

**`optimize_shot_prompt(user_input, characters, location, global_settings, scene_context, has_dialogue, objects, primary_subject, intent_notes, ensemble)`** — `prompt_optimizer.py:355`
Main entry. Builds structured user prompt with CHARACTER/OBJECTS/LOCATION/MOOD/PALETTE/LANGUAGE context. Calls `ensemble.competitive_generate(task_type="decompose", ...)`. Parses winner JSON. Falls back to `_fallback_optimize()` on any exception. Calls `_coerce_to_valid_keys()` before returning.

**`batch_optimize_scene(scene, characters, location, global_settings, ensemble)`** — `prompt_optimizer.py:473`
Iterates over `scene["shots"]`, builds per-shot context, calls `optimize_shot_prompt` for each, returns `[{"shot_id", "spec"}, ...]`. Filters characters to those in `shot["characters_in_frame"]` when that field is present.

**`_fallback_optimize(...)`** — `prompt_optimizer.py:201`
Deterministic LLM-free path. Classifies purpose via `_heuristic_purpose_with_objects`. Generates product-photography prompts for `product_hero`/`product_in_scene`/`product_reveal_motion` purposes; cinematic prompts otherwise. Uses `API_REGISTRY` (from `domain/scene_decomposer`) to check HIDREAM_I1 live status before recommending it.

**`_coerce_to_valid_keys(spec, has_chars, has_dialogue)`** — `prompt_optimizer.py:316`
Sanitizes LLM output: replaces invalid `purpose` (against `PURPOSE_TAGS` whitelist), `shot_type` (against `_VALID_SHOT_TYPES`), `suggested_image_api` (against `API_REGISTRY`), `suggested_video_api`, `suggested_lipsync`. Fills missing string fields with `""`.

**`_OPTIMIZER_SYSTEM_PROMPT`** — `prompt_optimizer.py:67`
158-line constant. Defines 9 guidelines: cinematography language, purpose→API recommendation matrix, negative constraint targets, identity anchor discipline, shot_type geometry, film-prompt prose style, minimum-enrichment rule, English-language enforcement (regardless of project dialogue language), product-shot photography guidelines.

**`_heuristic_purpose_with_objects(shot_type, has_chars, has_dialogue, has_objects, primary_subject)`** — `prompt_optimizer.py:37`
Extended purpose classifier handling `product_hero`, `product_in_scene`, `product_reveal_motion` purposes in addition to the character-shot taxonomy.

---

#### `llm/style_director.py`

**`generate_style_rules(project_name, mood, color_palette, music_mood, aspect_ratio, reference_films, use_web_research)`** — `style_director.py:12`
OpenAI-only (no Anthropic option; uses `settings.openai_api_key`; falls back to `_default_style_rules` if key absent). Always calls `research_cinematography(mood, ...)` from `research_engine` for mood-specific grounding. When `use_web_research=True` and `reference_films` provided, also calls `_research_aesthetic()` (Tavily search). Calls `web_research.run_with_tools(client, "gpt-4o", ..., max_tool_rounds=3, response_format={"type": "json_object"})`. Returns dict with keys: `director_vision`, `cinematography_rules`, `color_grading_palette`, `lighting_rules`, `sound_design`, `photorealism_rules`, `composition_rules`.

**`_default_style_rules(mood, color_palette, music_mood)`** — `style_director.py:127`
Hardcoded fallback keyed on mood: `melancholic`, `tense`, `hopeful`, `dark`, `cinematic`. `photorealism_rules` hardcoded as: `"Visible skin pores with subsurface scattering, shallow depth of field f/1.4-2.8 with circular bokeh, natural film grain ISO 400, micro-detail in fabric weave and material texture, volumetric atmospheric lighting, no AI artifacts, no smooth plastic skin, no over-saturated colors"`.

**`style_rules_to_prompt_suffix(style_rules)`** — `style_director.py:187`
Concatenates `color_grading_palette`, `lighting_rules`, `photorealism_rules`, `composition_rules` into a period-delimited string. Called by `cinema/shots/controller.py:333` and prepended to every shot prompt.

**`_to_str(val)`** — `style_director.py:176`
Safely coerces dict/list/other → string (GPT-4o sometimes returns structured objects for fields that should be strings).

---

#### `llm/negative_prompts.py`

**`NEGATIVE_PROMPT_BY_FAILURE_REASON`** — `negative_prompts.py:27`
Dict mapping `FailureReason.value` strings to English negative-prompt phrases. Keys: `no_face_detected`, `low_confidence_detection`, `small_face_region`, `face_angle_extreme`, `wrong_person`, `poor_lighting`, `occlusion`. `multiple_faces_ambiguous` intentionally omitted (enum exists, validator never emits it). `passed` not mapped (success sentinel).

**`get_negative_prompt_for_failure(reason: Optional[str])`** — `negative_prompts.py:41`
Returns phrase or `""` on None/unknown. Called from `ChiefDirector.evaluate_generation_quality` and `build_remediation_advisory`. *(SUPERSEDED by T6, 2026-06-06: `build_remediation_advisory` also calls this and is now wired in `generate_keyframe_take` + `diagnose_clip` — `8d18e57`.)*

---

### Data IN -> OUT

**IN:**
- `project` dict (with `global_settings`: `music_mood`, `color_palette`, `style_rules`, `creative_llm`, `quality_judge_llm`, `competitive_generation`, `language`)
- Shot dicts: `prompt`, `camera`, `target_api`, `characters_in_frame`, `dialogue`
- Scene dicts: `title`, `action`, `location_id`, `characters_present`, `shots`
- `DirectorialIntent` (Pydantic): `prose`, `verb`, `params`, `refs`, `target_stage`
- Identity validation results (`IdentityValidationResult`, `FailureReason.value`) and coherence results
- Operator freeform text (shot intent, mood description, reference films)

**OUT:**
- `validate_shot_prompts` → `{"decision": "APPROVED"|"REJECTED"|"MODIFIED", "violations": [...], "shots": [...]}`; shot dicts modified in-place on MODIFIED
- `evaluate_generation_quality` → `{"decision": "ACCEPT"|"RETRY"|"ACCEPT_LENIENT"|"FAIL", "diagnosis", "prompt_mutation", "mutation_level", "mutation_focus"}` (currently unconnected — no call sites) *(SUPERSEDED by T6, 2026-06-06: now wired via `diagnose_clip(deep=True)` — `10a0eb4`.)*
- `translate_intent` → `{"revised_prompt", "params_delta", "anchor_refs"}`; JSONL log written to `data/intent_log/{pid}/`
- `optimize_shot_prompt` → full shot spec dict (13 fields: `image_prompt`, `video_prompt`, `purpose`, `shot_type`, `suggested_image_api`, `suggested_video_api`, `suggested_lipsync`, `negative_constraints`, `identity_anchor`, `camera`, `lighting`, `color_palette`, `reasoning`)
- `generate_style_rules` → 7-key style dict written to `project.global_settings.style_rules`
- `style_rules_to_prompt_suffix` → period-delimited string appended to image prompts
- `competitive_generate` → `EnsembleResult`

---

### Connects to (other subsystems)

| Connection | How |
|---|---|
| `cinema/core.py:PipelineServices` | Instantiates `ChiefDirector(project)` and `LLMEnsemble(settings)` at `cinema/core.py:112,114`; stored as `services.director` and `services.ensemble` |
| `cinema_pipeline.py` | Calls `services.director.validate_shot_prompts()` at line ~936; calls `record_director_review_on_shots()` at ~959; calls `generate_style_rules()` at ~863 |
| `cinema/auto_approve.py` | Reads `shot["director_review"]["chief_director_verdict"]` and `shot["director_review"]["decision"]` in plan-gate logic (`auto_approve.py:180,243`); `record_director_review_on_shots` writes these fields |
| `cinema/shots/controller.py` | Calls `optimize_shot_prompt()` at line ~416; calls `style_rules_to_prompt_suffix()` at ~333; calls `intent_translator()` at ~1471 |
| `domain/scene_decomposer.py` | Imports `LLMEnsemble` at `domain/scene_decomposer.py:11`; calls `competitive_generate()` at ~749 for competitive scene decomposition |
| `domain/models.py` | `DirectorialIntent` Pydantic model at `models.py:38` consumed by `CinemaDirector.translate_intent` |
| `identity/validator.py` | Produces `IdentityValidationResult` + `FailureReason.value` strings consumed by `evaluate_generation_quality` and `negative_prompts` |
| `pipeline_context.py` | `PIPELINE_CONTEXT` string (loaded from `config/prompts/pipeline_context.md`) appended to `ChiefDirector.SYSTEM_PROMPT` and `style_director`'s system prompt |
| `research_engine.py` / `web_research.py` | Called by `style_director.generate_style_rules` for Tavily-grounded cinematography research |
| `web_server.py` | Imports `generate_style_rules` at line 54; exposes `/api/projects/<pid>/generate-style-rules` at line 1399 |

---

### User-facing surface & capability knobs

All knobs live in `project.global_settings` (set via `PUT /api/projects/<pid>` → `global_settings` update, or via the web UI settings panel):

| Knob | Key in `global_settings` | Default | Effect |
|---|---|---|---|
| **Creative LLM model** | `creative_llm` | `None` (auto) | Overrides default model in `ChiefDirector._call_llm` and `CinemaDirector._call_llm`. Must match active provider prefix. UI options: `"auto"`, `"claude-sonnet"`, `"gpt-4o"` (`web_server.py:364`) |
| **Quality judge model** | `quality_judge_llm` | `"auto"` | Overrides judge model in `LLMEnsemble.__init__`. Mapped: `"claude-opus"` → `claude-opus-4-20250918`, `"gpt-4o"` → `gpt-4o`, `"gemini-pro"` → `gemini-2.5-pro` (`ensemble.py:129`) |
| **Competitive generation** | `competitive_generation` | `True` | Read by `LLMEnsemble.__init__` (stored as `self.competitive_enabled` but not currently enforced as a gate — `competitive_generate` always runs regardless) |
| **Music/mood** | `music_mood` | `"cinematic"` | Feeds `generate_style_rules` mood + research query; also feeds `_fallback_optimize` prompt text |
| **Color palette** | `color_palette` | `""` | Feeds `generate_style_rules` and `_fallback_optimize` |
| **Language** | `language` | `"English"` | Passed to `optimize_shot_prompt` user prompt; guideline 8 of `_OPTIMIZER_SYSTEM_PROMPT` forces image/video prompts to remain English regardless |
| **Style rules** | `style_rules` | `{}` | Pre-computed style rules dict. If non-empty at pipeline start, `generate_style_rules` is skipped entirely (`cinema_pipeline.py:861`) |

**To maximize quality/capability:**
1. Set `quality_judge_llm = "claude-opus"` to use Claude Opus 4 as judge (highest-capability judge; costs more).
2. Leave `creative_llm = "auto"` (defaults to `claude-sonnet-4-6` which is the native provider for ChiefDirector and CinemaDirector).
3. Pre-provide `style_rules` with hand-crafted values to bypass GPT-4o's style generation (avoids OpenAI dependency).
4. Set `ANTHROPIC_API_KEY` (primary), `OPENAI_API_KEY` (fallback), and optionally `GEMINI_API_KEY` for Gemini judge option.
5. Set `TAVILY_API_KEY` for research-grounded style generation.
6. Use verb DSL (`tighten_framing`/`match_shot`/`shift_emotion` via `DirectorialIntent.verb`) instead of freeform prose for deterministic iteration.

---

### Control & data flow

**Phase A — Style generation (once per pipeline run):**
1. `cinema_pipeline.py` reads `settings.get("style_rules", {})`. If empty: calls `generate_style_rules(project_name, mood, color_palette, music_mood, aspect_ratio)` → OpenAI GPT-4o with Tavily-grounded research → 7-key dict → persisted to `project.global_settings.style_rules`.
2. `style_rules_to_prompt_suffix(style_rules)` converts the dict to a string suffix appended to every image generation prompt downstream.

**Phase B — Shot prompt optimization (per shot, during decomposition):**
1. `cinema/shots/controller.py:~400` calls `optimize_shot_prompt(user_input, characters, location, global_settings, scene_context, ...)`.
2. `optimize_shot_prompt` builds `LLMEnsemble` (or accepts pre-built), calls `ensemble.competitive_generate(task_type="decompose", ...)`.
3. Ensemble dispatches `gpt-4o` + `claude-sonnet-4-6` in parallel (ThreadPoolExecutor). Each generates a JSON shot spec.
4. Judge (default: `claude-sonnet-4-6`) scores candidates 0–10 on creativity/accuracy/completeness/style; returns winner index.
5. `_coerce_to_valid_keys()` sanitizes enum fields. Returns structured spec.
6. Fallback: if LLM unavailable, `_fallback_optimize()` runs heuristics deterministically.

**Phase C — ChiefDirector pre-generation validation (per scene):**
1. `cinema_pipeline.py:936` calls `self.director.validate_shot_prompts(shots, scene)`.
2. ChiefDirector serializes shots, calls `_call_llm(SYSTEM_PROMPT, user_prompt)` → Claude Sonnet 4 (Anthropic primary, OpenAI fallback).
3. LLM evaluates against HC1–HC8 tripwires, returns JSON with `decision` + `violations` + `modifications`.
4. ≤1-retry on `JSONDecodeError`. Parse-fallback to APPROVED on persistent failure.
5. If MODIFIED: modifications applied in-place to `shots[idx][field]`.
6. If REJECTED: `cinema_pipeline.py` re-runs `decompose_scene` with stricter constraints.
7. `record_director_review_on_shots(shots, review)` writes `shot["director_review"]["decision"]` and `shot["director_review"]["chief_director_verdict"]` for each shot. MODIFIED normalizes to gate-decision APPROVED (cycle-17 user decision, `138d7c7`).
8. `update_scene_shots(project, scene_id, shots)` persists to disk.
9. Pipeline waits at `PLAN_REVIEW` gate; auto-approve reads `chief_director_verdict` from each shot.

**Phase D — CinemaDirector iteration (per take, when operator iterates):**
1. Operator submits iteration via web API with `DirectorialIntent(prose, verb, params, target_stage)`.
2. `cinema/shots/controller.py:1471` calls `intent_translator(intent, take_context, scene_context, project=project)`.
3. `CinemaDirector.translate_intent`: extracts verb, builds verb_prefix block, appends to JSON payload.
4. Calls `_call_llm(user_prompt)` → Claude Sonnet 4. Returns `{"revised_prompt", "params_delta", "anchor_refs"}`.
5. JSONL log written to `data/intent_log/{pid}/`. Fallback to `intent.prose` on failure.

**Phase E — Post-generation quality evaluation (currently unconnected):**
`evaluate_generation_quality()` exists at `chief_director.py:406` with full 2×2 mutation matrix logic and negative-prompt enrichment but has **zero call sites** in the current codebase (grep confirmed). The method is implemented but not invoked by any active pipeline path. *(SUPERSEDED by T6, 2026-06-06: now wired via `diagnose_clip(deep=True)` at `cinema/shots/controller.py:1836` — `10a0eb4`. Line ref :318/:336 also stale → :406.)*

---

### Gotchas, divergences & doc-drift

1. **`evaluate_generation_quality` is dead code in the active pipeline.** No call sites found anywhere outside `llm/chief_director.py:406`. The 2×2 mutation matrix, negative-prompt enrichment, and diagnostic logging it implements are fully functional but unreachable from any pipeline path. The old worktree files (`.claude/worktrees/*/chief_director.py:345`) had a different `diagnosis_system` format (f-string template, not the embedded constant), confirming this was substantially rewritten but the calling code was never wired. *(SUPERSEDED by T6, 2026-06-06: now wired via `diagnose_clip(deep=True)` — `10a0eb4`.)*

2. **`style_director` is OpenAI-only** — no Anthropic path, no fallback to Anthropic. If only `ANTHROPIC_API_KEY` is set (no `OPENAI_API_KEY`), `generate_style_rules` falls through to `_default_style_rules` immediately (`style_director.py:127-130`). This is asymmetric with ChiefDirector and CinemaDirector which prefer Anthropic.

3. **`_strip_json_fences` is duplicated 3 times** — `prompt_optimizer.py:341`, `chief_director.py:27`, `ensemble.py:18`. Tracked as P2/P3 debt (`ensemble.py:25`); no shared utility yet.

4. **`competitive_enabled` flag is stored but not enforced** — `LLMEnsemble.__init__` sets `self.competitive_enabled` from `settings["competitive_generation"]` (`ensemble.py:126`) but `competitive_generate()` never checks it. All calls always run full multi-model competition.

5. **`creative_llm` override is family-checked but not provider-switching** — setting `creative_llm = "claude-sonnet-4-5"` when the active provider is OpenAI (e.g., Anthropic key absent) silently uses the OpenAI default instead of switching providers (`chief_director.py:116-125`). Cross-family override is silently ignored with a log line only.

6. **`evaluate_generation_quality` negative-prompt enrichment uses only the FIRST failing character** — `primary_reason_value` captures the first non-"passed" failure reason from the character loop (`chief_director.py:514-515`). If multiple characters fail with different reasons, only the first drives the negative prompt addition.

7. **`batch_optimize_scene` does not pass `objects` or `intent_notes`** — `prompt_optimizer.py:492-507` calls `optimize_shot_prompt` without the `objects` and `intent_notes` parameters. Product shot classification and per-shot creative direction are unavailable via the batch path.

8. **Dual-module pairs: top-level are all 9-line re-export shims, domain/ are canonical.** Verified: `character_manager.py` (9 LOC shim / 527 LOC canonical), `continuity_engine.py` (9/627), `scene_decomposer.py` (9/912), `project_manager.py` (9/1214), `dialogue_writer.py` (9/184), `location_manager.py` (9/214). All shims use `from domain.X import *`. New code should import from `domain.*` directly.

9. **`research_engine.py` and `web_research.py` exist at repo root** — both imports in `style_director` are guarded by `try/except Exception: pass`, so missing these modules silently skips research enhancement (not an error). Confirmed both files present via `ls`.

10. **Worktree drift** — worktrees `strange-goldberg`, `goofy-bhabha`, `jolly-cerf`, `hopeful-blackwell` contain stale `chief_director.py` at the repo root with an older `diagnosis_system` f-string format and imports `from chief_director import ChiefDirector` (top-level, not `llm.`). These are historical worktrees, not the active working tree; ignore for production purposes.

11. **Gemini judge client is optional-constructed in `__init__` but raises at call time if missing.** If `gemini-pro` is selected as `quality_judge_llm` but no Gemini API key is configured, `LLMEnsemble.__init__` sets `self.gemini_client = None`; the `_generate_gemini` helper raises `RuntimeError` at call time (`ensemble.py:336`). This will crash judging and fall back to the broad-except path (first-valid candidate).

---

### Citations

| Claim | File:line |
|---|---|
| ChiefDirector prefers Anthropic, falls back to OpenAI | `llm/chief_director.py:57-80` |
| Default model: `claude-sonnet-4-6` | `llm/chief_director.py:117` |
| HC1–HC8 hard constraints + tripwires T1–T9 | `llm/chief_director.py:225-281` |
| APPROVED/MODIFIED/REJECTED output schema | `llm/chief_director.py:248-256` |
| ≤1 retry on JSONDecodeError in validate_shot_prompts | `llm/chief_director.py:335-345` |
| Parse-fallback APPROVED (fail-safe-for-throughput) | `llm/chief_director.py:348-357` |
| In-place modification of shots on MODIFIED | `llm/chief_director.py:387-393` |
| 2×2 mutation matrix in evaluate_generation_quality | `llm/chief_director.py:454-461` |
| Negative prompt appended to prompt_mutation | `llm/chief_director.py:613-617` |
| evaluate_generation_quality has no callers | grep result (only `chief_director.py:406` returned) *(SUPERSEDED by T6, 2026-06-06: caller now at `cinema/shots/controller.py:1928` — `10a0eb4`.)*|
| creative_llm override with family-match guard | `llm/chief_director.py:110-125`, `llm/director.py:237-261` |
| CinemaDirector is permissive (overrides HC) | `llm/director.py:18-20`, `director.py:47-60` |
| S18 verb DSL: KNOWN_VERBS + _build_verb_prefix | `llm/director.py:95-187` |
| Verb prefix injected as user-prompt prefix (not system) | `llm/director.py:27-31`, `director.py:313` |
| Per-call JSONL log at data/intent_log/{pid}/ | `llm/director.py:24-26`, `director.py:353-386` |
| intent_translator functional wrapper | `llm/director.py:418-432` |
| Called by cinema/shots/controller.py | `cinema/shots/controller.py:1430,1471` |
| build_anthropic_system_blocks cache_control block | `llm/ensemble.py:40-57` |
| Default model rosters _DEFAULT_MODELS | `llm/ensemble.py:80-86` |
| ThreadPoolExecutor parallel generation | `llm/ensemble.py:178-191` |
| Judge: ≤1-retry + broad-except fallback | `llm/ensemble.py:436-480` |
| Gemini client optional; raises RuntimeError if missing | `llm/ensemble.py:113-119`, `ensemble.py:336` |
| competitive_enabled stored but not enforced | `llm/ensemble.py:125-126`; `competitive_generate` has no check |
| quality_judge_llm model map | `llm/ensemble.py:128-133` |
| optimize_shot_prompt signature + objects/intent_notes params | `llm/prompt_optimizer.py:355-389` |
| _OPTIMIZER_SYSTEM_PROMPT 9 guidelines | `llm/prompt_optimizer.py:67-158` |
| English-only image/video prompt rule (guideline 8) | `llm/prompt_optimizer.py:128-133` |
| batch_optimize_scene missing objects/intent_notes | `llm/prompt_optimizer.py:473-507` |
| _coerce_to_valid_keys enum sanitization | `llm/prompt_optimizer.py:316-338` |
| _fallback_optimize product-shot path | `llm/prompt_optimizer.py:201-313` |
| style_director OpenAI-only | `llm/style_director.py:36-42` |
| _default_style_rules photorealism_rules constant | `llm/style_director.py:138` |
| style_rules_to_prompt_suffix | `llm/style_director.py:182-193` |
| style_director called from cinema_pipeline.py | `cinema_pipeline.py:20,863` |
| generate_style_rules skipped if style_rules pre-set | `cinema_pipeline.py:861-863` |
| NEGATIVE_PROMPT_BY_FAILURE_REASON dict | `llm/negative_prompts.py:27-38` |
| get_negative_prompt_for_failure | `llm/negative_prompts.py:41-49` |
| multiple_faces_ambiguous intentionally omitted | `llm/negative_prompts.py:36-38` |
| ChiefDirector instantiated in PipelineServices | `cinema/core.py:112` |
| LLMEnsemble instantiated in PipelineServices | `cinema/core.py:114` |
| validate_shot_prompts called in cinema_pipeline | `cinema_pipeline.py:936` |
| record_director_review_on_shots called after validation | `cinema_pipeline.py:959` |
| MODIFIED normalizes to APPROVED (cycle-17 decision) | `cinema/auto_approve.py:219-235`; commit `138d7c7` |
| chief_director_verdict persisted per shot | `cinema/auto_approve.py:243` |
| LLMEnsemble used in domain/scene_decomposer | `domain/scene_decomposer.py:11,749` |
| Dual-module shims all 9-LOC re-exports | root `scene_decomposer.py`, `character_manager.py` (→ `domain/`), etc. |
| PIPELINE_CONTEXT from config/prompts/pipeline_context.md | `pipeline_context.py:14-16` |
| research_engine.py and web_research.py exist | `ls` result |
| _strip_json_fences 3rd copy in ensemble | `llm/ensemble.py:25-27` |

---

## 7. script->scenes/dialogue/research — Script → Scenes → Shots (+ Dialogue & Research Augmentation)

*Subsystem key: `script-scenes`*

### Purpose

This subsystem converts user-defined scenes (title, action, mood, dialogue, duration, characters, location) into concrete, API-routed shot records ready for image/video generation. The scene decomposer sends a structured prompt to GPT-4o (or a GPT-4o vs Claude ensemble) that enforces five hard constraints (identity firewall, schema lock, location lock, lighting lock, face-direction). A parallel dialogue writer generates per-character spoken lines from the scene action, and a research engine injects live web context (cinematography references, location images, music references) into both decomposition and dialogue prompts to ground output in real-world craft.

### Modules

| Path | Role | Verified LOC |
|---|---|---|
| `scene_decomposer.py` (top-level) | Backward-compat shim — `from domain.scene_decomposer import *` | 9 |
| `domain/scene_decomposer.py` | **Canonical** scene decomposer — API registry, purpose routing, `decompose_scene`, `competitive_decompose_scene`, `_fallback_decompose`, `update_scene_shots`, cost estimator | 912 |
| `dialogue_writer.py` (top-level) | Backward-compat shim — `from domain.dialogue_writer import *` | 9 |
| `domain/dialogue_writer.py` | **Canonical** dialogue writer — `generate_dialogue`, `format_dialogue_for_voiceover`, `dialogue_to_narration_text` | 184 |
| `domain/language_defaults.py` | Per-language pipeline defaults (TTS, lipsync priority, voice IDs); `get_language_defaults`, `merge_language_defaults_into_settings` | 206 |
| `research_engine.py` | Tavily + Firecrawl wrappers: `research_cinematography`, `research_location_visual`, `research_music_reference`, `research_trending_topics`, `scrape_technique_reference` | 160 |
| `web_research.py` | Shared tool-calling loop: `run_with_tools` (GPT-4o + Tavily/Firecrawl tool loop), `search_web`, `scrape_url`, `TOOLS_SCHEMA`, `handle_tool_call` | 221 |

**Canonical vs shim:** Top-level `scene_decomposer.py` and `dialogue_writer.py` are pure re-export shims (each 9 lines, one `import *`). All logic lives in `domain/`. The shims preserve legacy import surface used by `cinema_pipeline.py:18-19`, `web_server.py:50,53`, and tests.

### Key Functions & Classes

**`_build_cinedecompose_system_prompt`** — `domain/scene_decomposer.py:326`
Single-source-of-truth builder for the CineDecompose v1.0 system prompt. Accepts: `target_shots`, `char_descriptions`, `loc_description`, `loc_lighting`, `loc_time`, `loc_weather`, `style_ctx`, `research_ctx`, `global_settings`. Returns a multi-section f-string embedding HC1-HC5 hard constraints, four tripwires, `OUTPUT_SCHEMA` with five mandatory section labels (`[SHOT][SCENE][ACTION][OUTFIT][QUALITY]`), an example, `SCENE_DATA`, `ADDITIONAL_RULES` (including R5: "Do NOT default to AUTO — pick the best API for each shot"), and `PIPELINE_CONTEXT`. Extracted at Bundle-B 2.3 to eliminate the prior ~150 LOC duplication between `decompose_scene` and `competitive_decompose_scene`.

**`decompose_scene`** — `domain/scene_decomposer.py:429`
Params: `scene: dict`, `characters: List[dict]`, `location: dict`, `global_settings: dict`, `style_rules: Optional[dict]`.
Returns: `List[dict]` — shot records from `make_shot()`.
Flow: builds char descriptions + location context → optionally calls `research_cinematography()` → computes `target_shots = max(2, min(5, int(duration_seconds / 2.5)))` → calls `_build_cinedecompose_system_prompt` → invokes `web_research.run_with_tools(client, "gpt-4o", ...)` with `max_tool_rounds=2` → parses JSON response (handles bare list, `{"shots":[]}`, single-object, and non-standard key patterns) → validates each shot through `make_shot()` with enum-guard on `camera`, `visual_effect`, `target_api`. Falls back to `_fallback_decompose()` on any exception. Side effect: logs to stdout.

**`competitive_decompose_scene`** — `domain/scene_decomposer.py:617`
Same params/returns as `decompose_scene`. Runs `LLMEnsemble().competitive_generate(task_type="decompose", ...)` — defaults to GPT-4o vs claude-sonnet-4-6 in parallel, judged by claude-sonnet-4-6 (`_DEFAULT_JUDGE`, `llm/ensemble.py:86`). On any failure falls back to `decompose_scene()`. Adds `ensemble_winner` and `ensemble_scores` fields to each shot record (`domain/scene_decomposer.py:819-820`).

**`_fallback_decompose`** — `domain/scene_decomposer.py:837`
No API key required. Always returns exactly 2 shots: an establishing wide (24mm, `zoom_in_slow`, `AUTO`) and a medium close-up (85mm, `dolly_in_rapid`, `AUTO`). Used when OpenAI is unavailable or on exception.

**`update_scene_shots`** — `domain/scene_decomposer.py:880`
Params: `project: dict`, `scene_id: str`, `shots: list[dict]`, `timeout: float = 10`. Uses `mutate_project` lock pattern (P1-3 migration; validates via `Project.model_validate` then mutates `latest_project["scenes"][i]["shots"]` and `["num_shots"]` in place). Called by `cinema_pipeline.py:960` and `web_server.py:1388`.

**`_build_cinedecompose_system_prompt` hard constraints summary:**
- HC1: Never describe face/hair/skin/glasses/eyes (identity firewall for PuLID)
- HC2: Every shot must have exactly `[SHOT][SCENE][ACTION][OUTFIT][QUALITY]` sections
- HC3: `[SCENE]` identical across all shots in a scene
- HC4: Lighting identical across all shots
- HC5: Every `[ACTION]` must include face toward camera

**`generate_dialogue`** — `domain/dialogue_writer.py:12`
Params: `scene: dict`, `characters: List[dict]`, `mood: str = "neutral"`, `style: str = "natural, cinematic"`, `language: str = "English"`.
Returns: `List[dict]` — each entry `{"character_id", "character_name", "text", "delivery"}`.
Flow: builds char descriptions → adds `language_directive` if non-English (instructs native script in `text`, English in `delivery`, no name translation) → calls `web_research.run_with_tools(client, "gpt-4o", ..., max_tool_rounds=2)` → parses response (handles list, `{"lines":}`, `{"dialogue":}`, `{"dialogue_lines":}`, single-object, any-list-value fallbacks) → validates `character_id` against known char IDs. Returns `[]` on exception.

**`format_dialogue_for_voiceover`** / **`dialogue_to_narration_text`** — **REMOVED** (pruned in `45c2299`).
Were dead helpers in `domain/dialogue_writer.py` with zero non-test callers (the former stripped to `{"character_id", "text", "delivery"}` per line; the latter joined `text` fields with spaces). Audio uses raw `generate_dialogue` output via `audio.dialogue.generate_dialogue_voiceover`.

**`get_language_defaults`** — `domain/language_defaults.py:136`
Returns a copy of `PIPELINE_LANGUAGE_DEFAULTS[language]` or `_default`. Supports: English, Korean, Japanese, Mandarin, `_default` (universal fallback).

**`merge_language_defaults_into_settings`** — `domain/language_defaults.py:157`
Params: `settings: dict` (mutated in place), `language: str`, `overwrite_existing: bool = False`.
Returns: `(settings, list[str])` — changed fields. Writes only `APPLIED_SETTINGS_FIELDS` (`tts_provider`, `dialogue_mode_enabled`, `forced_alignment_enabled`, `lipsync_engine_priority`, `lipsync_quality_validation`, `lipsync_validation_threshold`) plus `language`. Does NOT write `voice_pool_filter` or `default_male_voice/female_voice` (those are UI hints, not pipeline settings).

**`research_cinematography`** — `research_engine.py:44`
Params: `mood: str`, `location: str`, `action: str`. Returns formatted string `"[RESEARCH REFERENCE]: ..."` (≤500 chars) or `""`. Queries Tavily `search_depth="basic"`, 3 results. Returns `""` silently if Tavily not configured or on exception.

**`research_location_visual`** — `research_engine.py:72`
Returns `List[str]` of up to 5 image URLs. Called by `domain/location_manager.py:89-90`.

**`research_music_reference`** — `research_engine.py:94`
Returns reference string ≤300 chars. Called by `audio/music.py:333-334`.

**`run_with_tools`** — `web_research.py:122`
Params: `client` (OpenAI), `model: str`, `system_prompt: str`, `user_prompt: str`, `max_tool_rounds: int = 3`, `response_format: dict = None`.
Returns: final text response string.
Two-phase: Phase 1 = tool-calling loop (up to `max_tool_rounds`; tools: `tavily_search`, `firecrawl_scrape_url`; no `response_format`); Phase 2 = final call with `response_format`. Logs both phases to `CostTracker` (best-effort, non-fatal). Falls back to Phase 2 immediately if no tools are available.

**`API_REGISTRY`** — `domain/scene_decomposer.py:36`
Dict of 40+ API keys → metadata (`label`, `category`, `description`, `modality`, `best_for`, `per_shot_cost`, `quality_score`, `latency_s`, `status`). Status values: `"live"`, `"beta"`, `"planned"`. Exported from shim; imported directly by `web_server.py:50`, `llm/prompt_optimizer.py:28`, `cinema/shots/controller.py:1081`.

**`PURPOSE_API_RANKING`** — `domain/scene_decomposer.py:120`
Dict mapping 15 purpose tags → ordered API key list. Consumed by `rank_apis_for_purpose()`, `llm/prompt_optimizer.py:190`, `cinema/shots/controller.py:1121`.

**`rank_apis_for_purpose`** — `domain/scene_decomposer.py:283`
Params: `purpose: str`, `status_filter=("live","beta")`, `max_per_shot_cost=None`, `exclude=()`.
Returns: `List[(api_key, api_dict)]` filtered and ordered best-first.

**`estimate_short_cost`** — `domain/scene_decomposer.py:173`
Returns cost breakdown dict for a 60-shot project: `{totals, by_provider, per_shot, shot_count, dialogue_shots, quality_tier, notes}`.

### Data IN → OUT

**IN (per decompose call):**
- `scene` dict: `{id, title, action, dialogue, mood, camera_direction, duration_seconds, characters_present: [char_ids], location_id}`
- `characters` list: `[{id, name, physical_traits/description}]`
- `location` dict: `{id, description, lighting, time_of_day, weather}`
- `global_settings` dict: `{aspect_ratio, color_palette, competitive_generation, language, style_rules, ...}`
- `style_rules` dict (optional): `{cinematography_rules, color_grading_palette, director_vision}`
- `PIPELINE_CONTEXT` (injected from `config/prompts/pipeline_context.md` — API routing tables, lipsync rules, assembly constraints, PuLID weights, ComfyUI parameters, prompt structure)

**OUT (per decompose call):**
List of shot dicts from `make_shot()` (`domain/project_manager.py:262`) with additional fields:
```python
{
  "id": "shot_{scene_id}_{i}",
  "prompt": str,           # [SHOT][SCENE][ACTION][OUTFIT][QUALITY] formatted
  "camera": str,           # from CAMERA_MOTIONS enum
  "visual_effect": str,    # from VISUAL_EFFECTS enum
  "target_api": str,       # from TARGET_APIS (API_REGISTRY keys)
  "scene_foley": str,
  "characters_in_frame": [char_id, ...],
  "primary_character": str,
  "action_context": str,
  "intent_notes": str,
  # make_shot defaults:
  "plan_status": "pending_review",
  "generated_image": "",
  "generated_video": "",
  "keyframe_takes": [], "motion_takes": [], "postprocess_variants": [],
  # competitive path only:
  "ensemble_winner": str,
  "ensemble_scores": dict,
}
```

**IN (generate_dialogue):**
- `scene` dict (same), `characters` list, `mood`, `style`, `language`

**OUT (generate_dialogue):**
```python
[{"character_id": str, "character_name": str, "text": str, "delivery": str}]
```

### Connects to

| Subsystem | Connection type | Detail |
|---|---|---|
| `cinema_pipeline.py` | Direct call | `decompose_scene` / `competitive_decompose_scene` at `cinema_pipeline.py:924,930,932,952`; `generate_dialogue` at `cinema_pipeline.py:494,499`; `update_scene_shots` at `cinema_pipeline.py:960` |
| `web_server.py` | Direct call | `api_decompose_scene` at `web_server.py:1400` calls `decompose_scene`; `api_generate_dialogue` at `web_server.py:1363` calls `generate_dialogue`; `api_apply_language_defaults` at `web_server.py:388` calls `merge_language_defaults_into_settings` |
| `llm/ensemble.py` (`LLMEnsemble`) | Direct call | `competitive_decompose_scene` instantiates `LLMEnsemble()` and calls `competitive_generate(task_type="decompose")` at `domain/scene_decomposer.py:749-755` |
| `domain/project_manager.py` (`make_shot`, `mutate_project`) | Direct call | `make_shot` at `domain/scene_decomposer.py:593,807`; `mutate_project` via `update_scene_shots` at `domain/scene_decomposer.py:880` |
| `cinema/auto_approve.py` | Persisted field | `record_director_review_on_shots` writes `director_review` onto shot dicts (`cinema_pipeline.py:959`) so the PLAN_REVIEW gate reads it |
| `llm/style_director.py` | Upstream provider | Generates `style_rules` that get passed into `decompose_scene` as `style_ctx`; also calls `research_cinematography` at `llm/style_director.py:47-49` |
| `domain/location_manager.py` | Calls research | `research_location_visual` at `domain/location_manager.py:89-90` |
| `audio/music.py` | Calls research | `research_music_reference` at `audio/music.py:333-334` |
| `llm/prompt_optimizer.py` | Imports registry | `API_REGISTRY`, `PURPOSE_TAGS`, `rank_apis_for_purpose` at `llm/prompt_optimizer.py:28` |
| `cinema/shots/controller.py` | Imports registry | `API_REGISTRY`, `PURPOSE_API_RANKING` at `cinema/shots/controller.py:1081,1121` |
| `audio/dialogue.py` (`generate_dialogue_voiceover`) | Data handoff | `cinema_pipeline.py` passes `generate_dialogue` output into `generate_dialogue_voiceover`; `format_dialogue_for_voiceover` / `dialogue_to_narration_text` in `domain/dialogue_writer.py` have zero live callers (dead code in the working tree) |
| `web_research.py` | Direct call | Both `decompose_scene` and `generate_dialogue` call `run_with_tools` for the Tavily/Firecrawl tool loop |
| `research_engine.py` | Lazy import | Both decompose paths do `from research_engine import research_cinematography` inside a try/except (optional enrichment) |

### User-facing Surface & Capability Knobs

| Setting | Location | Default | Effect |
|---|---|---|---|
| `competitive_generation` | `project.global_settings` | `True` | When True, runs GPT-4o + Claude in parallel and judges; when False, single GPT-4o call |
| `quality_judge_llm` | `project.global_settings` via `LLMEnsemble` | `"auto"` (claude-sonnet-4) | Options: `"claude-opus"`, `"gpt-4o"`, `"gemini-pro"` — sets the judge model |
| `aspect_ratio` | `project.global_settings` | `"16:9"` | Injected into prompt as R4; affects framing constraint |
| `style_rules` | `project.global_settings` (auto-generated or user-overridden) | `{}` (auto-generated from `style_director` if empty) | Cinematography rules, color grading palette, director vision passed as style context |
| `language` | `project.global_settings` | `"English"` | Passed to `generate_dialogue` → instructs native script in `text` field; also gates `merge_language_defaults_into_settings` |
| Scene `mood` | Per-scene field | `"neutral"` | Controls dialogue generation tone and Tavily cinematography search |
| Scene `duration_seconds` | Per-scene field | 5 | `target_shots = max(2, min(5, int(duration / 2.5))` — directly sets shot count per scene |
| `TAVILY_API_KEY` env | `config/settings.py:123` | unset → research disabled | Enables cinematography Tavily search enrichment in both decompose and dialogue paths |
| `FIRECRAWL_API_KEY` env | `config/settings.py:125` | unset → scraping disabled | Enables URL scraping inside GPT-4o tool loop |
| `OPENAI_API_KEY` env | `config/settings.py` | required | Without it, `decompose_scene` and `generate_dialogue` return fallback/empty |
| `overwrite_existing` | POST body to `/api/projects/<pid>/apply-language-defaults` | `false` | When true, overwrites existing user settings with language defaults |

**Maximize quality:**
1. Set `competitive_generation: true` (default) — ensemble winner beats single-model consistently.
2. Set `quality_judge_llm: "claude-opus"` — stronger judge model.
3. Configure `TAVILY_API_KEY` — research context injection improves shot specificity.
4. Set longer `duration_seconds` (≥10s) to get 4-5 shots per scene instead of 2.
5. Use `POST /api/projects/<pid>/apply-language-defaults` with `overwrite_existing: true` for Korean/Mandarin to get native-trained lipsync ordering.
6. Edit `config/prompts/pipeline_context.md` directly — all LLMs in the pipeline ingest it on every call; changing API routing tables or identity rules here affects every decomposition without code changes.

### Control & Data Flow

**Pipeline (headless/automated path via `cinema_pipeline.py`):**

1. Phase A setup: `style_rules` computed via `generate_style_rules()` if absent in `global_settings`; persisted into project via `mutate_project` (`cinema_pipeline.py:861-889`).
2. Per-scene loop: for each scene in `project["scenes"]`, gather `chars_in_scene` and `location`.
3. If `scene["shots"]` is empty: select decompose path:
   - `use_competitive = settings.get("competitive_generation", True)` (`cinema_pipeline.py:921`)
   - Competitive path: `competitive_decompose_scene()` → calls `LLMEnsemble.competitive_generate(task_type="decompose")` → GPT-4o and Claude-sonnet run in parallel → Claude-sonnet judges → winning JSON parsed → validated into shot records.
   - Standard path: `decompose_scene()` → calls `web_research.run_with_tools("gpt-4o")` → Phase 1: up to 2 Tavily/Firecrawl tool rounds; Phase 2: final JSON response → parsed.
   - Both paths call `research_cinematography()` (optional, silently skipped if Tavily absent).
4. Chief Director validates shots: `self.director.validate_shot_prompts(shots, scene)` → if MODIFIED, shots replaced; if REJECTED, `decompose_scene()` re-runs; always `record_director_review_on_shots(shots, review)` → persists `director_review` onto shots.
5. `update_scene_shots(project, scene_id, shots)` → `mutate_project` lock write.
6. `_ensure_scene_audio()`: if scene has characters and action but no pre-existing audio → `generate_dialogue(scene, chars, mood, language=lang)` → `generate_dialogue_voiceover(dialogue_lines, chars, output_path, ctx=dialogue_ctx)` (into `audio.dialogue`).
7. PLAN_REVIEW gate: operator must approve shot plans before generation proceeds.

**On-demand via web API:**
- `POST /api/projects/<pid>/scenes/<sid>/decompose` → `api_decompose_scene` → `decompose_scene()` (always standard path, not competitive) → `update_scene_shots()`.
- `POST /api/projects/<pid>/scenes/<sid>/generate-dialogue` → `api_generate_dialogue` → `generate_dialogue()`.
- `POST /api/projects/<pid>/apply-language-defaults` → `api_apply_language_defaults` → `merge_language_defaults_into_settings()`.

### Gotchas, Divergences & Doc-Drift

**1. `api_decompose_scene` never uses competitive path.** The HTTP endpoint at `web_server.py:1400` calls `decompose_scene()` directly, not `competitive_decompose_scene()`. Only the automated pipeline (`cinema_pipeline.py:921-932`) respects `competitive_generation`. On-demand decompose via UI is always single-model.

**2. `format_dialogue_for_voiceover` and `dialogue_to_narration_text` are dead code.** Defined at `domain/dialogue_writer.py:159,174`; zero callers in the working tree outside tests. The pipeline uses `audio.dialogue.generate_dialogue_voiceover` directly with raw `generate_dialogue` output.

**3. `research_engine.py` and `web_research.py` both define `_get_tavily()` and `_get_firecrawl()`.** Two separate module-level singleton caches. If both are imported in the same process, they maintain separate client instances. `research_engine.py` is used for programmatic research calls (direct results to callers); `web_research.py` is used inside LLM tool loops (`run_with_tools`).

**4. Shim doc comment mentions `main.py`, `cleanup.py` as callers.** `main.py` is deleted (confirmed by MEMORY.md). The root `scene_decomposer.py` shim's docstring is stale on this point.

**5. `PIPELINE_CONTEXT` includes stale lipsync routing.** `config/prompts/pipeline_context.md:19` says "Dialogue close-up → VEO_NATIVE / Native lip-sync", but `PIPELINE_CONTEXT` section 2 lines 42-44 describe Omnihuman v1.5 as PRIMARY and Veo as OPT-IN only (RAI filter concern). The API routing table (section 1) conflicts with section 2's cascade. Decomposer LLM sees both and must reconcile; the hard-coded `PURPOSE_API_RANKING["dialogue_close_up"]` in code (`domain/scene_decomposer.py:120`) leads with `HEDRA_C3`, not `VEO_NATIVE`.

**6. Shot JSON schema description in `competitive_decompose_scene` differs from `decompose_scene`.** At `domain/scene_decomposer.py:429`, the `prompt` field description says "including ALL character physical descriptions and FULL location description" — contradicting HC1 (identity firewall). The `decompose_scene` version at `domain/scene_decomposer.py:429` correctly says "leaving facial identity to reference locking". This is a latent prompt contamination risk in the competitive path's schema.

**7. Research augmentation is silently no-op.** Both decompose paths wrap `research_cinematography()` in `except (ImportError, RuntimeError)` and continue. If Tavily fails mid-call (network error returns non-RuntimeError), the exception is swallowed and no research context is added with no warning at the call site (only Tavily's own print at `research_engine.py:64-67`).

**8. `update_scene_shots` uses `MutationResult(False, save=False)` only when scene not found.** Return value is `True` on success but ignored by callers. The `timeout=10` default is overridden to `HTTP_PROJECT_TIMEOUT` in the web path (`web_server.py:111`) but not in the pipeline path (`cinema_pipeline.py:960`).

**9. `merge_language_defaults_into_settings` Korean threshold is 0.70 vs English 0.65.** This is a lipsync quality gate that applies at `audio/` layer — the stricter gate for Korean means more shots may fail the lipsync score check and be rejected.

**10. `competitive_generation` is read from raw dict not Pydantic model.** `cinema_pipeline.py:921` reads `settings.get("competitive_generation", True)` from the raw `global_settings` dict. No type validation — a string `"false"` would be truthy.

### Citations

- root `scene_decomposer.py` — 9-LOC shim definition, lists legacy callers (including stale `main.py`)
- `domain/scene_decomposer.py:16-21` — `CAMERA_MOTIONS` list
- `domain/scene_decomposer.py:23-26` — `VISUAL_EFFECTS` list
- `domain/scene_decomposer.py:36-91` — `API_REGISTRY` (full registry with modality/best_for/per_shot_cost/status)
- `domain/scene_decomposer.py:92` — `TARGET_APIS = list(API_REGISTRY.keys())`
- `domain/scene_decomposer.py:98-115` — `PURPOSE_TAGS` (15 tags)
- `domain/scene_decomposer.py:120-143` — `PURPOSE_API_RANKING`
- `domain/scene_decomposer.py:150-170` — `BILLING_PROVIDERS`
- `domain/scene_decomposer.py:173-280` — `estimate_short_cost`
- `domain/scene_decomposer.py:283-307` — `rank_apis_for_purpose`
- `domain/scene_decomposer.py:326-426` — `_build_cinedecompose_system_prompt` (HC1-HC5, tripwires, schema, example)
- `domain/scene_decomposer.py:429-614` — `decompose_scene`
- `domain/scene_decomposer.py:487-495` — research context injection (lazy import, try/except)
- `domain/scene_decomposer.py:497-499` — `target_shots` calculation
- `domain/scene_decomposer.py:550-608` — `run_with_tools` call + JSON parsing + shot validation
- `domain/scene_decomposer.py:593-605` — `make_shot()` call + field enrichment
- `domain/scene_decomposer.py:617-834` — `competitive_decompose_scene`
- `domain/scene_decomposer.py:749-755` — `LLMEnsemble.competitive_generate(task_type="decompose")`
- `domain/scene_decomposer.py:819-820` — ensemble metadata added to shot records
- `domain/scene_decomposer.py:837-877` — `_fallback_decompose` (2 hardcoded shots)
- `domain/scene_decomposer.py:880-912` — `update_scene_shots` (mutate_project pattern)
- `domain/dialogue_writer.py:1-9` — shim
- `domain/dialogue_writer.py:12-156` — `generate_dialogue` (full impl)
- `domain/dialogue_writer.py:51-58` — `language_directive` construction for non-English
- `domain/dialogue_writer.py:92-101` — `run_with_tools` call in dialogue
- `format_dialogue_for_voiceover` / `dialogue_to_narration_text` — REMOVED from `domain/dialogue_writer.py` (pruned in `45c2299`; were dead, unused in prod)
- `domain/language_defaults.py:48-127` — `PIPELINE_LANGUAGE_DEFAULTS` dict (4 languages + `_default`)
- `domain/language_defaults.py:130-134` — `get_language_defaults`
- `domain/language_defaults.py:141-148` — `APPLIED_SETTINGS_FIELDS` tuple
- `domain/language_defaults.py:151-182` — `merge_language_defaults_into_settings`
- `domain/language_defaults.py:185-207` — `get_voice_pool_filter`, `recommended_voices_for_language`
- `research_engine.py:22-41` — lazy singleton init (`_get_tavily`, `_get_firecrawl`)
- `research_engine.py:44-69` — `research_cinematography` (Tavily, 3 results, 500 char cap)
- `research_engine.py:72-91` — `research_location_visual` (Tavily images, 5 URLs)
- `research_engine.py:94-118` — `research_music_reference`
- `research_engine.py:121-139` — `scrape_technique_reference` (Firecrawl, 1000 char)
- `research_engine.py:142-161` — `research_trending_topics`
- `web_research.py:80-110` — `TOOLS_SCHEMA` (GPT-4o tool definitions)
- `web_research.py:113-119` — `handle_tool_call` dispatch
- `web_research.py:122-221` — `run_with_tools` (2-phase: tool loop + final call, CostTracker)
- `web_research.py:163-179` — CostTracker integration for tool rounds
- `pipeline_context.py:1-15` — `PIPELINE_CONTEXT` loader (reads `config/prompts/pipeline_context.md`)
- `config/prompts/pipeline_context.md:1-147` — full pipeline context (API routing, lipsync, assembly, PuLID, ComfyUI, prompt structure)
- `llm/ensemble.py:80-86` — `_DEFAULT_MODELS` and `_DEFAULT_JUDGE`
- `llm/ensemble.py:93-133` — `LLMEnsemble.__init__`
- `llm/ensemble.py:139-148` — `competitive_generate` signature
- `domain/project_manager.py:262-300` — `make_shot` factory
- `cinema_pipeline.py:18-19` — imports via shims
- `cinema_pipeline.py:481-523` — `_ensure_scene_audio` (generate_dialogue → generate_dialogue_voiceover)
- `cinema_pipeline.py:921-960` — competitive vs standard decompose gate + director review
- `web_server.py:50,52-53` — imports from shim and direct domain
- `web_server.py:315,378` — API registry and purpose ranking exposed to frontend
- `web_server.py:384-444` — `api_apply_language_defaults` endpoint
- `web_server.py:1313-1341` — `api_generate_dialogue` endpoint
- `web_server.py:1348-1390` — `api_decompose_scene` endpoint
- `audio/music.py:333-334` — `research_music_reference` caller
- `domain/location_manager.py:89-90` — `research_location_visual` caller
- `llm/style_director.py:47-49` — `research_cinematography` caller
- `llm/prompt_optimizer.py:28,190,195` — `rank_apis_for_purpose`, `API_REGISTRY` consumers
- `cinema/shots/controller.py:1081,1121-1123,1209,1214` — `API_REGISTRY`, `PURPOSE_API_RANKING` consumers
- `cinema/auto_approve.py:202` — `record_director_review_on_shots` def

---

## 8. video-gen/API-cascade — Video Generation, Shot-Type Routing, and API Fallback Cascade

*Subsystem key: `video-routing`*

### Purpose

Transforms a keyframe still image into a cinematic video clip by classifying the shot type, selecting an optimal video-generation API, and executing a fault-tolerant ordered fallback cascade across multiple vendors. The subsystem encapsulates all vendor API integrations (native and FAL-proxy) behind a single `generate_ai_video` entry point, routes dialogue shots through Veo's native audio path or a mandatory lipsync pass, and writes cascade provenance metadata back to the take record for downstream audit.

### Modules

| Path | Role | LOC |
|---|---|---|
| `phase_c_ffmpeg.py` | Central routing function (`generate_ai_video`) + all per-API handlers (native + FAL-proxy) + FFmpeg utilities (stitch, split, xfade, loudnorm, color-grade) | 1350 |
| `workflow_selector.py` | Shot-type classification (`classify_shot_type`), per-shot-type template lookup (`WORKFLOW_TEMPLATES` / `MAX_QUALITY_TEMPLATES`), adaptive PuLID weight, motion-fidelity floors | 581 |
| `kling_native.py` | Native Kling 3.0 client — JWT HS256 auth, image-to-video task lifecycle, storyboard mode | 446 |
| `veo_native.py` | Native Veo 3.1 client via google-genai SDK — Vertex AI preferred, Gemini fallback, inline-bytes extraction, duration clamping | 284 |
| `ltx_native.py` | LTX Video 2.3 client — native REST API (LTX_API_KEY) preferred, FAL proxy fallback; keyframe-transition method (private, not called from cascade) | 358 |
| `sora_native.py` | Native OpenAI Sora 2 client — image-to-video with optional driving-video conditioning, `create_and_poll` + `download_content` | 156 |
| `domain/scene_decomposer.py` | `API_REGISTRY` dict (capability metadata per engine), `PURPOSE_API_RANKING` dict (ordered lists per shot purpose), `rank_apis_for_purpose` | (large; only registry section relevant here) |

### Key Functions & Classes

#### `generate_ai_video` — `phase_c_ffmpeg.py:43`
Central dispatch and cascade. Params: `image_path` (start frame), `camera_motion` (string), `target_api` (engine key), `output_mp4`, `pacing`, `character_id`, `attempted_apis` (dedup list), `multi_angle_refs` (list of paths), `_cascade_retries`, `negative_prompt`, `shot_type`, `video_fallbacks` (override list), `driving_video_path` (performance-capture clip), `has_dialogue` (bool), `ctx` (PipelineContext), `_cascade_out` (dict written by `_record_video_cascade`). Returns `output_mp4 str` on success or `None` on total cascade failure. Side-effects: prints engine routing logs; modifies `_cascade_out["cascade_metadata"]` on success; may update module-global `_VEO_QUOTA_EXHAUSTED_UNTIL`.

#### `_record_video_cascade` — `phase_c_ffmpeg.py:91` (inner)
Writes `{"engine": winning_engine, "attempts": [...]}` into `_cascade_out["cascade_metadata"]`. Called immediately before every successful engine `return`. Not called on fallback. Enables the caller (`cinema/shots/controller.py:1205`) to persist provenance to the take record.

#### `try_next_api` — `phase_c_ffmpeg.py:122` (inner closure)
Iterates `video_fallbacks` (or the default ordered list) filtering already-attempted engines and optionally filtering by `api_engines.enabled` from `ctx`. On total exhaustion, sleeps 30 s then retries the full cascade up to `MAX_CASCADE_RETRIES` (default 1, overridable via `cascade_retry_limit` project setting). Returns `None` after max retries.

#### `_veo_quota_blocked` / `_VEO_QUOTA_EXHAUSTED_UNTIL` — `phase_c_ffmpeg.py:22 / 18`
Module-level state. `_VEO_QUOTA_BLOCKED()` returns `True` if a VEO (FAL-proxy, NOT VEO_NATIVE) 429 set the TTL flag within the last 1800 s (`_VEO_QUOTA_TTL_S`). Only the FAL-proxy `VEO` branch (`phase_c_ffmpeg.py:502–504`) sets this flag; `VEO_NATIVE` does NOT share it — native Veo errors are caught as generic exceptions.

#### `classify_shot_type` — `workflow_selector.py:411`
Input: shot dict with `characters_in_frame`, `prompt`, `camera` keys. Priority: (1) no characters → `"landscape"`, (2) parse `[SHOT]` section keywords, (3) full-prompt keywords, (4) default `"medium"`. Keyword tables at `workflow_selector.py:112–133`. Returns one of `"portrait" | "medium" | "wide" | "action" | "landscape"`. Note: `close_up` appears in `MOTION_FIDELITY_FLOORS` but is NOT returned by this function — the FLOORS dict has a comment acknowledging this inconsistency (`workflow_selector.py:395`).

#### `get_workflow_params` — `workflow_selector.py:450`
Returns a copy of `WORKFLOW_TEMPLATES[shot_type]` (production tier) or `MAX_QUALITY_TEMPLATES[shot_type]` (max tier). Overlays 4 per-project UI knobs: `flux_guidance → guidance`, `comfyui_sampler → sampler`, `comfyui_steps → steps`, `continuity_options.img2img_denoise → denoise_default` (clamped `[0.2, 0.6]`). Unknown `shot_type` falls back to `"medium"`. Returns mutable copy.

#### `apply_workflow_params` — `workflow_selector.py:501`
Writes params into a ComfyUI workflow JSON dict in-place: Node 100 (ApplyPulid weight/start_at/end_at), Node 60 (FluxGuidance), Node 17 (BasicScheduler steps+scheduler), Node 16 (KSamplerSelect sampler_name), Node 301 (PAG scale). Returns the workflow. Does NOT override denoise (set by img2img logic in `generate_ai_broll`).

#### `get_adaptive_pulid_weight` — `workflow_selector.py:540`
Queries `identity_validator.get_rolling_stats(character_id)` → `suggested_pulid_delta` and adds it to the base weight, clamped `[0.0, 1.0]`. Suppresses boost for `FACE_ANGLE_EXTREME` failures (clamps delta ≤ 0) and zeroes it for `SMALL_FACE_REGION`.

#### `WORKFLOW_TEMPLATES` — `workflow_selector.py:21`
Dict mapping shot type → primary video API + fallback list + ComfyUI render params. Shot-type primary API assignments (production tier):

| shot_type | target_api | video_fallbacks |
|---|---|---|
| portrait | KLING_NATIVE | RUNWAY_GEN4, SORA_NATIVE, KLING_3_0 |
| medium | KLING_NATIVE | RUNWAY_GEN4, SORA_NATIVE, LTX |
| wide | LTX | VEO_NATIVE, KLING_NATIVE, RUNWAY_GEN4 |
| action | SORA_NATIVE | KLING_NATIVE, RUNWAY_GEN4, LTX, SEEDANCE |
| landscape | LTX | VEO_NATIVE, KLING_NATIVE |

#### `WORKFLOW_TEMPLATES` note on dialogue
`workflow_selector.py:104–108`: `"dialogue"` is explicitly NOT a ComfyUI image-gen template. Dialogue shots use portrait/medium for image gen; video generation cascade is `VEO_NATIVE → Kling Lip Sync → Omnihuman` with hard cuts only for assembly.

#### `KlingNativeAPI` — `kling_native.py:19`
- `__init__`: reads `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` from settings; raises `ValueError` if missing.
- `_generate_token` (`kling_native.py:46`): HS256 JWT with 30-min expiry; cached, regenerated if < 5 min remain.
- `create_image_to_video` (`kling_native.py:86`): base64-encodes image; submits to `POST /v1/videos/image2video`. Params: `duration` (str, default `"5"`), `mode` (`"pro"`), `model_name` (`"kling-v1-6"`), `face_consistency` (bool), `image_references` (list → body as `image_reference`). Returns `task_id`.
- `poll_task` (`kling_native.py:170`): exponential backoff `[3,5,8,12,15]` s, 600-s timeout. Raises `RuntimeError` on `"failed"`, `TimeoutError` on timeout.
- `generate_video` (`kling_native.py:264`): convenience wrapper — create → poll (180-s default timeout from kwarg) → download → return path.
- `generate_storyboard` (`kling_native.py:310`): up to 6 shots, 15 s total, distributes durations, sets `face_consistency: True`, posts `multi_prompt`. 600-s poll timeout.

#### `VeoNativeAPI` — `veo_native.py:105`
- `__init__` (`veo_native.py:112`): tries Vertex AI (`genai.Client(vertexai=True, project=..., location=...)`); on failure falls back to Gemini API (`genai.Client(api_key=...)`). Model: `"veo-3.1-generate-001"` (Vertex) or `"veo-3.1-generate-preview"` (Gemini). Records `self._backend`.
- `generate_video` (`veo_native.py:138`): key behaviors — (1) accepts `reference_images` but silently ignores them (image/reference_images are mutually exclusive on image-to-video; `veo_native.py:201–204`); (2) `driving_video_path` accepted but not wired — SDK `video=` and `image=` are mutually exclusive (`veo_native.py:231–234`); (3) duration clamped via `_clamp_image_to_video_duration`; (4) polls via `client.operations.get(operation)` every 10 s up to 120 polls (20 min); (5) surfaces `operation.error` deterministically (`veo_native.py:255–259`); (6) reads bytes via `_extract_video_bytes`.
- `_extract_video_bytes` (`veo_native.py:85`): prefers `video_obj.video_bytes` (Vertex inline); falls back to `client.files.download` (Gemini only). Uses `is not None` (not truthiness) so empty `b""` stays on the inline path and doesn't crash Vertex.
- `_clamp_image_to_video_duration` (`veo_native.py:38`): valid values are `(4, 6, 8)`. Ties round UP (5→6, 7→8). Any other value is snapped to nearest. 5 s is rejected server-side with INVALID_ARGUMENT.
- `_build_generate_videos_config` (`veo_native.py:50`): builds `types.GenerateVideosConfig`. Wraps each reference_image in `VideoGenerationReferenceImage(reference_type=ASSET)`.

#### `SoraNativeAPI` — `sora_native.py:20`
- `generate_video` (`sora_native.py:42`): valid durations `[4, 8, 12, 16, 20]` (invalid defaults to 4); resizes image to 1280×720 via PIL before upload; uses `client.videos.create_and_poll`; downloads via `client.videos.download_content(video.id)` iterating `response.iter_bytes()`.
- Driving-video conditioning (`sora_native.py:77–114`): when `driving_video_path` exists, Sora uses it as `input_reference` (video conditioning) instead of the resized still. Still-frame resize always runs as safety net. On any access error, falls through to still-image path.
- Shutdown warning: OpenAI announced Sora will shut down September 2026 (`sora_native.py:6`).

#### `LTXVideoAPI` — `ltx_native.py:22`
- Init: checks `LTX_API_KEY` (native mode) → else `FAL_KEY` (FAL proxy) → else disabled.
- `generate_video` (`ltx_native.py:68`): `duration * 24 = num_frames`; dispatches to `_native_generate` or `_fal_generate`. Camera motion from 15-item allowlist (`CAMERA_MOTIONS` at `ltx_native.py:42`).
- `_native_generate` (`ltx_native.py:201`): uploads via FAL if available for a hosted URL, else base64 data URI; POST to `https://api.ltx.video/v1/image-to-video`, model `"ltx-2-3-pro"`, returns video bytes directly (no polling). On failure, falls back internally to `_fal_generate`.
- `_fal_generate` (`ltx_native.py:114`): `fal_client.subscribe("fal-ai/ltx-2/image-to-video", ...)`.
- `_fal_transition` / `_native_transition` (`ltx_native.py:157 / 273`): keyframe interpolation (start + end frame); these methods exist but are NOT called from `generate_ai_video` — they are unused by the cascade.
- Singleton accessor `get_ltx_client()` at `ltx_native.py:363`.

#### `API_REGISTRY` — `domain/scene_decomposer.py:36`
Master capability dict for all engines. Key fields per entry: `modality` (`"video"/"image"/"lipsync"/...`), `status` (`"live"/"beta"/"planned"`), `native_audio` (bool, only on VEO_NATIVE: `True`), `per_shot_cost`, `quality_score`, `latency_s`, `best_for` list.

Video-modality entries relevant to this subsystem:

| Key | Status | native_audio | Quality | Cost/shot | Latency |
|---|---|---|---|---|---|
| KLING_NATIVE | live | — | 0.86 | $0.35 | 90 s |
| SORA_NATIVE | live | — | 0.88 | $0.50 | 120 s |
| VEO_NATIVE | live | **True** | 0.85 | $0.40 | 100 s |
| RUNWAY_GEN4 | live | — | 0.82 | $0.30 | 75 s |
| LTX | live | — | 0.74 | $0.06 | 60 s |
| KLING_3_0 | live | — | 0.84 | $0.40 | 110 s |
| SORA_2 | live | — | 0.87 | $0.55 | 130 s |
| VEO (FAL) | live | — | 0.83 | $0.45 | 115 s |
| RUNWAY | live | — | 0.80 | $0.32 | 80 s |
| FAL_SVD | (live) | — | — | — | — |
| SEEDANCE | (live) | — | — | — | — |

### Data IN -> OUT

**Inputs consumed:**
- `image_path`: start-frame keyframe image (JPEG/PNG) — generated upstream by phase_c_assembly / ComfyUI
- `camera_motion`: string from shot's `camera` field (e.g. `"zoom_in_slow"`, `"pan_right"`)
- `shot_type`: one of `portrait/medium/wide/action/landscape` — derived by `classify_shot_type` at call site
- `video_fallbacks`: ordered list of API keys from `WORKFLOW_TEMPLATES[shot_type]["video_fallbacks"]`
- `multi_angle_refs`: list of character reference image paths (from `continuity_config.multi_angle_refs`)
- `driving_video_path`: optional performance-capture MP4 (from `shot.approved_performance_take_id`)
- `has_dialogue`: bool derived from `shot.optimizer_cache.spec.purpose` ∈ `{dialogue_close_up, talking_head_full}`
- `negative_prompt`: auto-built from shot_type or passed from `shot.negative_constraints`
- `ctx`: `PipelineContext` carrying `global_settings` (for `api_engines` filter + `cascade_retry_limit`)

**Outputs produced:**
- `output_mp4`: MP4 video file on disk at the path passed in
- Returns: `str` path on success, `None` on total failure
- `_cascade_out["cascade_metadata"]`: `{"engine": str, "attempts": [str, ...]}` — provenance record
- Side-effect on `take["metadata"]`: `audio_embedded=True` when winning engine is VEO_NATIVE with `has_dialogue`; `has_dialogue=True` always written for gate awareness

### Connects To

| Subsystem | Connection type | Details |
|---|---|---|
| `cinema/shots/controller.py` | Direct call | Primary caller at `cinema/shots/controller.py:1186`; builds `PipelineContext`, resolves `target_api` + `video_fallbacks`, passes `driving_video_path` + `has_dialogue`; reads `_cascade_out` post-call |
| `domain/scene_decomposer.py` | Import of `API_REGISTRY` + `PURPOSE_API_RANKING` | Controller reads registry at routing time to resolve dialogue override; `try_next_api` reads `api_engines` filter from `ctx` |
| `workflow_selector.py` | Direct call | Controller calls `classify_shot_type` + `WORKFLOW_TEMPLATES` at `controller.py:1080–1111` to determine `target_api` + `video_fallbacks` before calling `generate_ai_video` |
| `cinema/context.py` | PipelineContext | `get_project_setting(ctx, "api_engines")` and `cascade_retry_limit` read inside `generate_ai_video:try_next_api` |
| `config/settings.py` | Module-level import | API keys (`KLING_ACCESS_KEY/SECRET`, `OPENAI_API_KEY`, `FAL_KEY`, `LTX_API_KEY`, `RUNWAYML_API_SECRET`, `SEEDANCE_API_KEY`, `GOOGLE_CLOUD_PROJECT/LOCATION`) |
| `identity/` + `domain/continuity_engine.py` | Shared data | `multi_angle_refs` passed in from `continuity_config`; `workflow_selector.get_adaptive_pulid_weight` called by `domain/continuity_engine.py:523` |
| `performance/motion_gate.py` | Post-call | Reads the generated video + `driving_video_path` to score motion fidelity against `MOTION_FIDELITY_FLOORS`; advisory only |
| `lip_sync.py` | Post-call (F1b) | Called at `cinema/shots/controller.py:1233` when `has_dialogue=True` and `not audio_embedded` — mandatory lipsync pass |
| `cinema/phases/motion_render.py` | Phase wrapper | `MotionRenderPhase.run()` iterates shots and calls the controller's motion-take path; also uses `classify_shot_type` directly at `motion_render.py:232` and `split_video_into_segments` from `phase_c_ffmpeg` at `motion_render.py:118` |

### User-Facing Surface & Capability Knobs

**Per-project settings (via UI / `global_settings` JSON):**

| Setting key | Effect | Where applied |
|---|---|---|
| `api_engines` (dict) | Per-engine enable/disable; `{"VEO_NATIVE": {"enabled": false}}` drops that engine from `try_next_api` loop AND from explicit targeting | `phase_c_ffmpeg.py:135–142, 185–191` |
| `cascade_retry_limit` (int ≥ 0) | Override `MAX_CASCADE_RETRIES` (default 1); 0 = no retry after total exhaustion | `phase_c_ffmpeg.py:158–163` |
| `flux_guidance` (float) | Overlays `guidance` in workflow params (ComfyUI FLUX CFG) | `workflow_selector.py:479–481` |
| `comfyui_sampler` (str) | Overlays `sampler` (e.g. `"dpmpp_3m_sde_gpu"` for max tier) | `workflow_selector.py:483–485` |
| `comfyui_steps` (int) | Overlays `steps` count | `workflow_selector.py:487–489` |
| `continuity_options.img2img_denoise` (float) | Overlays `denoise_default` for img2img strength; clamped `[0.2, 0.6]` | `workflow_selector.py:493–496` |

**Per-shot overrides:**
- `shot.target_api`: explicitly pin an engine; `"AUTO"` triggers smart routing via optimizer cache + shot-type template
- `shot.camera`: camera motion string passed through to prompt and LTX camera-motion mapping
- `shot.negative_constraints`: overrides the auto-built negative prompt
- `shot.driving_video_path` + `shot.approved_performance_take_id`: triggers driving-video conditioning (Sora wires it; Veo/Kling accept param but do not apply it)

**Env vars (API keys):**
`KLING_ACCESS_KEY`, `KLING_SECRET_KEY`, `OPENAI_API_KEY`, `FAL_KEY`, `LTX_API_KEY`, `RUNWAYML_API_SECRET`, `SEEDANCE_API_KEY`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` (default `us-central1`), `GOOGLE_API_KEY` (Gemini fallback for Veo)

**To maximize quality/capability:**
- Use quality tier `"max"` to get `MAX_QUALITY_TEMPLATES` (N=8 best-of, 4-layer identity, SUPIR upscale)
- For portrait/medium: KLING_NATIVE + `face_consistency=True` is primary; Sora for action physics
- For landscape/environment: LTX at 4K (`shot_type == "landscape"` → `ltx_resolution = "4k"`)
- For dialogue: ensure VEO_NATIVE is live (only engine with `native_audio=True`); audio generation auto-triggered when `has_dialogue=True`
- For driving-video: only Sora fully wires it; Veo and Kling accept the param but silently ignore it

### Control & Data Flow

1. **Shot classification**: `classify_shot_type(shot)` → `shot_type` ∈ {portrait, medium, wide, action, landscape} (`cinema/shots/controller.py:1083`)

2. **API resolution** (`controller.py:1084–1147`):
   - If `shot.target_api == "AUTO"`: check `shot.optimizer_cache.spec.suggested_video_api` → if valid API_REGISTRY key, use it + template fallbacks; else use `WORKFLOW_TEMPLATES[shot_type]["target_api"]` + its fallbacks
   - Dialogue override (F1a): if `has_dialogue=True`, scan `PURPOSE_API_RANKING[purpose]` for first entry where `native_audio=True AND modality=="video" AND status=="live"` → override `target_api` to that engine (currently VEO_NATIVE) and `video_fallbacks = None`
   - If `shot.target_api != "AUTO"`: use raw value, `video_fallbacks = None`

3. **`generate_ai_video` called** (`cinema/shots/controller.py:1186`) with resolved `target_api`, `video_fallbacks`, `driving_video_path`, `has_dialogue`, `ctx`, `_cascade_out={}`

4. **Engine-disabled check** (`phase_c_ffmpeg.py:185–191`): if `ctx.api_engines[target_api].enabled == False`, immediately call `try_next_api()`

5. **Per-engine branch** — attempts the targeted engine:
   - **KLING_NATIVE** (`phase_c_ffmpeg.py:197`): `face_consistency=True` for portrait/medium/action; `image_references=multi_angle_refs`; 5-s duration; mode=pro; native JWT auth
   - **SORA_NATIVE** (`phase_c_ffmpeg.py:227`): duration from `{action/wide/landscape→8, portrait/medium→4}`; passes `driving_video_path` as `input_reference` when file exists
   - **VEO_NATIVE** (`phase_c_ffmpeg.py:265`): `generate_audio=(shot_type=="landscape" or has_dialogue)`; `reference_images=multi_angle_refs` (accepted but silently dropped per Bug #4); `driving_video_path` accepted but not wired (SDK exclusivity)
   - **LTX** (`phase_c_ffmpeg.py:292`): camera-motion remapped via `_ltx_camera_map`; resolution 4K for landscape, 1080p otherwise
   - **RUNWAY_GEN4** (`phase_c_ffmpeg.py:331`): uses `runwayml` SDK, model `"gen4"`, 10-s duration, polls up to 300 s
   - **SORA_2** (FAL proxy) (`phase_c_ffmpeg.py:386`): `fal_client.subscribe("fal-ai/sora-2/image-to-video")`, 4-s fixed duration
   - **VEO** (FAL proxy) (`phase_c_ffmpeg.py:437`): quota-block check first; uploads up to 4 `multi_angle_refs`; 8-s, 720p; quota exhaustion sets `_VEO_QUOTA_EXHAUSTED_UNTIL = now + 1800`
   - **KLING_3_0** (FAL proxy) (`phase_c_ffmpeg.py:511`): subject binding via `elements[0].frontal_image_url + reference_image_urls`; up to 2 attempts
   - **FAL_SVD** (`phase_c_ffmpeg.py:597`): `fal-ai/fast-svd`, `motion_bucket_id=127`
   - **RUNWAY** (`phase_c_ffmpeg.py:658`): `gen3a_turbo`, 5-s, `wait_for_task_output()`
   - **SEEDANCE** (`phase_c_ffmpeg.py:691`): `seedance-2.0`, 5-s, polls 120 × 5 s max (10 min); identity reference appended if `character_id` and `characters.json` found
   - **Unknown key** (`phase_c_ffmpeg.py:765`): falls immediately to `try_next_api()`

6. **On success**: `_record_video_cascade(api_name)` writes provenance → engine returns `output_mp4`

7. **On failure**: calls `try_next_api()` → iterates `video_fallbacks` (or default list), skipping already-attempted; filters by `api_engines`; recurses into `generate_ai_video` with next engine

8. **Total exhaustion**: if all engines in list attempted, sleeps 30 s, resets `attempted_apis=[]`, restarts from `first_api`; stops after `MAX_CASCADE_RETRIES` (default 1); returns `None`

9. **Post-call** (controller): reads `winning_engine` from `cascade_metadata`; checks `API_REGISTRY[winning_engine]["native_audio"]`; if `True` and `has_dialogue`, sets `take.metadata.audio_embedded=True`; if `has_dialogue and not audio_embedded`, runs mandatory lipsync pass via `generate_lip_sync_video`

### Gotchas, Divergences & Doc-Drift

**Bug #4 — Veo reference_images silently dropped** (`veo_native.py:155–204`): `reference_images` param is accepted by `VeoNativeAPI.generate_video` and by the `VEO_NATIVE` branch of `generate_ai_video` (which passes `multi_angle_refs=multi_angle_refs`), but `veo_native.py` logs a warning and passes `reference_images=None` to `_build_generate_videos_config`. Reason: Vertex AI rejects "Image and reference images cannot be both set." The upstream caller at `phase_c_ffmpeg.py:280` still passes the arg — it has no observable effect. Identity comes from the start frame only.

**driving_video_path unwired on Veo** (`veo_native.py:169–176, 231–234`): Veo SDK's `video=` input is for video extension and is mutually exclusive with `image=`. The param is accepted for interface stability but doing nothing. Only Sora fully wires it.

**5-second duration rejected by Veo** (`veo_native.py:26`): Veo image-to-video only accepts 4, 6, or 8 seconds. 5 s is explicitly invalid (server returns INVALID_ARGUMENT). `_clamp_image_to_video_duration` snaps 5→6, 7→8. The comment at line 22–26 documents this empirically.

**VEO_NATIVE has NO quota-block guard** (`phase_c_ffmpeg.py:265–290`): The `_VEO_QUOTA_EXHAUSTED_UNTIL` flag is only checked and set for the FAL-proxy `VEO` branch. If VEO_NATIVE exhausts quota, the exception is caught generically and cascades without setting the TTL — no automatic cooldown for the native path.

**Default cascade order includes both native and FAL-proxy duplicates** (`phase_c_ffmpeg.py:128–130`): `["KLING_NATIVE", "SORA_NATIVE", "RUNWAY_GEN4", "LTX", "VEO_NATIVE", "KLING_3_0", "SORA_2", "VEO", "RUNWAY"]` — VEO_NATIVE and VEO (FAL) are separate cascade members. If VEO_NATIVE fails, VEO (FAL) is a later fallback.

**Dialogue routing override drops fallbacks** (`controller.py:1138–1141`): when `has_dialogue=True`, `video_fallbacks` is set to `None` to prevent cross-engine fallback to non-native-audio engines. If VEO_NATIVE fails, `try_next_api()` falls through to the default global list which includes non-audio engines — the native-audio guarantee is only on the primary attempt.

**LTX `_fal_transition` / `_native_transition` are dead code** in the cascade: `ltx_native.py:157, 273` implement keyframe interpolation (start + end frame) but nothing in `generate_ai_video` calls them. They can only be reached by direct use of `LTXVideoAPI`.

**RUNWAY (Runway) does NOT have a dedicated native module**: there is no `runway_native.py`. The `RUNWAY_GEN4` branch imports `runwayml` SDK inline at `phase_c_ffmpeg.py:334`; the legacy `RUNWAY` branch also does so inline at `phase_c_ffmpeg.py:663`. Both use the `runwayml` pip package directly — no wrapper class exists.

**SEEDANCE uses an unverified API endpoint** (`phase_c_ffmpeg.py:706`): `https://api.seedance.ai/v1/video/generate` — no official Seedance SDK; relies on a speculative REST schema. Status: "live" in `API_REGISTRY` but not battle-tested.

**`close_up` inconsistency in `MOTION_FIDELITY_FLOORS`** (`workflow_selector.py:395`): the dict has a `close_up` key with a comment saying "close_up is a real shot_type returned by classify_shot_type," but `classify_shot_type` never returns `"close_up"` — it only returns `portrait/medium/wide/action/landscape`. The floor for `close_up` is unreachable via the normal code path.

**Sora shutdown planned September 2026** (`sora_native.py:6`): documented as a comment; no automated fallback policy currently in code.

**`FAL_SVD` key renamed** from `"COMFY_UI"` (`phase_c_ffmpeg.py:600–602`): old shot records using `target_api: "COMFY_UI"` will fall through to `try_next_api()` (unknown-key branch at `phase_c_ffmpeg.py:765`).

**Kling `poll_task` timeout default mismatch**: `generate_video` kwarg reads `timeout = kwargs.pop("timeout", 180)` (`kling_native.py:288`) but the caller in `phase_c_ffmpeg.py:202` does not pass `timeout` — so Kling native polls for 180 s max (3 min). The storyboard path uses 600 s. The API-level default in `poll_task` is also 600 s, but the `kwargs.pop` in `generate_video` shadows it.

**Sora `download_url` dead code** (`sora_native.py:133–141`): the code tries to find `video.url` / `video.video.url` / `video.output.url` but immediately below uses `client.videos.download_content(video.id)` — the URL extraction is never used for the actual download.

### Citations

| Claim | File:Line |
|---|---|
| `_VEO_QUOTA_EXHAUSTED_UNTIL` module-level state, TTL 1800 s | `phase_c_ffmpeg.py:18–19` |
| `_veo_quota_blocked` function | `phase_c_ffmpeg.py:22–28` |
| `generate_ai_video` signature | `phase_c_ffmpeg.py:43–60` |
| Shot-type negative-prompt tailoring | `phase_c_ffmpeg.py:103–118` |
| `_record_video_cascade` inner function | `phase_c_ffmpeg.py:91–101` |
| `try_next_api` closure + default cascade order | `phase_c_ffmpeg.py:122–179` |
| `api_engines` filter in `try_next_api` | `phase_c_ffmpeg.py:135–142` |
| `MAX_CASCADE_RETRIES` default + `cascade_retry_limit` override | `phase_c_ffmpeg.py:158–166` |
| 30-s quota-cooldown sleep | `phase_c_ffmpeg.py:168–172` |
| Engine-disabled guard | `phase_c_ffmpeg.py:185–191` |
| KLING_NATIVE branch: `face_consistency`, 5-s duration | `phase_c_ffmpeg.py:197–225` |
| SORA_NATIVE branch: duration map, driving-video usage | `phase_c_ffmpeg.py:227–263` |
| VEO_NATIVE branch: `generate_audio` trigger | `phase_c_ffmpeg.py:265–290` |
| VEO_NATIVE `generate_audio` condition | `phase_c_ffmpeg.py:281` |
| LTX branch: camera-motion remap, 4K for landscape | `phase_c_ffmpeg.py:292–329` |
| RUNWAY_GEN4 branch: model gen4, 10-s, 300-s poll | `phase_c_ffmpeg.py:331–380` |
| SORA_2 (FAL) branch: 4-s fixed | `phase_c_ffmpeg.py:386–435` |
| VEO (FAL) branch: quota-block check, 4-ref upload, 8-s 720p | `phase_c_ffmpeg.py:437–509` |
| VEO (FAL) quota exhaustion sets TTL flag | `phase_c_ffmpeg.py:502–504` |
| KLING_3_0 (FAL) subject binding via `elements` | `phase_c_ffmpeg.py:511–595` |
| FAL_SVD renamed from COMFY_UI | `phase_c_ffmpeg.py:600–602` |
| RUNWAY (legacy) `gen3a_turbo` | `phase_c_ffmpeg.py:658–689` |
| SEEDANCE speculative API endpoint | `phase_c_ffmpeg.py:691–763` |
| Unknown API → `try_next_api()` | `phase_c_ffmpeg.py:765–767` |
| `WORKFLOW_TEMPLATES` dict (shot types, primary APIs, fallback lists) | `workflow_selector.py:21–109` |
| Dialogue note — VEO_NATIVE → Kling Lip Sync → Omnihuman | `workflow_selector.py:104–108` |
| `SHOT_TYPE_KEYWORDS` keyword tables | `workflow_selector.py:112–133` |
| `MAX_QUALITY_TEMPLATES` (max tier, N=8) | `workflow_selector.py:143–370` |
| `MOTION_FIDELITY_FLOORS` + `close_up` inconsistency comment | `workflow_selector.py:395–402` |
| `classify_shot_type` priority logic | `workflow_selector.py:411–447` |
| `get_workflow_params` overlay knobs | `workflow_selector.py:450–498` |
| `apply_workflow_params` node map | `workflow_selector.py:501–537` |
| `get_adaptive_pulid_weight` feedback loop | `workflow_selector.py:540–580` |
| `VEO_IMAGE_TO_VIDEO_DURATIONS = (4, 6, 8)` | `veo_native.py:26` |
| `_clamp_image_to_video_duration` logic | `veo_native.py:38–47` |
| `_extract_video_bytes` inline vs files.download decision | `veo_native.py:85–102` |
| `VeoNativeAPI.__init__` Vertex/Gemini preference | `veo_native.py:112–133` |
| Model name strings | `veo_native.py:136` |
| `reference_images` silently dropped (Bug #4) | `veo_native.py:155–213` |
| `driving_video_path` not wired on image-to-video | `veo_native.py:169–176, 231–234` |
| Poll loop 120 × 10 s = 20-min max | `veo_native.py:242–250` |
| `operation.error` surface | `veo_native.py:255–259` |
| RAI filter detection | `veo_native.py:262–269` |
| `KlingNativeAPI.__init__` raises on missing keys | `kling_native.py:36–39` |
| JWT token generation / 30-min expiry / 5-min cache threshold | `kling_native.py:46–72` |
| `create_image_to_video` `image_reference` param | `kling_native.py:86–168` |
| `poll_task` exponential backoff schedule | `kling_native.py:190–233` |
| `generate_video` 180-s timeout kwarg pop | `kling_native.py:264` |
| `generate_storyboard` 6-shot cap, 15-s total, `multi_prompt` | `kling_native.py:310–446` |
| Sora shutdown Sep 2026 warning | `sora_native.py:6` |
| Sora valid durations `[4,8,12,16,20]` | `sora_native.py:81–84` |
| Sora driving-video as `input_reference` | `sora_native.py:77–114` |
| Sora `download_content` download method | `sora_native.py:146–151` |
| LTX `CAMERA_MOTIONS` 15-item list | `ltx_native.py:42–47` |
| LTX `_native_generate` → bytes direct, no poll | `ltx_native.py:201–271` |
| LTX `_fal_transition` / `_native_transition` (unused in cascade) | `ltx_native.py:157–195, 273–305` |
| `get_ltx_client` singleton | `ltx_native.py:348–353` |
| `API_REGISTRY` full dict | `domain/scene_decomposer.py:36–91` |
| `VEO_NATIVE native_audio=True` | `domain/scene_decomposer.py:43` |
| `PURPOSE_API_RANKING` | `domain/scene_decomposer.py:121–141` |
| Controller: `classify_shot_type` call | `cinema/shots/controller.py:1083` |
| Controller: dialogue override logic (F1a) | `cinema/shots/controller.py:1113–1144` |
| Controller: `generate_ai_video` call site | `cinema/shots/controller.py:1186–1201` |
| Controller: `audio_embedded` flag write | `cinema/shots/controller.py:1214–1216` |
| Controller: mandatory F1b lipsync pass | `cinema/shots/controller.py:1233–1253` |
| `web_server.py` imports `WORKFLOW_TEMPLATES` | `web_server.py:58` |
| Motion render phase uses `split_video_into_segments` | `cinema/phases/motion_render.py:118` |

---

## 9. keyframe/image-gen/max-tier — Image/Keyframe Generation and Quality Tiers

*Subsystem key: `image-tiers`*

### Purpose

This subsystem converts a per-shot text prompt into a 1344×768 JPEG keyframe that serves as the visual anchor for all downstream video generation. It uses FLUX-Dev on a RunPod ComfyUI pod with PuLID face-locking as the primary path, FAL.ai FLUX Kontext/Pro as cloud fallback, and an optional "max" tier that runs N=8 adaptive best-of generation with ArcFace/Aesthetic scoring, four-channel Union ControlNet, FLUX Redux style transfer, FaceDetailer, ReActor CodeFormer, and SUPIR 4K upscale. A produced keyframe must be operator-approved before the pipeline advances to video generation.

### Modules

| Path | Role | LOC |
|---|---|---|
| `phase_c_assembly.py` | Production-tier image generation: ComfyUI PuLID orchestration, FAL fallbacks, `generate_ai_broll` entry point | 582 |
| `quality_max.py` | Max-tier orchestrator: workflow loading, node pruning/injection, N=8 best-of loop with adaptive halt | 865 |
| `cinema/phases/keyframe_render.py` | Phase wrapper: iterates all unapproved shots, calls `generate_keyframe_take`, handles per-shot failures without failing the phase | 109 |
| `workflow_selector.py` | Shot-type classifier + per-type param templates for both tiers; production `WORKFLOW_TEMPLATES` (5 types) and `MAX_QUALITY_TEMPLATES` (5 types); adaptive PuLID weight feedback | 581 |
| `face_validator_gate.py` | Scoring: `CandidateScore` dataclass, `score_candidate` (ArcFace + LAION Aesthetic v2), `should_halt`, `select_best`, `needs_regenerate` | 304 |
| `cinema/shots/controller.py` | `generate_keyframe_take`: wires continuity engine output, quality tier, optimizer, and calls `generate_ai_broll`; `approve_take` | 1873 |
| `domain/continuity_engine.py` | `ContinuityEngine.enhance_shot_prompt`: builds prompt + `continuity_config` (img2img chain, scene seed, adaptive PuLID weight, primary reference, identity anchor) | 627 |
| `continuity_engine.py` | Backward-compat shim — `from domain.continuity_engine import *` | 9 |
| `identity/validator.py` | `IdentityValidator`: ArcFace cosine similarity scoring, rolling stats, per-character history | 887 |
| `pulid.json` | Production ComfyUI workflow (22 nodes, SDXL-style `ApplyPulid`/`PulidModelLoader`) | — |
| `pulid_max.json` | Max-tier ComfyUI workflow (56 nodes, FLUX-native `ApplyPulidFlux`/`PulidFluxModelLoader`) | — |

### Key Functions & Classes

#### `generate_ai_broll` — `phase_c_assembly.py:74`

Entry point for all production-tier image generation. Signature: `(prompt, output_filename, seed, character_image, init_image, denoise_strength, characters, multi_angle_refs, identity_anchor, pulid_weight_override, negative_prompt, quality_tier, char_lora_path, style_reference, shot_hint, ctx) → ImageGenResult | None`

Priority chain:
1. If `quality_tier == "max"`: import `quality_max.generate_ai_broll_max`, call it; fall through on `None` or exception.
2. If `COMFYUI_SERVER_URL` set AND `pulid.json` exists: use `RunPodComfyUI` + dynamic injection (steps 1–5c below).
3. Else: `_fal_flux_fallback`.

Notable: landscape shots skip PuLID entirely and route to `_fal_flux_fallback` with `character_image=None` (`phase_c_assembly.py:198–200`). No-character shots strip all PuLID nodes (97/99/100/101/93) and rewire PAG (node 301) directly to UNETLoader (node 112) (`phase_c_assembly.py:227–231`).

#### `RunPodComfyUI` — `phase_c_assembly.py:34`

HTTP client for the ComfyUI REST API. Methods: `upload_image` (POST `/upload/image`), `queue_prompt` (POST `/prompt`), `get_history` (GET `/history/{id}`), `get_image` (GET `/view`). Used by both production and max-tier paths (`quality_max.py:60` re-imports it from `phase_c_assembly`).

#### `ImageGenResult` — `phase_c_assembly.py:17`

`NamedTuple(path: str, api_name: str)`. `api_name` is the authoritative backend token: `COMFYUI_PULID | FLUX_KONTEXT | FLUX_PRO | FLUX_SCHNELL | POLLINATIONS | QUALITY_MAX`. Always truthy; callers use `if not result` for failure (None return).

#### `_fal_flux_fallback` — `phase_c_assembly.py:438`

FAL.ai priority chain: (1) FLUX Kontext Max Multi (up to 6 face refs, structured prompt with PRESERVE/CHANGE/CONSTRAIN/QUALITY blocks, `guidance_scale=3.5`, `aspect_ratio=16:9`) → (2) FLUX-Pro v1.1-ultra (no face-lock, 32 steps) → (3) FLUX Schnell (4 steps) → (4) Pollinations free API.

#### `_parse_structured_prompt` — `phase_c_assembly.py:420`

Parses `[SHOT][SCENE][ACTION][OUTFIT][QUALITY]` tagged sections from prompt. Returns dict of sections; falls back to full prompt as `SCENE` if no tags found.

#### `generate_ai_broll_max` — `quality_max.py:694`

Max-tier entry. Steps: classify shot → `get_max_quality_params` → apply UI overrides (7 halt knobs + 17 ComfyUI knobs via `_validate_overlay_value`) → probe pod `/object_info` → load `pulid_max.json` → optionally swap to HiDream-I1 → prune unavailable nodes → upload/cache refs → inject all axes → best-of-N loop → PuLID-boost retry if identity floor missed → `shutil.copyfile` best to output. Returns `ImageGenResult(path, "QUALITY_MAX")`.

#### `_probe_node_availability` — `quality_max.py:253`

One-time GET `/object_info` per `(process, server_url)` — returns set of available `class_type` strings. Failure is NOT cached (next call retries). Used by `_prune_unavailable` to conditionally strip unsupported nodes.

#### `_prune_unavailable` — `quality_max.py:364`

Strips nodes whose `class_type` is absent from the pod's `/object_info`. Pruning cascade with safe rewires: SLG→PAG→UNETLoader; FreeU→SLG; DiffDiff→FreeU; DetailDaemon→base sampler; LatentBlend→VAEEncode; LatentUpscale→None; FaceDetailer→VAEDecode-P2; ReActor→FaceDetailer; SUPIR nodes→None; final SaveImage feed wired to highest surviving node.

#### `_inject_identity` — `quality_max.py:461`

Wires LoRA (node 700: `lora_name`, `strength_model`, `strength_clip`), face anchor image (node 93: `image` = remote filename), and PuLID params (node 100: `weight`, `start_at`, `end_at`). Zero-strength LoRA when no `char_lora_path` (load runs, zero effect).

#### `_inject_conditioning` — `quality_max.py:509`

Wires prompt to node 122 (CLIPTextEncode), guidance to node 60 (FluxGuidance). When `prev_shot_remote` present: injects depth/canny/pose/tile ControlNet strengths (nodes 404/412/422/432). Drops pose channel (nodes 420/421/422) when no character or `cn_pose_strength <= 0.001`, rewires CN chain. Wires Redux style ref (node 810/804).

#### `_inject_sampling` — `quality_max.py:543`

Wires AYS steps (node 17), sampler (node 16), PAG scale (node 301), SLG scale + layers (node 770), FreeU v2 params (node 772), DetailDaemon amount (node 780).

#### `_inject_latent_source` — `quality_max.py:564`

Picks latent source: `EmptyLatentImage` (txt2img) or `LatentBlend(201, 102, ratio=0.15)` or `VAEEncode(init)` (img2img). Sets denoise on node 17 (`params["denoise_default"]`). Drops img2img nodes 200/201/250 for txt2img.

#### `_inject_post_passes` — `quality_max.py:587`

Enables/disables FaceDetailer (node 600: `guide_size`, `denoise=0.35`) and SUPIR (nodes 500–503: `steps`, `cfg_scale`). Sets final resolution at node 950 (default 3840×2160). Also rewires SaveImage (node 9) feed to highest surviving post-pass node.

#### `_swap_to_hidream` — `quality_max.py:200`

Replaces node 112 (UNETLoader→FLUX-Dev) with HiDream-I1-Full when pod has `HiDreamModelLoader|HiDreamI1Loader|HiDreamLoader` in `/object_info`. Strips PuLID nodes 97/99/100/101/93 (no HiDream PuLID equivalent). LoRA (node 700) survives. Returns `bool` indicating success.

#### `_validate_overlay_value` — `quality_max.py:144`

Validates/clamps UI overlay values against `_MAX_TIER_KNOB_SCHEMA` (17 sampler/CN/post-pass knobs + 8 halt knobs). Numeric: clamps to `[min, max]`, rejects bool masquerading as numeric. Enum: rejects unknown values. Bool: rejects non-bool. Unknown keys pass through (forward-compat).

#### `should_halt` — `face_validator_gate.py:227`

Composite-only halt rule: halt if `n >= halt_max_n` (budget exhausted) OR `n >= halt_min_n AND best.composite >= halt_threshold_composite`. Arc threshold is informational only (not enforced at halt time — already folded into composite via 0.6 weight). Returns `HaltDecision(halt, reason, best)`.

#### `score_candidate` — `face_validator_gate.py:170`

Scores one candidate: `arc_score` from ArcFace via `IdentityValidator.validate_image`, `aesthetic_score` from LAION Aesthetic v2 (lazy-loaded). Composite = `0.6 * arc + 0.4 * aesthetic`; missing component substituted with neutral 0.5. Returns `CandidateScore`.

#### `needs_regenerate` — `face_validator_gate.py:326`

Returns True if `best.arc_score < regenerate_floor_arc` AND `has_character` AND `best.has_arc`. Triggers one PuLID-boost retry in `generate_ai_broll_max` (weight += 0.15, capped at 1.0).

#### `classify_shot_type` — `workflow_selector.py:411`

Classifies shot into `portrait|medium|wide|action|landscape`. Priority: no characters → landscape; keyword match in `[SHOT]` section first, then full prompt+camera field; default → medium. Keywords: `quality_max.py:57` imports this for max-tier param lookup.

#### `get_workflow_params` — `workflow_selector.py:450`

Returns copy of `WORKFLOW_TEMPLATES[shot_type]`. Applies 4 per-project UI overrides when `settings` dict provided: `flux_guidance → guidance`, `comfyui_sampler → sampler`, `comfyui_steps → steps`, `continuity_options.img2img_denoise → denoise_default` (clamped [0.2, 0.6]).

#### `apply_workflow_params` — `workflow_selector.py:501`

Writes params into production `pulid.json` workflow in-place. Node map: 100 (ApplyPulid: weight/start_at/end_at), 60 (FluxGuidance), 17 (BasicScheduler: steps/scheduler), 16 (KSamplerSelect: sampler_name), 301 (PAG: scale). Does NOT override denoise (set by img2img logic).

#### `get_adaptive_pulid_weight` — `workflow_selector.py:540`

Computes adaptive PuLID weight from `identity_validator.get_rolling_stats(character_id)`. Applies `suggested_pulid_delta` to base weight. Smart gating: no boost for `FACE_ANGLE_EXTREME`; zero delta for `SMALL_FACE_REGION`. Clamped [0.0, 1.0].

#### `ContinuityEngine.enhance_shot_prompt` — `domain/continuity_engine.py:446`

Builds enhanced prompt (location fragment + character identity fragments + physics constraints + motion constraints) and `continuity_config` dict. Computes `use_img2img` (True if `approved_anchor_image` exists OR `TemporalConsistencyManager.should_use_img2img`), `scene_seed` (location seed or `hash(scene_id) % 2^31`), `denoise_strength` (context-aware: 0.30–0.55), adaptive `pulid_weight_override`. Returns `enhanced` dict with `continuity_config` key.

#### `KeyframeRenderPhase.run` — `cinema/phases/keyframe_render.py:68`

Iterates `project["scenes"][]["shots"]`, skips shots with `approved_keyframe_take_id` set, calls `shot_generator.generate_keyframe_take(scene_id, shot_id)`. Cancellation checked at scene and shot boundaries. Partial failures do NOT fail the phase (returns `ok=True` with counts).

#### `generate_keyframe_take` — `cinema/shots/controller.py:478`

Requires `shot["plan_status"] == "approved"`. Calls `continuity.enhance_shot_prompt` → optionally `llm.prompt_optimizer.optimize_shot_prompt` (cached on `shot["optimizer_cache"]`) → builds `PipelineContext(global_settings=settings)` → calls `generate_ai_broll` → validates identity with `IdentityValidator.validate_image` → appends take to `shot["keyframe_takes"]` → sets `shot["generated_image"]` → records cost. Returns `{"success": True/False, ...}`.

#### `approve_take` — `cinema/review/controller.py:647`

`approval_kind="keyframe"`: verifies take is in `keyframe_takes` collection, sets `shot["approved_keyframe_take_id"] = take_id`, saves project. The `KeyframeRenderPhase` skip gate (`shot.get("approved_keyframe_take_id")`) reads this field.

### Data IN → OUT

**IN:**
- `shot["prompt"]` (raw text from scene decomposer)
- `shot["characters_in_frame"]` list → primary character reference image (`.jpg` face anchor)
- `approved_anchor_image`: previous shot's approved keyframe (img2img init)
- `project["global_settings"]`: tier, sampler knobs, LoRA paths, style reference paths, UI overlay values
- `pulid.json` / `pulid_max.json`: baseline ComfyUI workflow graphs

**OUT:**
- JPEG file at `{project_dir}/shots/{shot_id}/{take_id}.jpg` (1344×768 production; 3840×2160 after SUPIR in max tier)
- `ImageGenResult(path, api_name)` — provenance token
- Take dict appended to `shot["keyframe_takes"]`
- Identity score in `take["metadata"]["identity_score"]`
- `take["metadata"]["identity_failure_reason"]` + `"suggested_pulid_adjustment"` on failure
- Cost record in `cost_tracker`

### Connects to

| Subsystem | How |
|---|---|
| `cinema/shots/controller.py` | Direct call: `generate_ai_broll(...)` from `generate_keyframe_take` at controller.py:476 |
| `domain/continuity_engine.py` | Direct call: `self.continuity.enhance_shot_prompt(...)` at controller.py:336 — provides `continuity_config` dict including `init_image`, `scene_seed`, `pulid_weight_override`, `primary_reference` |
| `workflow_selector.py` | Direct call: `classify_shot_type`, `get_workflow_params`, `apply_workflow_params`, `get_adaptive_pulid_weight` — imported in `phase_c_assembly.py:183` and `quality_max.py:57` |
| `face_validator_gate.py` | Direct call: `score_candidate`, `should_halt`, `select_best`, `needs_regenerate` — imported in `quality_max.py:50–56` |
| `identity/validator.py` | Shared singleton via `identity.get_shared_validator()` — used by `face_validator_gate._get_validator()` and directly in `generate_keyframe_take` at controller.py:506 for post-generation identity validation |
| `cinema/phases/keyframe_render.py` | `KeyframeRenderPhase` wraps `ShotControllerMixin.generate_keyframe_take` (proxied via `cinema_pipeline.py:235`); used in `cinema_pipeline.generate()` at line 994 |
| `cinema_pipeline.py` | `generate_keyframe_take` proxied via `ShotControllerMixin` at pipeline.py:235–236; `KeyframeRenderPhase` instantiated at pipeline.py:994 |
| `web_server.py` | HTTP endpoints: `POST /api/projects/<pid>/shots/<shot_id>/keyframes/generate` (line 1599) calls `generate_keyframe_take`; `POST .../keyframes/<take_id>/approve` (line 1624) calls `approve_take` |
| `llm/prompt_optimizer.py` | Optional call from `generate_keyframe_take` when `prompt_optimizer_enabled=True` (controller.py:391–442); caches result on `shot["optimizer_cache"]` |
| `cost_tracker.py` | `record_api_call(api_name, "keyframe_generation", shot_id, video_id)` at controller.py:562 — uses `result.api_name` as backend token |

### User-Facing Surface & Capability Knobs

All knobs write into `project["global_settings"]` via `PUT /api/projects/<pid>` with `{"global_settings": {...}}`.

**Tier selection:**
- `quality_tier`: `"production"` (default) | `"max"` — routes `generate_ai_broll` to the max-tier path

**Production tier sampler knobs** (applied via `get_workflow_params` → `apply_workflow_params`):
- `flux_guidance` (float): FluxGuidance node 60; per-type defaults 3.0–4.0
- `comfyui_sampler` (str): KSamplerSelect node 16; default `dpmpp_2m`
- `comfyui_steps` (int): BasicScheduler node 17; per-type defaults 20–25
- `continuity_options.img2img_denoise` (float, [0.2, 0.6]): BasicScheduler denoise when img2img active; also controls max-tier `denoise_default`

**Max-tier halt knobs** (UI: `MaxQualityTierSection.tsx`, 7 knobs):
- `max_candidate_count` (int, [1, 16]): total candidate budget; default 8
- `max_candidate_batch` (int, [1, 8]): candidates per batch iteration; default 4
- `max_halt_threshold_composite` (float, [0.70, 1.00]): halt when best composite >= this; portrait default 0.92
- `max_halt_threshold_arc` (float, [0.50, 1.00]): informational arc bar (not enforced at halt); portrait default 0.85
- `max_halt_min_n` (int, [1, 8]): minimum candidates before halt allowed; default 4
- `max_regenerate_floor_arc` (float, [0.50, 1.00]): ArcFace floor; below = PuLID-boost retry; portrait default 0.82
- `max_halt_rule` (`"composite_only"` | `"conjunctive"` | `"budget_only"`): halt logic mode
- `max_quality_parallel_workers` (int, [1, 4]): parallel ComfyUI submit/poll/download workers per batch

**Max-tier ComfyUI knobs** (UI: `AdvancedSection.tsx::MaxTierComfyControls`, 17 knobs):
- `slg_scale` (float, [0.0, 5.0]): SkipLayerGuidance scale, node 770
- `freeu_b1/b2/s1/s2` (float): FreeU v2 skip-connection amplification, node 772
- `ays_steps` (int, [15, 40]): AlignYourSteps steps, node 17
- `detail_daemon_amount` (float, [0.0, 1.0]): mid-sampling detail injection, node 780
- `controlnet_canny_strength` (float, [0.0, 0.5]): CN-Canny, node 412
- `controlnet_pose_strength` (float, [0.0, 0.6]): CN-Pose (DWPose), node 422
- `controlnet_tile_strength` (float, [0.0, 0.5]): CN-Tile, node 432
- `redux_strength` (`"high"` | `"medium"` | `"low"`): FLUX Redux style strength, node 804
- `hires_fix_enabled` (bool): LatentUpscale 1.5×, node 900; note: **Pass-2 denoise NOT currently injected** (quality_max.py:738–742); post-passes carry the lift instead
- `hires_fix_denoise` (float, [0.2, 0.6]): 2nd-pass BasicScheduler denoise
- `face_detailer_enabled` (bool): FaceDetailer Impact Pack, node 600
- `face_detailer_guide_size` (enum: 512 | 1024 | 2048): face region re-denoise crop
- `supir_enabled` (bool): SUPIR upscaler nodes 500–503
- `supir_steps` (int, [20, 100]): SUPIR sampling steps

**Identity knobs:**
- `identity_strictness` (float): overrides per-shot `identity_threshold` for `IdentityValidator.validate_image` after generation (controller.py:505)
- `adaptive_pulid` (bool, default True): enables rolling-stats adaptive PuLID weight override (domain/continuity_engine.py:535)
- `char_lora_paths` (dict `{char_id: path}`): per-character LoRA `.safetensors` for max-tier LoRA loader (node 700)
- `style_reference_paths` (list[str]): style board images → `style_reference` arg → Redux node 810

**Prompt optimizer:**
- `prompt_optimizer_enabled` (bool, default False): triggers `llm.prompt_optimizer.optimize_shot_prompt` before image gen; result includes `image_prompt`, `identity_anchor`, `negative_constraints`, `suggested_video_api`, `suggested_image_api`

**Per-shot image engine pin:**
- `shot["image_api"]` (str | `"AUTO"`): pin a specific image backend; overrides optimizer suggestion (controller.py:462–468); `"HIDREAM_I1"` triggers `_swap_to_hidream` in max tier

**Environment variables:**
- `COMFYUI_SERVER_URL`: RunPod endpoint (default `http://127.0.0.1:8188`); absence forces FAL fallback
- `FAL_KEY`: required for FLUX Kontext / FLUX-Pro fallbacks

**Quality maximization strategy (operator recipe):**
1. Set `quality_tier = "max"`, ensure `pulid_max.json` present and pod running
2. Set `max_candidate_count=8`, `max_halt_threshold_composite=0.95`, `max_halt_min_n=4`
3. Enable `prompt_optimizer_enabled=True` for cinematography-precise prompts
4. Provide `char_lora_paths` (rank-32 fp16 LoRA) and `style_reference_paths`
5. For portraits: `face_detailer_enabled=True`, `face_detailer_guide_size=1024`, `supir_enabled=True`, `supir_steps=50`
6. Set `ays_steps=30`, `slg_scale=2.5`, `detail_daemon_amount=0.6`
7. For landscapes: `slg_scale=2.8`, `controlnet_tile_strength=0.35`, `pag_scale=3.5`

### Control & Data Flow

1. **Pipeline trigger** — `KeyframeRenderPhase.run` iterates shots; skips any with `approved_keyframe_take_id` set; calls `shot_generator.generate_keyframe_take(scene_id, shot_id)` for each unapproved shot.

2. **`generate_keyframe_take`** (controller.py:314) — asserts `shot["plan_status"] == "approved"`. Calls `ContinuityEngine.enhance_shot_prompt` which: appends location/character/physics/motion fragments to prompt; computes `scene_seed`; resolves `init_image` (previous shot's approved keyframe path, or `TemporalConsistencyManager.last_generated_image`); decides `use_img2img`; computes `denoise_strength` (0.30–0.55 context-aware); optionally computes `pulid_weight_override` from rolling ArcFace stats.

3. **Prompt optimizer** (optional) — `optimize_shot_prompt` replaces `full_prompt`, overrides `identity_anchor`, `negative_constraints`, optionally pins `suggested_image_api`.

4. **`generate_ai_broll`** (phase_c_assembly.py:72):
   - **MAX branch**: dispatches to `generate_ai_broll_max`; on `None`/exception falls through to production.
   - **Production ComfyUI branch**:
     - Load `pulid.json`, deep-copy.
     - Call `classify_shot_type` → `get_workflow_params` → `apply_workflow_params` (injects PuLID weight/start/end, CFG, steps, scheduler, PAG scale by shot type).
     - Landscape with character → route to `_fal_flux_fallback` (no PuLID needed).
     - Upload face anchor → inject into node 93.
     - **ControlNet depth** (if `init_image`): dynamically inject nodes 400 (DepthAnythingV2), 401 (ControlNetLoader), 402 (ControlNetApplyAdvanced, strength from `wf_params["controlnet_depth_strength"]`, end at 50%). Rewire node 22 (BasicGuider) conditioning.
     - **Img2img** (if `init_image`): inject nodes 200 (LoadImage), 201 (VAEEncode). Rewire node 13 (SamplerCustomAdvanced) latent from node 102→201. Apply `effective_denoise` to node 17 (UI `img2img_denoise` overrides if present, clamped [0.2, 0.6]).
     - **IP-Adapter style transfer** (if `init_image`): inject nodes 410 (IPAdapterUnifiedLoader, `PLUS (high strength)`) and 411 (IPAdapterAdvanced, `weight_type="style transfer"`, end at 0.4, weight from `wf_params["ip_adapter_weight"]`). Rewire nodes 17 and 22 model inputs.
     - Queue prompt → poll `get_history` every 2s, timeout 600s (300 × 2). On success: download image, return `ImageGenResult(path, "COMFYUI_PULID")`. On timeout/error: fall to `_fal_flux_fallback`.

5. **MAX tier** (`generate_ai_broll_max`, quality_max.py:574):
   - Classify shot → `get_max_quality_params` → apply UI overlay (7 halt + 17 ComfyUI knobs) via `_validate_overlay_value`.
   - Optionally swap FLUX backbone to HiDream-I1 if `image_api == "HIDREAM_I1"` and pod has the node.
   - `_probe_node_availability` → `_prune_unavailable` (prune missing nodes with safe rewires).
   - Upload + SHA-cache character, init, style images.
   - Inject in 5 axis calls: `_inject_identity`, `_inject_conditioning`, `_inject_sampling`, `_inject_latent_source`, `_inject_post_passes`.
   - **Best-of-N loop**: `n_max` candidates in `candidate_batch` batches, deterministic seeds (`base_seed + i*1009`). Up to `parallel_workers` concurrent `_run_one_candidate` per batch via `ThreadPoolExecutor`. Each candidate: `score_candidate` (ArcFace + LAION Aesthetic v2). After each batch: `should_halt(composite_only rule)`.
   - Select `select_best(scores)`. If `needs_regenerate(best, regen_floor)`: retry once with `pulid_weight + 0.15` (capped 1.0), replace best if better.
   - `shutil.copyfile(best.image_path, output_filename)`. Return `ImageGenResult(path, "QUALITY_MAX")`.

6. **Post-generation** (controller.py:498): validate identity with `IdentityValidator.validate_image(img_path, primary_ref, character_id, threshold)`. Store score + failure reason + pulid adjustment hint in `take["metadata"]`. Append take to `shot["keyframe_takes"]`, set `shot["generated_image"]`, record cost.

7. **Approval** — operator calls `POST /api/projects/<pid>/shots/<shot_id>/keyframes/<take_id>/approve`. `approve_take` sets `shot["approved_keyframe_take_id"] = take_id`. `KeyframeRenderPhase` skip gate checks this field; downstream video generation reads it for the `init_image` chain.

### Gotchas, Divergences & Doc-Drift

1. **Production `ApplyPulid` vs max `ApplyPulidFlux`**: `pulid.json` uses SDXL-era `ApplyPulid`/`PulidModelLoader`/`PulidEvaClipLoader` (nodes 100/99/101). `pulid_max.json` uses FLUX-native `ApplyPulidFlux`/`PulidFluxModelLoader`/`PulidFluxEvaClipLoader`. These are incompatible node classes — mixing the wrong workflow with the wrong model would fail at queue time. Node 99 in production is `PulidModelLoader`; in max it is `PulidFluxModelLoader`.

2. **Production `pulid.json` upscale nodes (500–502) are Real-ESRGAN**, not SUPIR: node 500=`ImageUpscaleWithModel`, 501=`UpscaleModelLoader`, 502=`ImageScale`. Max-tier nodes 500–503 are `SUPIR_model_loader_v2`, `SUPIR_first_stage`, `SUPIR_sample`, `SUPIR_decode`. They share node IDs but are entirely different subsystems.

3. **Hires-fix pass-2 denoise NOT wired**: `quality_max.py:738–742` explicitly notes that hires-fix pass-2 (nodes 901/902) runs "whatever denoise the JSON baseline encodes" — no `_inject_sampling` step configures the 2nd-pass denoise. The `hires_fix_denoise` UI knob is accepted and clamped by `_validate_overlay_value` but effectively stored in `params["hires_fix_denoise"]` without a code path that writes it to node 901/17. Post-passes (FaceDetailer/SUPIR) carry the quality lift instead.

4. **ControlNet depth `cn_strength` variable scope bug in production path**: `phase_c_assembly.py:253` uses `wf_params.get("controlnet_depth_strength", 0.35) if 'wf_params' in dir() else 0.35`. The `'wf_params' in dir()` pattern is a footgun — `dir()` is not meant for local scope checking; this is effectively checking whether the name exists in the current scope (truthy in any normal execution where `workflow_selector` imported successfully), but it's fragile. The IP-Adapter weight at line 336 has the same pattern.

5. **`_upload_with_cache` lock gap**: `_upload_with_cache` (quality_max.py:295) checks cache under lock, drops lock, uploads, re-acquires to insert. Two concurrent threads on the same content both pass the cache check and both upload; `setdefault` means the first writer wins but the second upload is wasted bandwidth. This is documented as "acceptable correctness" but is a known inefficiency.

6. **`_probe_node_availability` empty-set return**: A failed probe returns an empty set, causing `_prune_unavailable` to no-op (`if not available: return`). All nodes are assumed present. A pod with missing custom nodes will then fail at queue time, not at probe time — harder to debug.

7. **`continuity_engine.py` (top-level) is a shim**: All code is in `domain/continuity_engine.py`. The 9-line top-level file does `from domain.continuity_engine import *`. New code should import from `domain.continuity_engine` directly.

8. **Landscape detection in production tier routes to FAL even with ComfyUI available**: `phase_c_assembly.py:198–200` — landscape + character_image → `_fal_flux_fallback(character_image=None)`. Landscape without character → also falls through to FAL in the `not server_url` branch. The ComfyUI PuLID path for landscapes is only hit if `server_url` and `pulid.json` exist AND `shot_type != "landscape"`.

9. **`halt_rule` enum accepted but not dispatched**: `_MAX_TIER_KNOB_SCHEMA` defines `max_halt_rule` as `enum("composite_only", "conjunctive", "budget_only")`. `should_halt` (face_validator_gate.py:225) implements only the composite-only rule; `halt_rule` param is never read at runtime. The knob is plumbed through the UI overlay and stored in `params["halt_rule"]` but `should_halt` doesn't accept a `halt_rule` parameter.

10. **Seed spread formula**: max-tier seeds are `base_seed + i * 1009` (quality_max.py:793). The prime multiplier ensures no aliasing within a 16-candidate budget but is hardcoded; the retry seed is `base_seed + n_max * 1009`.

11. **`denoise_default` in max tier for img2img**: `_inject_latent_source` (quality_max.py:481) writes `params.get("denoise_default", 1.0)` to node 17. This is 1.0 for txt2img mode (correct). For img2img, `denoise_default` is set by the UI overlay (`img2img_denoise` from `continuity_options`, clamped [0.2, 0.6]) at quality_max.py:688–690. If the UI value is absent, `denoise_default` remains at the shot-type template value (e.g., portrait=0.25) even in txt2img mode — a mismatch from the intended 1.0 txt2img default.

### Citations

| Claim | File:Line |
|---|---|
| `generate_ai_broll` signature, quality_tier dispatch | `phase_c_assembly.py:72–143` |
| MAX tier try/fallback block | `phase_c_assembly.py:114–143` |
| ComfyUI unavailability → FAL branch | `phase_c_assembly.py:157–168` |
| Workflow selector import + shot classification | `phase_c_assembly.py:183–202` |
| PuLID node injection, no-character strip | `phase_c_assembly.py:204–231` |
| ControlNet depth dynamic injection (nodes 400–402) | `phase_c_assembly.py:236–271` |
| Img2img VAEEncode injection (nodes 200–201) | `phase_c_assembly.py:275–316` |
| IP-Adapter injection (nodes 410–411), rewire 17/22 | `phase_c_assembly.py:318–354` |
| ComfyUI polling loop, 600s timeout | `phase_c_assembly.py:365–394` |
| `_fal_flux_fallback` Kontext prompt architecture | `phase_c_assembly.py:415–521` |
| `_parse_structured_prompt` | `phase_c_assembly.py:397–412` |
| `ImageGenResult` NamedTuple | `phase_c_assembly.py:15–29` |
| `RunPodComfyUI` class | `phase_c_assembly.py:32–71` |
| `_MAX_TIER_KNOB_SCHEMA` (17+8 knobs) | `quality_max.py:100–138` |
| `_validate_overlay_value` | `quality_max.py:141–182` |
| `_load_max_workflow` (module-level cache + lock) | `quality_max.py:185–194` |
| `_swap_to_hidream` | `quality_max.py:197–247` |
| `_probe_node_availability` | `quality_max.py:250–283` |
| `_upload_with_cache` | `quality_max.py:295–315` |
| `_prune_node` / `_prune_unavailable` | `quality_max.py:322–394` |
| `_inject_identity` | `quality_max.py:397–417` |
| `_inject_conditioning` (CN channel wiring) | `quality_max.py:419–446` |
| `_inject_sampling` | `quality_max.py:453–471` |
| `_inject_latent_source` (LatentBlend ratio 0.15) | `quality_max.py:474–494` |
| `_inject_post_passes` (FaceDetailer, SUPIR, 4K) | `quality_max.py:497–523` |
| `generate_ai_broll_max` entry point | `quality_max.py:574–599` |
| UI overlay application (7 halt + 17 ComfyUI knobs) | `quality_max.py:621–690` |
| Best-of-N loop, parallel workers, seed spread | `quality_max.py:744–821` |
| PuLID-boost retry logic | `quality_max.py:829–852` |
| Hires-fix Pass-2 NOT injected note | `quality_max.py:738–742` |
| `WORKFLOW_TEMPLATES` (5 shot types, production) | `workflow_selector.py:21–109` |
| `MAX_QUALITY_TEMPLATES` (5 shot types, max) | `workflow_selector.py:143–370` |
| `classify_shot_type` | `workflow_selector.py:411–447` |
| `get_workflow_params` (UI overlays: guidance/sampler/steps/denoise) | `workflow_selector.py:450–498` |
| `apply_workflow_params` (node map) | `workflow_selector.py:501–537` |
| `get_adaptive_pulid_weight` (feedback loop, smart gating) | `workflow_selector.py:540–580` |
| `CandidateScore` dataclass, DEFAULT_WEIGHTS | `face_validator_gate.py:153–165` |
| `score_candidate` | `face_validator_gate.py:168–211` |
| `should_halt` (composite-only rule) | `face_validator_gate.py:225–279` |
| `needs_regenerate` | `face_validator_gate.py:289–304` |
| `KeyframeRenderPhase.run` | `cinema/phases/keyframe_render.py:68–109` |
| `generate_keyframe_take` (plan gate, continuity wiring, optimizer, call) | `cinema/shots/controller.py:314–568` |
| `_resolve_previous_approved_keyframe` | `cinema/shots/controller.py:303–308` |
| `approve_take` (`approved_keyframe_take_id` write) | `cinema/review/controller.py:647–686` |
| `enhance_shot_prompt` (continuity_config construction) | `domain/continuity_engine.py:446–581` |
| `TemporalConsistencyManager.should_use_img2img`, `get_denoise_strength` | `domain/continuity_engine.py:350–416` |
| Production pulid.json node classes | `pulid.json` (22 nodes, verified via python3) |
| Max pulid_max.json node classes | `pulid_max.json` (56 nodes, verified via python3) |
| `COMFYUI_SERVER_URL` env var | `config/settings.py:126` |
| Keyframe generate/approve HTTP endpoints | `web_server.py:1599–1632` |
| `global_settings` update path | `web_server.py:506–507` |

---

## 10. identity/continuity/coherence — Character Consistency — Identity Validation, Continuity, Coherence, Characters & Locations

*Subsystem key: `identity-continuity`*

### Purpose

This subsystem guarantees that characters, locations, and visual properties remain coherent across every shot in a multi-scene production. It combines four continuity sub-engines (character identity/wardrobe, location prompt fragments, physics constraints, temporal img2img chaining), a unified identity validation stack with adaptive frame sampling and GhostFaceNet/ArcFace embeddings, a best-of-N face gate with aesthetic scoring, and a pixel-level coherence analyzer — all wired together to produce a `continuity_config` dict per shot and identity pass/fail scores that feed back into PuLID weight adaptation.

### Modules

| Path | Role | LOC |
|---|---|---|
| `continuity_engine.py` | Backward-compat shim — `from domain.continuity_engine import *` | 9 |
| `domain/continuity_engine.py` | Canonical: 4 sub-engines + `ContinuityEngine` orchestrator | 627 |
| `coherence_analyzer.py` | Color/lighting/composition coherence scoring between consecutive shots | 277 |
| `face_validator_gate.py` | N=8 best-of gate: ArcFace + LAION aesthetic composite scoring + adaptive halt | 304 |
| `character_manager.py` | Backward-compat shim | 9 |
| `domain/character_manager.py` | Character creation, multi-angle FLUX refs, embedding cache, voice assignment | 527 |
| `location_manager.py` | Backward-compat shim | 9 |
| `domain/location_manager.py` | Location creation, prompt fragments, seeds, optional Tavily image research | 214 |
| `generate_characters.py` | **Legacy standalone script** — reads a `characters.json` file, generates faces via FLUX-PRO ultra if missing; NOT wired into pipeline | 68 |
| `identity/__init__.py` | Package: public API, `make_validator()` factory, `get_shared_validator()` singleton | 100 |
| `identity/types.py` | Data classes: `FailureReason`, `FrameSample`, `CharacterIdentityResult`, `IdentityValidationResult`; threshold tables | 123 |
| `identity/validator.py` | `IdentityValidator`: GhostFaceNet embedding cache (disk+memory), adaptive frame sampling, per-frame diagnostics, rolling stats | 887 |
| `performance/identity_gate.py` | Performance-capture gate: single-frame ArcFace check on Act-One/LivePortrait output | 117 |

### Key functions & classes (THE MICRO LEVEL)

#### `domain/continuity_engine.py`

**`CharacterContinuityTracker.__init__`** (line 38)
Validates project dict via `_Project.model_validate(project)`, builds `self.characters = {c.id: project["characters"][i]}` (dict-reference, not model_dump — so mutations to the raw project dict are visible). Pre-loads GhostFaceNet embeddings for all characters via `get_character_embedding`.

**`CharacterContinuityTracker.build_character_prompt_fragment`** (line 65)
Params: `char_id`, `spatial_position`, `scene_context`. Injects wardrobe continuity from `appearance_log` + spatial position text. Does NOT add raw face descriptors (identity is bound by PuLID reference image, not text).

**`CharacterContinuityTracker.validate_multi_identity`** (line 118)
Legacy method — extracts 3 frames at 25%/50%/75%, calls `DeepFace.extract_faces` + `DeepFace.represent(model_name="GhostFaceNet")`, computes cosine similarity mapped to [0,1]. Threshold default 0.55. Returns `{"passed": bool, "results": {char_id: {"matched": bool, "similarity": float}}}`. **Superseded by `ContinuityEngine.validate_shot` → `IdentityValidator.validate_video`** — kept for backward compat.

**`LocationPersistence.get_seed`** (line 250) / **`get_prompt`** (line 253)
Delegates to `domain.location_manager.get_location_seed` / `get_location_prompt`. Provides the deterministic seed (`loc.seed`) and pre-built prompt fragment for location-locked generation.

**`PhysicsPromptEngineer.enforce_spatial_consistency`** (line 275)
Returns a string of physics constraints: character-position continuity, lighting direction matching, camera-cut labeling, real-world physics boilerplate. Appended to shot prompt.

**`PhysicsPromptEngineer.generate_motion_constraints`** (line 319)
Takes current + previous action strings; returns transition continuity clause.

**`TemporalConsistencyManager.should_use_img2img`** (line 350)
Returns `True` if same scene AND `last_generated_image` is set AND `shot_index > 0`.

**`TemporalConsistencyManager.get_denoise_strength`** (line 374)
Context-aware denoise:
- first shot: 0.55
- location change: 0.50
- same location shot_index ≤ 1: 0.40
- same location shot_index > 1: 0.30
Override via `global_settings.continuity_options.img2img_denoise` (clamped [0.2, 0.6]).

**`ContinuityEngine.__init__`** (line 429)
Instantiates all 4 sub-engines. Critically creates `self.identity_validator = make_validator(embedding_cache=..., cache_dir=<project_dir>/characters)` — the shared validator with disk-persistent embedding cache.

**`ContinuityEngine.enhance_shot_prompt`** (line 446)
Central shot augmentation. Returns a copy of the shot dict with:
- `enhanced["prompt"]`: original + location fragment + character fragments + physics + motion constraints
- `enhanced["continuity_config"]`: `{use_img2img, init_image, denoise_strength, location_seed, scene_seed, primary_character, primary_reference, multi_angle_refs, identity_anchor, identity_threshold, shot_type, pulid_weight_override, negative_constraints, approved_anchor_image}`

Key behavior: calls `classify_shot_type(shot)` → `get_threshold_for_shot(shot_type, mode="standard")` → if `adaptive_pulid` enabled, calls `get_adaptive_pulid_weight(shot_type, primary_char, self.identity_validator)`.

**`ContinuityEngine.validate_shot`** (line 587)
Params: `video_path`, `expected_chars`, `threshold`, `shot_type`, `mode`, `attempt`, `max_attempts`. Builds `configs = [{"id": cid, "reference_image": ref, "name": name}]` then delegates to `self.identity_validator.validate_video(...)`. Returns `IdentityValidationResult`.

#### `identity/validator.py`

**`IdentityValidator.__init__`** (line 53)
Params: `embedding_cache` (in-memory dict), `cache_dir` (disk .npy path), `vision_fallback` (callable for DeepFace-unavailable path). Maintains `self.history: List[IdentityValidationResult]` for rolling stats.

**`IdentityValidator.validate_video`** (line 131)
Adaptive video validation. Calls `_compute_sample_positions` → reads frames → `_analyze_frame` per position → `_aggregate_character` per char → `IdentityValidationResult`. Appends to `self.history`.

**`IdentityValidator._compute_sample_positions`** (line 365)
Density table by shot type: portrait=2.0×, medium=1.5×, action=1.5×, wide=1.0×, landscape=skip. Formula: `num_samples = int(duration * 2.0 * density)`, clamped [3, 10]. Always includes anchors at 10%, 50%, 90% of video.

**`IdentityValidator._analyze_frame`** (line 408)
For each detected face: computes face area ratio (`fw*fh/frame_area`), estimates face angle from bbox aspect ratio (frontal >0.75, three_quarter >0.55, profile ≤0.55), computes GhostFaceNet embedding, cosine similarity mapped to [0,1] via `(1+cos_sim)/2`. Best match per character across all detected faces in frame.

**`IdentityValidator.get_rolling_stats`** (line 266)
Window (default 10) over `self.history`. Returns `{mean_similarity, success_rate, common_failure, suggested_pulid_delta, sample_count}`. Delta logic: success_rate <0.5 → +0.10; <0.8 → +0.05; ==1.0 AND mean_sim >0.80 → -0.05 (allow creativity); else 0.

**`IdentityValidator._get_embedding`** (line 323)
Three-tier lookup: in-memory cache → disk .npy → compute via `DeepFace.represent(model_name="GhostFaceNet")`. Newly computed embeddings written to both memory and disk (`cache_dir/emb_{safe_key}.npy`).

**`IdentityValidator._compute_pulid_delta`** (line 684, static)
Per-result delta: matched AND sim >0.80 → -0.05; matched → 0.0; sim >0.55 → +0.05; else → +0.10.

#### `identity/types.py`

**`SHOT_TYPE_THRESHOLDS`** (line 92) — full table:
| shot_type | strict | standard | lenient |
|---|---|---|---|
| portrait | 0.75 | 0.70 | 0.60 |
| medium | 0.70 | 0.65 | 0.55 |
| wide | 0.60 | 0.55 | 0.45 |
| action | 0.65 | 0.60 | 0.50 |
| landscape | 0.0 | 0.0 | 0.0 |

**`get_threshold_for_shot`** (line 101)
`attempt=0` → returns `thresholds[mode]`. `attempt >= max_attempts-1` → returns `thresholds["lenient"]`. Between → linear interpolation mode→lenient.

#### `coherence_analyzer.py`

**`assess_coherence`** (line 215)
Params: `current_image`, `previous_image`, `scene_images` (optional list for palette comparison). Returns `SceneCoherenceResult`. Formula:

```
overall = (1.0 - color_drift) * 0.4 + lighting_consistency * 0.3 + composition_similarity * 0.3
```

- `color_drift`: HSV histogram correlation via `cv2.HISTCMP_CORREL`, inverted (0=consistent, 1=drifted). Triggers `adjust_color_prompt` if > 0.3.
- `lighting_consistency`: Sobel gradient direction comparison (angular diff / π, inverted). Triggers `match_lighting` if < 0.5.
- `composition_similarity`: `1 - min(brightness_delta * 2, 1.0)`. Triggers `tighten_denoise` if brightness_delta > 0.15.

Returns `valid=False` (not 0.0 scores) when either image fails `cv2.imread`. Callers MUST check `result.valid`.

#### `face_validator_gate.py`

**`score_candidate`** (line 168)
Params: `image_path`, `face_anchor`, `weights` (default `{"arc": 0.6, "aesthetic": 0.4}`), `threshold`. Calls `_arcface_score` → `IdentityValidator.validate_image` and `_aesthetic_score` → LAION Aesthetic Predictor v2. Missing component → neutral 0.5 for composite. Returns `CandidateScore`.

**`should_halt`** (line 225)
Composite-only decision: halt if `n >= halt_max_n` (budget exhausted) OR `n >= halt_min_n` AND `best.composite >= halt_threshold_composite` (default 0.92). Identity NOT gated separately at halt; it's folded into composite via 0.6 weight. `needs_regenerate` is the identity floor check (separate stage).

**`needs_regenerate`** (line 289)
Returns `True` if `best.arc_score < regenerate_floor_arc` AND `has_character=True`. Triggers PuLID +0.15 boost + one retry in `quality_max.py`.

#### `domain/character_manager.py`

**`create_character_with_images`** (line 104)
v2 flow: copy reference uploads → face-detect best upload as canonical (no synthetic fallback if DeepFace available) → FLUX Kontext MAX Multi generates 5 angle variants (45°, profile, back, smile, outdoor lighting) → assign voice (language+gender-aware) → pre-compute GhostFaceNet embedding → build identity anchor string.

**`_generate_multi_angle_refs`** (line 226)
Calls `fal-ai/flux-pro/kontext/max/multi` with `guidance_scale=4.0`, `aspect_ratio="3:4"`. Generates up to 5 angles beyond the canonical upload. These feed `get_multi_angle_refs` → Kling 3.0 Pro subject binding.

**`build_identity_anchor`** (line 477)
Returns `"{name}: {physical_traits}"` verbatim. This string is injected into every prompt unchanged — never rephrased by LLMs.

**`assign_voice`** (line 387)
Priority: direct preference match → language filter (via `domain.language_defaults`) + gender filter → language only → gender only → first unused → cycle. Closes VG-B1: prior path returned Rachel (English female) regardless of project language.

**`get_character_embedding`** (line 370)
Loads from `.npy` disk cache, or computes on-the-fly from `canonical_reference`.

#### `domain/location_manager.py`

**`create_location_with_images`** (line 41)
Params: `name`, `description`, `reference_image_paths`, `lighting`, `time_of_day`, `weather`, `auto_research` (default False). When `auto_research=True`, calls `research_engine.research_location_visual` → Tavily image search → downloads to `locations/<lid>/ref_research_N.jpg`.

**`build_location_prompt_fragment`** (line 117)
Assembles: `"Setting: {description}, {lighting_or_tod_default}, {weather_description}. Photorealistic, cinematic composition, rule of thirds"`. This string is stored in `location.prompt_fragment` and injected verbatim into all shots at this location.

**`get_location_seed`** (line 198)
Returns `loc.seed` — an integer persisted in the project dict, used as the ComfyUI seed for all images at this location, ensuring architectural consistency.

#### `workflow_selector.py`

**`get_adaptive_pulid_weight`** (line 540)
Params: `shot_type`, `character_id`, `identity_validator`, `base_params`, `settings`. Calls `identity_validator.get_rolling_stats(character_id)`. Computes `adapted = base_weight + delta`, clamped [0,1]. Smart suppression: if `common_failure == FACE_ANGLE_EXTREME` → delta capped at 0 (boosting PuLID won't fix angle). If `SMALL_FACE_REGION` → delta=0.

**`classify_shot_type`** (line 411)
Priority: no characters → "landscape"; keyword match in prompt+camera (portrait, action, wide, landscape, medium); default "medium".

**WORKFLOW_TEMPLATES** (line 21) — per shot-type PuLID weights (production tier):
| shot_type | pulid_weight | pulid_start_at | steps | guidance |
|---|---|---|---|---|
| portrait | 1.0 | 0.2 | 25 | 3.5 |
| medium | 0.9 | 0.25 | 20 | 3.5 |
| wide | 0.65 | 0.35 | 20 | 3.0 |
| action | 0.8 | 0.3 | 20 | 3.5 |
| landscape | 0.0 | 0.0 | 25 | 4.0 |

#### `performance/identity_gate.py`

**`validate_performance_take`** (line 93)
Extracts frame at 1s via ffmpeg, calls `IdentityValidator.validate_image` via shared singleton. Returns similarity [0,1] or None ("inconclusive"). Floor default 0.70.

### Data IN -> OUT

**IN:**
- Project dict (characters with `canonical_reference`, `multi_angle_refs`, `embedding_cache`, `physical_traits`; locations with `prompt_fragment`, `seed`; `global_settings` with `identity_strictness`, `adaptive_pulid`, `coherence_check_enabled`, `color_drift_sensitivity`)
- Shot dict (`prompt`, `characters_in_frame`, `camera`, `continuity_constraints`, `negative_constraints`)
- Scene dict (`location_id`, `action`, `id`)
- Previous shot dict (for img2img chaining)
- Generated image/video paths (for validation)

**OUT (per shot):**
- Enhanced shot dict: `prompt` (augmented), `continuity_config` dict with:
  - `use_img2img`, `init_image`, `denoise_strength` → ComfyUI workflow parameters
  - `location_seed`, `scene_seed` → passed to ComfyUI seed nodes
  - `primary_reference`, `multi_angle_refs`, `identity_anchor` → PuLID + Kling subject binding inputs
  - `identity_threshold`, `shot_type`, `pulid_weight_override` → gate thresholds + adaptive weight
- `IdentityValidationResult`: `passed`, `overall_score`, `character_results[cid].{best_similarity, mean_similarity, frame_results, primary_failure_reason, suggested_pulid_adjustment}`, `frames_sampled`, `threshold_used`
- `SceneCoherenceResult`: `overall_coherence_score`, `color_drift`, `lighting_consistency`, `composition_similarity`, `recommendations`, `valid`
- `CandidateScore`: `arc_score`, `aesthetic_score`, `composite`, `seed`
- Take metadata fields: `identity_score`, `identity_failure_reason`, `suggested_pulid_adjustment`

### Connects to

| Subsystem | How |
|---|---|
| `cinema/shots/controller.py` | Direct call: `continuity.enhance_shot_prompt()` at line 336 (keyframe) and 1072 (iteration); `continuity.validate_shot()` at line 888 (video validation after generation); `_get_shared_validator().validate_image()` at line 506 (image validation post-keyframe) |
| `workflow_selector.py` | Direct call from `ContinuityEngine.enhance_shot_prompt` → `classify_shot_type`, `get_adaptive_pulid_weight`; `apply_workflow_params` applies `continuity_config.pulid_weight_override` to ComfyUI Node 100 |
| `quality_max.py` | Direct call: `score_candidate`, `should_halt`, `needs_regenerate`, `select_best` from `face_validator_gate`; reads `identity_strictness` from project settings |
| `domain/project_manager.py` | Data handoff: `get_character`, `get_location`, `mutate_project` (for `get_location_prompt` lazy-build); provides project dict to all subsystems |
| `cinema/core.py` | Instantiates `ContinuityEngine(project)` at line 111; stores in `PipelineCore.continuity` |
| `cinema_pipeline.py` | Refreshes `ContinuityEngine.character_tracker` and `location_persistence` on project snapshot reload (line 431) |
| `phase_c_vision.py` | `_get_shared_validator()` (alias for `identity.get_shared_validator()`) used by controller; `validate_identity_vision` is wired as the `vision_fallback` in `make_validator()` |
| `performance/identity_gate.py` | Shares `get_shared_validator()` singleton; rolling stats from performance takes accumulate in same validator history |
| ComfyUI (via `generate_ai_broll`) | Receives `continuity_config` fields: `use_img2img`, `init_image`, `denoise_strength`, `location_seed`, `primary_reference` (for PuLID Node 100), `pulid_weight_override` |
| Kling API | Receives `multi_angle_refs` list for Kling 3.0 Pro subject binding |

### User-facing surface & capability knobs

All knobs live in `project.global_settings` (set via `PUT /api/projects/<pid>` with `{"global_settings": {...}}`):

| Setting | Default | Effect | Maximize quality with |
|---|---|---|---|
| `identity_strictness` | 0.60 | Override threshold for keyframe image validation in `cinema/shots/controller.py:504` and N=8 scoring in `quality_max.py:767` | Set to 0.70–0.75 for portrait shots |
| `adaptive_pulid` | True | Enables rolling-stats PuLID weight adjustment. False → static template weight | Keep True; disable only for debugging |
| `coherence_check_enabled` | True | Enables per-shot `assess_coherence` comparison | Keep True |
| `color_drift_sensitivity` | 0.3 | Threshold for `adjust_color_prompt` recommendation (higher = more tolerant) | Lower to 0.2 for very tight color grading |
| `coherence_threshold` | 0.6 (not in defaults, read with this fallback at controller.py:1667) | Overall coherence floor below which `regenerate` is recommended | Raise to 0.65–0.70 for consistent scenes |
| `flux_guidance` | per-template | Overrides ComfyUI FluxGuidance node | 3.5–4.0 for character shots |
| `comfyui_sampler` | `dpmpp_2m` | ComfyUI sampler selection | `dpmpp_2m` is already optimal |
| `comfyui_steps` | per shot-type | Override step count | 25+ for portrait, 20 for medium |
| `continuity_options.img2img_denoise` | per shot-type | Override TemporalConsistencyManager denoise | 0.25–0.30 for same-location consecutive shots |
| `max_quality_parallel_workers` | 1 | N=8 batch parallelism (capped to 4) | Set to 4 if RunPod has spare CPU |
| Character creation: `ip_adapter_weight` | 0.85 | IP-Adapter weight stored on character object | 0.85–0.95 for highest identity lock |
| Location creation: `auto_research` | False | Fetch Tavily real photos as additional location refs | Set True when no reference images are available |

**To maximize identity consistency:**
1. Upload multiple real front-facing reference photos per character (not synthetic) — `_find_canonical_from_uploads` picks the best-face-detected one.
2. Let multi-angle generation run (FLUX Kontext Max Multi — 5 additional angles; requires `FAL_KEY`).
3. Set `identity_strictness=0.70` for close-up/portrait shots.
4. Keep `adaptive_pulid=True` — the rolling stats system self-calibrates PuLID weight per character.
5. Use `quality_tier="max"` (N=8 best-of) which engages `face_validator_gate`.
6. For Kling generation, `multi_angle_refs` are automatically bound as subject references.

### Control & data flow

1. **Character creation** (`POST /api/projects/<pid>/characters`):
   Upload → `create_character_with_images` → face-detect best upload → `_generate_multi_angle_refs` (FLUX Kontext Max Multi × 5 angles) → compute GhostFaceNet embedding → save to `characters/<cid>/embedding.npy` → `build_identity_anchor` stores `"{name}: {traits}"` on character dict.

2. **Location creation** (`POST /api/projects/<pid>/locations`):
   → `create_location_with_images` → `build_location_prompt_fragment` (description + lighting defaults + weather) → stored as `location.prompt_fragment`; `location.seed` set by `make_location`.

3. **Pipeline core construction** (`build_pipeline_core`):
   → `ContinuityEngine(project)` instantiates all 4 sub-engines, pre-loads character embeddings into `CharacterContinuityTracker.embeddings`, creates `IdentityValidator(embedding_cache=..., cache_dir=<project>/characters)`.

4. **Per-shot prompt enhancement** (`ContinuityEngine.enhance_shot_prompt`):
   - Concat: original prompt + `get_location_prompt(loc_id)` + per-character `build_character_prompt_fragment` + `enforce_spatial_consistency` + `generate_motion_constraints` + continuity_notes.
   - Classify shot → `get_threshold_for_shot(shot_type, "standard")`.
   - If `adaptive_pulid` → `get_adaptive_pulid_weight` → queries `IdentityValidator.get_rolling_stats` → computes delta → clamps weight [0,1].
   - Compute denoise via `TemporalConsistencyManager.get_denoise_strength`.
   - Assemble `continuity_config` dict.

5. **Keyframe generation** (controller keyframe flow):
   → `enhance_shot_prompt` → image generated by ComfyUI (PuLID Node 100 uses `primary_reference`, weight from `pulid_weight_override`) → `_get_shared_validator().validate_image(img_path, primary_ref, threshold=identity_strictness)` → scores stored in take metadata.

6. **N=8 max-quality generation** (`quality_max.generate_ai_broll_max`):
   → per candidate: `score_candidate(path, face_anchor, threshold=identity_strictness)` → ArcFace + LAION aesthetic → composite. `should_halt(scores, halt_threshold_composite=0.92)` checked after each batch. If `needs_regenerate(best, regen_floor)` → PuLID weight +0.15 retry.

7. **Video identity validation** (controller post-video-gen):
   → `continuity.validate_shot(video_path, [primary_char], shot_type, ...)` → `IdentityValidator.validate_video` → `_compute_sample_positions` (adaptive 3–10 frames) → `_analyze_frame` per frame (DeepFace face detection → per-face GhostFaceNet embedding → cosine sim) → `_aggregate_character` (best/mean/min/failure reason/PuLID delta) → `IdentityValidationResult` → appended to `self.history`.

8. **Coherence check** (controller post-keyframe, `_run_quality_diagnostics`):
   → `assess_coherence(current_image, prev_approved_image)` → `color_drift`, `lighting_consistency`, `composition_similarity` → recommendations (`adjust_color_prompt`, `match_lighting`, `tighten_denoise`, `regenerate`) stored in diagnostic record.

9. **Rolling stats feedback loop** (next shot's `enhance_shot_prompt`):
   → `IdentityValidator.get_rolling_stats(char_id, window=10)` reads accumulated history → if success_rate <0.5 → next shot's PuLID weight gets +0.10; if consistently high → -0.05.

### Gotchas, divergences & doc-drift

**Skill doc claims `identity_validator.py` / `identity_types.py`** — CONFIRMED WRONG paths. Real locations: `identity/validator.py` (887 LOC) and `identity/types.py` (123 LOC). The `identity/` package did not exist under those flat names.

**Skill doc claims `phase_b_audio.py`** for the audio phase — no such file exists. Unrelated to this subsystem but reflects the broader skill-doc drift.

**Top-level shims (`continuity_engine.py`, `character_manager.py`, `location_manager.py`) are NOT canonical** — they are 9-line `from domain.X import *` re-export shims preserved for old import paths. New code imports from `domain.` directly. The shims' docstrings mention `main.py` as a consumer, but `main.py` was deleted.

**`generate_characters.py` is a legacy standalone script**, not integrated into the pipeline. It reads a `characters.json` file at the repo root (does not exist in normal pipeline operation) and generates face images via `fal-ai/flux-pro/v1.1-ultra`. The pipeline uses `domain/character_manager.create_character_with_images` instead.

**`validate_multi_identity` on `CharacterContinuityTracker`** (`domain/continuity_engine.py:35`) is superseded by `ContinuityEngine.validate_shot` → `IdentityValidator.validate_video`. The legacy method is still present but `IdentityValidator.__init__` docstring at `identity/validator.py:45` explicitly names it as replaced.

**`TemporalConsistencyManager.record_shot_generated` / `reset_scene`** — `ContinuityEngine.record_shot_generated` (`line 583`) and `reset_scene` (`line 625`) exist but have NO callers in the production pipeline (verified: `grep -rn "record_shot_generated\|continuity\.reset_scene"` returns only test files and the class definitions themselves). Temporal img2img chaining relies instead on `approved_anchor_image` passed explicitly to `enhance_shot_prompt` via `_resolve_previous_approved_keyframe` in the controller. The in-memory `last_generated_image` mechanism is functionally dead.

**`coherence_threshold`** is read in `cinema/shots/controller.py:1667` with a fallback of 0.6, but it is NOT scaffolded in `domain/project_manager.py`'s default `global_settings` dict. Must be set manually via `PUT /api/projects/<pid>`.

**`CharacterContinuityTracker` holds dict references** (not model_dump copies) to `project["characters"][i]`. This is intentional (preserves mutation visibility) but means that if upstream code replaces the project dict entirely (as `_refresh_project_snapshot` does in `cinema_pipeline.py:443`), the tracker's `self.characters` becomes stale. The pipeline code re-instantiates the tracker on snapshot reload.

**`IdentityValidator.vision_fallback` is required for DeepFace-unavailable path** — if constructed directly without `make_validator()`, the fallback is None and calling `validate_image` / `validate_video` when `DEEPFACE_AVAILABLE=False` raises `RuntimeError`. Always use `identity.make_validator()` or `identity.get_shared_validator()`.

**LAION Aesthetic v2 is optional** (`aesthetics_predictor` package + `shunk031/aesthetics-predictor-v2-sac-logos-ava1-l14-linearMSE`). If unavailable, `_aesthetic_score` returns None and the composite uses neutral 0.5 for that axis — so ArcFace alone drives selection.

**`face_validator_gate._get_validator`** previously held a local singleton; now delegates to `identity.get_shared_validator()`. Behavior change: the shared instance has `vision_fallback` wired (was `None` in the old per-module singleton), so an ArcFace-ambiguous frame may trigger a small Claude Vision call.

**`DEFAULT_PERFORMANCE_FLOOR = 0.70`** in `performance/identity_gate.py:31` is the same as `IDENTITY_THRESHOLD = 0.70` in `domain/character_manager.py:32`, but they are NOT the same variable. The character manager constant is used only for documentation/import; the actual runtime threshold for keyframe validation comes from `identity_strictness` project setting (default 0.60).

**`get_workflow_params` `img2img_denoise` override** (`workflow_selector.py:493`) writes to `params["denoise_default"]` not `params["denoise_strength"]` — `denoise_default` is used only within `get_workflow_params` return value, but `ContinuityEngine.enhance_shot_prompt` computes its own denoise via `TemporalConsistencyManager.get_denoise_strength` and ignores `denoise_default`. The `continuity_options.img2img_denoise` setting therefore only affects the `get_workflow_params` dict; it is NOT currently plumbed through to the temporal manager's per-shot denoise computation.

### Citations

- `continuity_engine.py:1–9` — shim declaration
- `domain/continuity_engine.py:1–11` — module docstring listing 4 subsystems
- `domain/continuity_engine.py:35–63` — `CharacterContinuityTracker.__init__`
- `domain/continuity_engine.py:65–95` — `build_character_prompt_fragment`
- `domain/continuity_engine.py:118–227` — `validate_multi_identity` (legacy)
- `domain/continuity_engine.py:234–255` — `LocationPersistence`
- `domain/continuity_engine.py:261–332` — `PhysicsPromptEngineer`
- `domain/continuity_engine.py:339–417` — `TemporalConsistencyManager`
- `domain/continuity_engine.py:423–581` — `ContinuityEngine` including `enhance_shot_prompt`
- `domain/continuity_engine.py:523–539` — adaptive_pulid gate
- `domain/continuity_engine.py:587–623` — `validate_shot`
- `domain/continuity_engine.py:583–628` — `record_shot_generated` / `reset_scene` (uncalled)
- `identity/types.py:19–85` — data classes
- `identity/types.py:92–98` — `SHOT_TYPE_THRESHOLDS` table
- `identity/types.py:101–123` — `get_threshold_for_shot` with interpolation
- `identity/__init__.py:40–55` — `make_validator` factory
- `identity/__init__.py:58–86` — `get_shared_validator` singleton
- `identity/validator.py:41–63` — `IdentityValidator.__init__`
- `identity/validator.py:131–264` — `validate_video`
- `identity/validator.py:266–310` — `get_rolling_stats` with delta logic
- `identity/validator.py:316–363` — `_get_embedding` three-tier cache
- `identity/validator.py:365–406` — `_compute_sample_positions` (adaptive sampling)
- `identity/validator.py:408–534` — `_analyze_frame`
- `identity/validator.py:684–693` — `_compute_pulid_delta`
- `coherence_analyzer.py:20–36` — `SceneCoherenceResult` dataclass
- `coherence_analyzer.py:38–116` — `ColorCoherenceAnalyzer`
- `coherence_analyzer.py:119–195` — `CompositionAnalyzer`
- `coherence_analyzer.py:215–277` — `assess_coherence` with formula
- `face_validator_gate.py:1–17` — module docstring (N=8 strategy)
- `face_validator_gate.py:152–211` — `score_candidate`, `DEFAULT_WEIGHTS`
- `face_validator_gate.py:225–304` — `should_halt`, `needs_regenerate`
- `domain/character_manager.py:31–34` — `IDENTITY_THRESHOLD` constants
- `domain/character_manager.py:104–196` — `create_character_with_images`
- `domain/character_manager.py:226–339` — `_generate_multi_angle_refs` (FLUX Kontext Max Multi)
- `domain/character_manager.py:370–384` — `get_character_embedding`
- `domain/character_manager.py:387–459` — `assign_voice`
- `domain/character_manager.py:462–527` — `get_reference_image`, `build_identity_anchor`, `get_multi_angle_refs`
- `domain/location_manager.py:41–114` — `create_location_with_images`
- `domain/location_manager.py:117–160` — `build_location_prompt_fragment`
- `domain/location_manager.py:163–214` — `get_location_prompt`, `get_location_seed`, `get_location_reference`
- `workflow_selector.py:21–133` — `WORKFLOW_TEMPLATES`, `SHOT_TYPE_KEYWORDS`
- `workflow_selector.py:411–447` — `classify_shot_type`
- `workflow_selector.py:540–580` — `get_adaptive_pulid_weight`
- `domain/project_manager.py:310–356` — project defaults including `identity_strictness:0.60`, `adaptive_pulid:True`
- `cinema/core.py:53,111` — `ContinuityEngine` instantiation in `build_pipeline_core`
- `cinema/shots/controller.py:336–342` — `enhance_shot_prompt` call at keyframe gen
- `cinema/shots/controller.py:500–520` — `validate_image` call with `identity_strictness`
- `cinema/shots/controller.py:888–896` — `validate_shot` call post-video-gen
- `cinema/shots/controller.py:1648–1669` — `assess_coherence` call with `coherence_threshold` fallback
- `performance/identity_gate.py:31,93–117` — `DEFAULT_PERFORMANCE_FLOOR`, `validate_performance_take`
- `phase_c_vision.py:15–26` — `_get_shared_validator` backward-compat alias
- `phase_c_vision.py:242–265` — `validate_identity_vision` Claude Vision fallback
- `quality_max.py:760–851` — N=8 best-of loop with `score_candidate`, `should_halt`, `needs_regenerate`
- `generate_characters.py:12–68` — legacy standalone script (NOT pipeline-integrated)

---

## 11. post-proc/assembly/audio — Post-Processing & Final Assembly (Phase C + Audio)

*Subsystem key: `post-assembly`*

### Purpose

Transforms approved per-shot AI-generated clips into a finished cinema-grade MP4. This subsystem covers every step that runs after video generation: face-swap for identity correction, lip-sync (overlay on existing video or full talking-head generation), frame interpolation (RIFE) and upscaling (SeedVR2/Topaz), per-character LoRA training, and the FFmpeg assembly pipeline that applies color grading, stitches scene transitions, mixes dialogue/BGM/foley, and normalises to EBU R128.

The audio side generates dialogue TTS (ElevenLabs multi-turn or per-line; Cartesia for Korean), BGM (Suno V5 or FAL Stable Audio), environmental foley (Stability AI), word-level forced alignment (WhisperX/Whisper), and voice DSP (Pedalboard/AU/FFmpeg presets). All audio paths converge into a 3-track mix at the final FFmpeg assembly step.

### Modules

| Path | Role | Verified LOC |
|---|---|---|
| `phase_c_ffmpeg.py` | Video routing (all AI video APIs), FFmpeg assembly helpers: concat, xfade, color grade, speed adjust, loudnorm, motion QA | 1350 |
| `phase_c_vision.py` | Face swap (fal.ai PixVerse → FaceFusion CLI), GPT-4o shot QC, Claude identity validation, Gemini coherence check; frame extraction helpers | 422 |
| `lip_sync.py` | Lip sync modes: overlay (mouth-only, MuseTalk/LatentSync/SyncV2/SyncV3) and generation (full talking-head, Hedra/Kling/Omnihuman/Aurora); RIFE frame interpolation; SeedVR2 cloud upscale; SyncNet quality gate | 860 |
| `phase_c_assembly.py` | Image generation (ComfyUI+PuLID, FLUX Kontext, FLUX-Pro, Pollinations); img2img mode with ControlNet depth + IP-Adapter style transfer; quality-tier dispatch ("max" delegates to `quality_max`) | 582 |
| `prep/lora_training.py` | Per-character LoRA dataset prep + ai-toolkit subprocess trainer + status I/O; quality validation stub (ArcFace gate planned) | 555 |
| `prep/topaz_upscale.py` | Topaz Video AI local CLI wrapper (`tvai-cli` / `ffmpeg`+tvai_up filter); model selection by content type | 151 |
| `audio/dialogue.py` | Multi-character TTS via ElevenLabs v3 Dialogue Mode (2+ speakers) or per-line loop; Cartesia Sonic 2 for Korean; forced alignment sidecar | 515 |
| `audio/music.py` | BGM: Suno V5 → FAL Stable Audio router; music mastering (Pedalboard/FFmpeg); 25+ mood presets with BPM/key/reference | 427 |
| `audio/foley.py` | Environmental foley via Stability AI Stable Audio 2.0; 15+ environment prompts | 188 |
| `audio/effects.py` | Pedalboard effect chain builder; macOS AU plugin host; 13 FFmpeg voice-FX presets; `apply_voice_effect` router | 284 |
| `audio/alignment.py` | Forced alignment: WhisperX (wav2vec2) → vanilla Whisper word timestamps; `AlignmentResult`/`WordTiming` schema; thread-safe model cache | 288 |
| `audio/voiceover.py` | Voice delivery → ElevenLabs VoiceSettings mapper | 307 |
| `audio/_client.py` | Shared ElevenLabs singleton | 17 |

### Key functions & classes (THE MICRO LEVEL)

#### phase_c_ffmpeg.py

**`generate_ai_video`** (`phase_c_ffmpeg.py:43`)
Routes an image → video to one of 9+ AI video engines. Params: `image_path`, `camera_motion`, `target_api`, `output_mp4`, `pacing`, `character_id`, `attempted_apis` (dedup list), `multi_angle_refs` (up to 6 character reference images), `_cascade_retries`, `negative_prompt` (shot-type-aware auto-built if None), `shot_type`, `video_fallbacks` (custom fallback order list), `driving_video_path` (performance-capture video for Veo/Sora/Runway), `has_dialogue` (triggers native audio on VEO_NATIVE/landscape), `ctx` (PipelineContext for api_engines filter + cascade_retry_limit), `_cascade_out` (mutable dict; written with `cascade_metadata` on success). Returns: `output_mp4` path or `None`. Internally defines `try_next_api()` which reads `ctx.api_engines` to filter cascade; `_record_video_cascade()` writes the winning engine name + attempt list.

**`stitch_modules`** (`phase_c_ffmpeg.py:769`)
FFmpeg concat demuxer on a list of normalized MP4 paths → single `final_output` MP4 using `-c copy`. No re-encode. Raises `subprocess.CalledProcessError` on failure.

**`split_video_into_segments`** (`phase_c_ffmpeg.py:795`)
Splits a combined storyboard MP4 into per-segment clips using `-ss`/`-t` (stream-copy). Last segment runs to EOF to absorb float accumulation drift. Returns list of absolute paths. Used after Kling storyboard generation to recover per-shot clips.

**`assess_motion_quality`** (`phase_c_ffmpeg.py:894`)
OpenCV Farneback optical-flow analysis on N sampled frames. Returns `{smoothness_score, artifact_frames, frozen_ratio, recommendation: "accept"|"interpolate"|"regenerate"}`. Thresholds: `frozen_ratio > 0.5` → regenerate; `smoothness < 0.4` → interpolate; `artifact_frames > 30% of pairs` → regenerate.

**`COLOR_GRADE_PRESETS`** (`phase_c_ffmpeg.py:1006`)
Dict of 8 named FFmpeg eq/curves filter chains: `warm_cinema`, `cool_noir`, `vibrant`, `desaturated`, `golden_hour`, `moonlight`, `high_contrast`, `pastel`.

**`apply_color_grade`** (`phase_c_ffmpeg.py:1018`)
Applies a preset filter chain or custom `.cube`/`.3dl` LUT via FFmpeg `lut3d`. Params: `video_path`, `output_path`, `preset` (default `warm_cinema`), `lut_path` (optional). Re-encodes with `libx264 -preset fast`. Returns `output_path` or `None`.

**`adjust_speed`** (`phase_c_ffmpeg.py:1057`)
Speed multiplier via `setpts` (video) + chained `atempo` (audio; handles values outside 0.5–2.0 by chaining). Params: `video_path`, `output_path`, `factor` (0.5 = half-speed/slow-mo, 2.0 = double).

**`two_pass_loudnorm`** (`phase_c_ffmpeg.py:1103`)
EBU R128 two-pass loudness normalization. Pass 1: measure; parses `loudnorm` JSON from stderr. Pass 2: normalize with measured values (`linear=true`). Defaults: -14 LUFS / 11 LU / -1.5 dBTP (YouTube/Netflix). Video stream copied; only audio re-encoded to AAC 192k. Returns `bool`; caller replaces input file on `True`.

**`_probe_duration`** (`phase_c_ffmpeg.py:1202`) / **`_has_audio_stream`** (`phase_c_ffmpeg.py:1212`)
ffprobe helpers. `_has_audio_stream` detects whether a clip has any audio stream — used by xfade to decide the acrossfade path.

**`_build_xfade_filtergraph`** (`phase_c_ffmpeg.py:1232`)
Builds a chained `xfade`+`acrossfade` filtergraph string. Three audio-presence cases: (a) all inputs have audio → raw acrossfade; (b) no inputs have audio → video-only, `alab=None`; (c) mixed → `anullsrc`-pad silent legs, normalize every leg to `48kHz stereo fltp` before acrossfade (Lane V #25 M1 fix). Returns `(filter_complex, video_label, audio_label)`.

**`xfade_concat`** (`phase_c_ffmpeg.py:1301`)
Public entry point: probes durations, clamps transition to `0.4 * min(durations)`, calls `_build_xfade_filtergraph`, runs single FFmpeg re-encode. Re-encodes to `libx264 -crf 20` + `aac 192k`. Raises on FFmpeg failure (caller falls back to hard-cut concat). Lane V #24 F1: was erroring silently on silent-video inputs; fixed by `_has_audio_stream` guard.

#### phase_c_vision.py

**`_get_shared_validator`** (`phase_c_vision.py:16`)
Backward-compat alias for `identity.get_shared_validator()`. Returns the process-wide `IdentityValidator` singleton. Referenced in `ARCHITECTURE.md §15` smoke test.

**`get_middle_frame`** (`phase_c_vision.py:30`) / **`extract_frame_at`** (`phase_c_vision.py:41`)
OpenCV frame extractors. `extract_frame_at` takes a `position_ratio` (0.0–1.0).

**`face_swap_video_frames`** (`phase_c_vision.py:53`)
Priority 1: fal.ai PixVerse cloud swap (`fal-ai/pixverse/swap` endpoint, uploads video + face reference); Priority 2: FaceFusion CLI (`--face-swapper-model inswapper_128_fp16 --face-enhancer-model gfpgan_1.4 --execution-providers cpu`). Returns output path or `None` on total failure. Requires `settings.fal_key` for cloud path.

**`quality_control_image`** (`phase_c_vision.py:108`)
Wraps `validate_shot_quality_vision`; returns `bool` (pass if score >= 7). Default-passes when OpenAI key missing or image absent.

**`validate_shot_quality_vision`** (`phase_c_vision.py:144`)
GPT-4o-Vision scored QC (0–10) against 6 criteria: composition, lighting, face clarity, outfit accuracy, prompt adherence, artifact detection. Returns `{score, issues, pass, suggestions, source}`. Pass threshold: 7/10. Default-passes on any failure.

**`validate_identity_vision`** (`phase_c_vision.py:236`)
Claude Sonnet (claude-sonnet-4-6) compares reference vs generated face. Ignores clothing/background/pose. Returns `{confidence 0.0–1.0, issues, match (bool, threshold 0.7), source}`. Default-passes on missing key/image.

**`validate_scene_coherence_vision`** (`phase_c_vision.py:345`)
Gemini 2.5-flash checks ≤3 consecutive shot images for lighting direction, wardrobe, background, spatial position, and color palette continuity. Returns `{coherent: bool, issues, source}`.

#### lip_sync.py

**`PrerequisiteResult`** (`lip_sync.py:47`)
Dataclass: `passed: bool, mode: str, warnings: List[str], blockers: List[str]`.

**`check_overlay_prerequisites`** (`lip_sync.py:54`)
Validates inputs for MuseTalk overlay mode: video ≥ 0.5s, width ≥ 256px (warning), audio ≥ 0.5s, duration within 2× ratio. Returns `PrerequisiteResult`.

**`check_generation_prerequisites`** (`lip_sync.py:119`)
Validates inputs for Omnihuman generation mode: image ≥ 512×512, audio ≤ 60s (blocker), audio > 30s (warning: 720p only). Returns `PrerequisiteResult`.

**`lipsync_overlay`** (`lip_sync.py:177`)
Mode 1 — mouth-only overlay on existing video. Cascade: SyncV3 → MuseTalk → LatentSync → SyncV2. Each engine's output is scored by `validate_lipsync_quality`; if below threshold it's stashed; best-of-failed returned at cascade end. Writes `cascade_metadata` to `_cascade_out` dict. Requires `FAL_KEY`.

**`validate_lipsync_quality`** (`lip_sync.py:373`)
Returns sync confidence [0.0, 1.0]. Provider chain: (1) SyncNet (`SyncNetInstance.evaluate` — external dependency); (2) duration-match heuristic (each 1% drift costs 5 pts); (3) neutral 1.0 fallback. Never raises.

**`_sync_gate_settings`** (`lip_sync.py:429`)
Reads `lipsync_quality_validation` (bool) and `lipsync_validation_threshold` (float, default 0.65) from per-project `global_settings` dict. Returns `(enabled, threshold)`.

**`lipsync_generation`** (`lip_sync.py:470`)
Mode 2 — full talking-head from still image + audio. Cascade: Hedra Character-3 → Kling native lip sync → Omnihuman v1.5 → Creatify Aurora. Same SyncNet gate + best-of-failed recovery as overlay. Params: `resolution` ("720p"/"1080p"), `turbo` (bool), `settings` (project global_settings dict), `_cascade_out`.

**`generate_lip_sync_video`** (`lip_sync.py:680`)
Smart router. If `existing_video_path` present → overlay mode; else → generation mode. `mode` param: "auto" | "overlay" | "generation".

**`generate_rife_interpolation`** (`lip_sync.py:733`)
Cloud RIFE via `fal-ai/rife/video`. Params: `num_frames` (1–4; 2 = 3× FPS), `use_scene_detection` (prevent smearing at cuts). Returns output path or `None`.

**`upscale_video_seedvr2`** (`lip_sync.py:789`)
Cloud upscale via `fal-ai/seedvr/upscale/video`. Params: `target_resolution` ("1080p", "2160p"). `noise_scale=0.1`, `output_quality="high"`, `output_format="X264 (.mp4)"`. Temporally consistent (no frame-to-frame flicker). Returns output path or `None`.

**`extract_last_frame`** (`lip_sync.py:845`)
FFmpeg `sseof -0.1` to extract last frame as JPEG for shot chaining.

#### phase_c_assembly.py

**`RunPodComfyUI`** (`phase_c_assembly.py:34`)
HTTP client for ComfyUI API on RunPod. Methods: `upload_image`, `queue_prompt`, `get_image`, `get_history`. Polling with 300-iteration timeout (600s).

**`generate_ai_broll`** (`phase_c_assembly.py:74`)
Primary image generator. Priority chain: (1) `quality_max.generate_ai_broll_max` when `quality_tier=="max"`; (2) ComfyUI+PuLID via RunPod when `comfyui_server_url` + `pulid.json` present; (3) `_fal_flux_fallback`. In ComfyUI path, injects: `workflow["122"]` (prompt), `workflow["102"]` (1344×768 latent), `workflow["25"]` (seed), `workflow["93"]` (PuLID face image), DepthAnything V2 ControlNet (nodes 400/401/402) for spatial lock, img2img VAEEncode (nodes 200/201) for temporal chaining, IP-Adapter style transfer (nodes 410/411). For landscape shots: skips PuLID entirely, routes to Kontext.

**`_fal_flux_fallback`** (`phase_c_assembly.py:438`)
FAL image fallback. Priority: FLUX Kontext Max Multi (up to 6 refs, structured PRESERVE/CHANGE/CONSTRAIN prompt) → FLUX-Pro ultra → FLUX Schnell → Pollinations (free). Returns `ImageGenResult(path, api_name)` or `None`.

#### prep/lora_training.py

**`DEFAULT_TRAIN_CONFIG`** (`prep/lora_training.py:101`)
`rank=32, alpha=32, lr=1e-4, steps=3000, batch_size=1, resolution=1024, dtype=fp16, save_every=500, optimizer=adamw8bit, scheduler=constant, noise_offset=0.05`. Calibrated for FLUX-Dev LoRA portrait training on RTX 4090 (~30 min).

**`LoraStatus`** (`prep/lora_training.py:118`)
Dataclass persisted to `<project>/loras/<char_id>/status.json`: `char_id, status, progress_percent, started_at, finished_at, lora_path, quality_score, image_count, config, error, log_tail`.

**`prepare_character_lora_dataset`** (`prep/lora_training.py:161`)
Stages reference images to `<project>/loras/<char_id>/dataset/` with per-image `.txt` captions. Hard-links when possible. Validates minimum 15 images. Writes `dataset_manifest.json`. Returns `{dataset_dir, image_count, caption_strategy, trigger_token, manifest_path}`. Path-traversal-safe via `_safe_under`.

**`train_character_lora`** (`prep/lora_training.py:431`)
Blocking orchestration: (1) dataset prep; (2) trainer detection (`ai-toolkit` > `kohya`); (3) subprocess run via `_run_ai_toolkit`; (4) `.safetensors` location in output dir; (5) `validate_lora_quality` (currently stub, returns `LORA_VALIDATION_SKIPPED=-1.0`). Returns `{success, lora_path, quality_score, status}`. Updates `status.json` at each phase for UI polling.

#### prep/topaz_upscale.py

**`upscale_with_topaz`** (`prep/topaz_upscale.py:75`)
Local Topaz Video AI CLI wrapper. Detects `tvai-cli`/`veai`/`ffmpeg+tvai_up` via `_detect_cli`. Model selection: `auto` → `prob-3` (Proteus, general); `cinema` → `rhea-1` (grain preserved); `interview` → `gaia-cg-1` (talking heads); `vfx` → `iris-2`; `stylized` → `artemis-3`; `low_quality` → `thd-3`. Params: `scale` (2 or 4), `target_fps` (optional, triggers `tvai_fi` frame interpolation), `target_resolution` ("4k"|"8k"). 1-hour subprocess timeout. Returns `None` if CLI missing (caller falls back to SeedVR2).

#### audio/dialogue.py

**`generate_cartesia`** (`audio/dialogue.py:130`)
Cartesia Sonic 2 REST POST to `https://api.cartesia.ai/tts/bytes`. Params: `text`, `voice_id`, `output_path`, `language` (ISO code), `model_id` ("sonic-2"). Caches by output path existence. Never raises; returns bool. Requires `CARTESIA_API_KEY`.

**`_resolve_tts_provider`** (`audio/dialogue.py:211`)
Reads `scene["language"]` → `character["language"]` → `settings.language_pref` cascade. Korean + Cartesia key present → `"CARTESIA_SONIC_2"`; else → `"ELEVENLABS"`.

**`_try_dialogue_mode`** (`audio/dialogue.py:310`)
ElevenLabs v3 Dialogue Mode via `client.text_to_dialogue.convert`. Requires ≥2 distinct speakers with explicit `voice_id`. Needs SDK with `text_to_dialogue` attribute (graceful fallback on AttributeError). Returns path or `None`.

**`generate_dialogue_voiceover`** (`audio/dialogue.py:419`)
Path 1: Dialogue Mode (if enabled, 2+ speakers). Path 2: per-line loop. Per-line: routes to Cartesia (Korean) → ElevenLabs (else). Voice delivery mapped by `get_voice_direction`. Lines concatenated via FFmpeg with configurable silence (default 0.3s). Emits `.alignment.json` sidecar if `forced_alignment_enabled`.

**`_maybe_save_alignment`** (`audio/dialogue.py:385`)
Gate on `forced_alignment_enabled` in project settings. Calls `audio.alignment.align_audio_to_text`, writes JSON sidecar at `<audio>.alignment.json`.

#### audio/music.py

**`MUSIC_MASTERING_PRESETS`** (`audio/music.py:32`)
6 presets: `none`, `cinema_master` (-14 LUFS, 3:1 comp, room reverb), `lo_fi`, `epic_wide` (-12 LUFS, wide stereo), `intimate_acoustic` (-16 LUFS), `dark_ambient`. Each has both `pedalboard` (Pedalboard chain) and `ffmpeg` (filter string) definitions.

**`generate_suno_v5`** (`audio/music.py:139`)
Suno V5 via sunoapi.org REST API. Polls `GET /api/v1/generate/record-info` every 5s up to `poll_timeout_s=240`. Downloads via `requests` with browser User-Agent (CDN blocks `Python-urllib`). Returns `bool`. Requires `SUNO_API_KEY` + `SUNO_API_BASE`.

**`generate_bgm`** (`audio/music.py:259`)
Router: Suno V5 → FAL Stable Audio. `prefer_provider`: "AUTO", "SUNO_V5", or FAL path.

**`generate_fal_bgm`** (`audio/music.py:283`)
FAL Stable Audio via `fal-ai/stable-audio`. 25+ `vibe_prompts` with BPM/key/instrumentation/texture. Optionally enhanced with `research_engine.research_music_reference` (Tavily). `seconds_total` param (default 42).

**`master_music`** (`audio/music.py:386`)
Priority: AU plugin (if `au_plugin` param) → Pedalboard chain → FFmpeg filter fallback. Resolves preset from `MUSIC_MASTERING_PRESETS`.

#### audio/foley.py

**`_build_foley_prompt`** (`audio/foley.py:30`)
Maps 15 environment keys (rain, crowd, traffic, forest, ocean, fire, kitchen, etc.) to elaborated Stable Audio prompt strings. Falls through to raw string for unknown keys.

**`generate_stability_foley`** (`audio/foley.py:110`)
Stability AI Stable Audio 2.0 via `POST https://api.stability.ai/v2beta/audio/stable-audio-2/text-to-audio`. Multipart form. Params: `duration` (capped at 190s), `steps` (50), `cfg_scale` (7.0), `seed` (optional). Caller-controlled cache (skips if output_path exists). Never raises. Requires `STABILITY_API_KEY`.

#### audio/alignment.py

**`WordTiming`** / **`AlignmentResult`** (`audio/alignment.py:47`)
Dataclasses. `WordTiming`: `word, start_s, end_s, confidence`. `AlignmentResult`: `audio_path, duration_s, words, provider, transcript`.

**`align_audio_to_text`** (`audio/alignment.py:217`)
Provider chain: WhisperX (wav2vec2 forced alignment, language-pinned) → vanilla Whisper (`word_timestamps=True`). Models are cached in thread-safe dicts (`_MODEL_LOCK`). Language mapping via `_LANG_NAME_TO_CODE`. Returns `AlignmentResult` or `None`.

**`save_alignment_json`** / **`load_alignment_json`** (`audio/alignment.py:255, 271`)
JSON sidecar I/O at `<audio>.alignment.json`.

#### audio/effects.py

**`VOICE_EFFECTS`** (`audio/effects.py:28`)
13 FFmpeg-filter presets: `cinema_reverb`, `intimate_room`, `cathedral`, `telephone`, `radio`, `megaphone`, `underwater`, `dream_sequence`, `robot`, `warm_broadcast`, `whisper_intimate`, `vintage_film`, `epic_narrator`.

**`apply_au_plugin`** (`audio/effects.py:88`)
Loads installed macOS AU `.component` from `/Library/Audio/Plug-Ins/Components/` or `~/Library/`. Uses Pedalboard `load_plugin` + `AudioFile` I/O. Sets named plugin parameters via `setattr`. Returns processed path or original on failure.

**`apply_pedalboard_chain`** (`audio/effects.py:156`)
Applies chain of `{type, params}` effect dicts using Pedalboard built-ins (Reverb, Compressor, Gain, Delay, HighpassFilter, LowpassFilter, Chorus, Distortion). Cross-platform. Returns processed path or original on failure.

**`apply_voice_effect`** (`audio/effects.py:230`)
Top-level router: AU plugin > Pedalboard chain > FFmpeg filter.

### Data IN -> OUT

**IN (per shot, Phase C):**
- Approved final take MP4 path (from `motion_takes` or `postprocess_variants`)
- Character reference image(s) for face swap / lip sync
- Per-scene dialogue audio MP3 (from `_ensure_scene_audio` / `generate_dialogue_voiceover`)
- Per-scene foley MP3 (from `_ensure_scene_foley` / `generate_stability_foley`)
- BGM MP3 (from `_ensure_bgm` / `generate_bgm`)
- Project `global_settings` dict (gate knobs, presets, mode overrides)

**OUT:**
- `{export_dir}/final_cinema.mp4` — 1920×1080@30fps, H.264, AAC 192k, EBU R128 normalized, with color grade, scene transitions (optional), dialogue+BGM+foley 3-track mix
- Per-shot `postprocess_variants` entries in project JSON (face_swap, lip_sync, rife, upscale, color_grade, speed variants stored as separate takes)
- `<shot>_ls.mp4` lip-synced take registered with `lipsync_score` metadata
- `<audio>.alignment.json` sidecar with word-level timestamps
- `<project>/loras/<char_id>/output/<char_id>.safetensors` per-character LoRA weights
- `<project>/loras/<char_id>/status.json` training state

### Connects to (other subsystems)

| Connection | Mechanism |
|---|---|
| `cinema/shots/controller.py` | **Direct call** — imports `face_swap_video_frames`, `generate_lip_sync_video`, `generate_rife_interpolation`, `upscale_video_seedvr2` (`controller.py:92–96`); calls them in `apply_correction` and during mandatory F1b lipsync pass at take generation time |
| `cinema_pipeline.py` | **Direct call** — `_assemble_final` imports `xfade_concat`, `apply_color_grade` from `phase_c_ffmpeg`; `_apply_final_loudnorm` imports `two_pass_loudnorm`; `_ensure_bgm` calls `master_music`; `_ensure_scene_foley` calls `generate_stability_foley` |
| `cinema/auto_approve.py` | **Shared state (persisted field)** — reads `take["metadata"]["lipsync_score"]` and `take["metadata"]["audio_embedded"]` to gate auto-approval; `final_min_lipsync` threshold default 0.8 (`auto_approve.py:98`) |
| `domain/scene_decomposer.py` (API_REGISTRY) | **Direct reference** — `cinema/shots/controller.py:1081` imports `API_REGISTRY` to check `native_audio` flag on winning engine; VEO_NATIVE is the only live engine with `native_audio: True` (`domain/scene_decomposer.py:43`) |
| `phase_c_assembly.py` (image gen) | **Direct import** — `cinema/shots/controller.py:90` imports `generate_ai_broll`; used for keyframe generation in Phase B |
| `audio/_client.py` | **Shared state (singleton)** — `dialogue.py` imports the ElevenLabs `client` singleton; thread-safe reuse |
| `config/settings.py` | **Direct reference** — all modules read API keys (`fal_key`, `elevenlabs_api_key`, `cartesia_api_key`, `stability_api_key`, `suno_api_key`, `anthropic_api_key`, `openai_api_key`, `runwayml_api_secret`, `comfyui_server_url`) |
| `cost_tracker.py` | **Direct call** — `CostTracker().record_api_call()` called in `generate_suno_v5`, `generate_fal_bgm`, `generate_stability_foley`, `generate_dialogue_voiceover` (both ElevenLabs + Cartesia paths), and lipsync paths in `controller.py` |
| `identity/` package | **Direct call** — `phase_c_vision._get_shared_validator()` delegates to `identity.get_shared_validator()` for the process-wide IdentityValidator |

### User-facing surface & capability knobs

All knobs live in `project["global_settings"]` dict unless noted. To maximize quality, set these:

| Knob | Key | Values / Default | Quality lever |
|---|---|---|---|
| **Color grade preset** | `color_grade_preset` | Any `COLOR_GRADE_PRESETS` key (default `warm_cinema`); overridden per-mood in `_assemble_final` (`cool_noir` for suspense, `golden_hour` for romantic, etc.) | Set to `high_contrast` for action; `golden_hour` for romance |
| **Custom LUT** | (params to `apply_correction`) | `lut_path` param in `apply_correction(action="color_grade", params={lut_path: "..."})` | `.cube`/`.3dl` LUT for studio-grade grade |
| **Scene transitions** | `scene_transitions` | `bool` (default `False`) | Enable for dissolve between scenes |
| **Transition duration** | `transition_duration` | `float` seconds (default 0.5) | Longer dissolves are smoother |
| **Music mood** | `music_mood` | 25+ vibe keys (suspense, romantic, epic, etc.) | Drives both Suno V5 and FAL prompt |
| **Music mastering** | `music_mastering` | Keys in `MUSIC_MASTERING_PRESETS` (default `cinema_master`) | `epic_wide` for blockbuster; `none` to keep raw |
| **BGM provider** | (not yet surfaced as global_settings; controlled in `generate_bgm` `prefer_provider`) | "AUTO", "SUNO_V5" | SUNO_V5 for vocals/songs; FAL for instrumentals |
| **Lip sync mode** | `lip_sync_mode` | "auto" | "overlay" | "generation" (default "auto") | Force "generation" for dedicated talking-head shots; "overlay" for cinematic motion shots |
| **Lip sync quality threshold** | `lipsync_validation_threshold` | float [0,1] (default 0.65) | Raise to 0.8+ to enforce higher sync quality; pipeline tries more engines until cleared |
| **Lip sync validation toggle** | `lipsync_quality_validation` | bool (default True) | Disable to skip SyncNet gate entirely (lower latency, no quality bar) |
| **Face swap gate** | `face_swap_enabled` | bool (default True) | Set to False to globally disable face swap corrections |
| **API engine filter** | `api_engines` | `{ENGINE_NAME: {enabled: false}}` | Disable specific engines from cascade (e.g., force Kling-only) |
| **Cascade retry limit** | `cascade_retry_limit` | int (default 1) | Raise for unreliable API environments |
| **Dialogue mode** | `dialogue_mode_enabled` | bool (default True) | Forces ElevenLabs v3 Dialogue Mode for 2+ speaker scenes (best prosody continuity) |
| **Forced alignment** | `forced_alignment_enabled` | bool (default False) | Enables `.alignment.json` sidecar (word-level timestamps; better lip sync precision) |
| **Language** | `language` | "English", "Korean", etc. | Routes Korean → Cartesia Sonic 2; sets Whisper language hint |
| **VEO native audio** | (automatic) | `generate_ai_video(has_dialogue=True)` triggers `generate_audio=True` for VEO_NATIVE on dialogue shots | VEO_NATIVE is the only live native-audio engine; use it for dialogue close-ups to get voice+video generated together |
| **LoRA training** | `char_lora_paths` (set by `train_character_lora`) | dict {char_id: lora_path} in global_settings | Train with 25–50 varied reference images; FLUX rank-32 LoRA is the single biggest identity-quality lever |
| **Topaz upscale** | (invocation only) | `prep/topaz_upscale.upscale_with_topaz(model="cinema", scale=4)` | Requires local Topaz Video AI license + tvai-cli on PATH; `rhea-1` model best for final-master cinematic footage |
| **SeedVR2 upscale** | (apply_correction) | `action="upscale"` | Cloud path, no local deps; `target_resolution="2160p"` for 4K output |
| **RIFE interpolation** | (apply_correction or diagnose trigger) | `action="rife"`, `num_frames=2` (default) | `num_frames=4` for 5× FPS smooth slow-mo |
| **img2img denoise** | `continuity_options.img2img_denoise` | float [0.2, 0.6] (default caller-supplied) | Lower = more temporal consistency; higher = more creative divergence per shot |
| **PuLID weight** | per-shot adaptive | `pulid_weight_override` param in `generate_ai_broll` | Auto-adapted by continuity engine feedback loop; ComfyUI node `"100"` |
| **Coherence check** | `coherence_check_enabled` | bool (default True) | Enables Gemini coherence + color drift scoring in diagnose |
| **Color drift threshold** | `color_drift_sensitivity` | float (default 0.3) | Lower = more aggressive color_grade recommendation |

### Control & data flow

1. **Per-shot take generation** (`controller.py:generate_motion_take`):
   - `generate_ai_video` called with `target_api` (from prompt_optimizer suggestion or project default), `has_dialogue`, `multi_angle_refs`, `driving_video_path`
   - VEO_NATIVE with `has_dialogue=True` generates audio-embedded take (`audio_embedded=True` tagged in metadata)
   - Non-embedded dialogue takes: mandatory F1b lipsync pass runs immediately after video download, calls `generate_lip_sync_video(mode="auto")` → writes `lipsync_score` to metadata

2. **Per-scene audio** (`cinema_pipeline._ensure_scene_audio`):
   - `generate_dialogue` (LLM) → `generate_dialogue_voiceover` → Dialogue Mode (if 2+ speakers) or per-line TTS (Cartesia/ElevenLabs) → cached in `self.scene_audio[scene_id]`
   - Optional: `_maybe_save_alignment` writes `.alignment.json` sidecar

3. **Per-scene foley** (`cinema_pipeline._ensure_scene_foley`):
   - Aggregates `shot["scene_foley"]` descriptors → `_build_foley_prompt` → `generate_stability_foley` → cached in `self.scene_foley[scene_id]`

4. **BGM** (`cinema_pipeline._ensure_bgm`):
   - `generate_fal_bgm` (Stable Audio) → `master_music` (Pedalboard or FFmpeg preset)

5. **Manual correction cycle** (`controller.apply_correction`):
   - `face_swap`: `face_swap_video_frames` (fal PixVerse → FaceFusion) → stored as `postprocess_variant`
   - `lip_sync`: `generate_lip_sync_video` (overlay or generation cascade with SyncNet gate) → stored as `postprocess_variant`
   - `rife`: `generate_rife_interpolation` (fal RIFE cloud) → stored as `postprocess_variant`
   - `upscale`: `upscale_video_seedvr2` (fal SeedVR2 cloud) → stored as `postprocess_variant`
   - `color_grade`: `apply_color_grade` → stored as `postprocess_variant`
   - `speed`: `adjust_speed` → stored as `postprocess_variant`

6. **Diagnostic** (`controller.diagnose_clip`):
   - `assess_motion_quality` (optical flow) → `recommendation` ("accept"/"interpolate"/"regenerate")
   - `_get_shared_validator().validate_image` → identity score; if failed → recommends `face_swap`
   - `assess_coherence` → color drift; if > threshold → recommends `color_grade`
   - Recommendations written to `diagnostic_history` on project

7. **Final assembly** (`cinema_pipeline._assemble_final`):
   a. Collect approved clips from scene_data
   b. Normalize all clips: `ffmpeg scale=1920:1080 pad fps=30 libx264 aac`
   c. Stitch: hard-cut concat (`-c copy`) OR `xfade_concat` (if `scene_transitions=True`)
   d. Color grade: `apply_color_grade` with mood-mapped preset
   e. Audio mix: 3-track amix: voice (1.0) + BGM (0.12) + foley (0.20); voice source = `[0:a]` if embedded or `[N:a]` standalone dialogue track; `-shortest` for standalone path; `duration=longest` for amix when standalone
   f. `_apply_final_loudnorm`: two-pass EBU R128 → in-place replace

### Gotchas, divergences & doc-drift

1. **`phase_b_audio.py` does not exist at repo root or in `cinema/phases/`** — the skill source-map names it, but the real audio subsystem is `audio/` package (`dialogue.py`, `music.py`, `foley.py`, `effects.py`, `alignment.py`, `voiceover.py`). Verified: `find /Users/hyungkoookkim/Content -name "phase_b_audio.py" -not -path "*worktree*"` returns only worktree copies, none in the live source tree.

2. **Worktree copies** — `lip_sync.py`, `phase_c_*.py`, `phase_b_audio.py` appear under `.claude/worktrees/*/`; canonical versions are at repo root only.

3. **xfade_concat audio mixed-presence bug (Lane V #25 M1)** — Fixed at `phase_c_ffmpeg.py:1275–1298`. Engines like Kling-Native produce clips without an audio stream; engines like Veo with `generate_audio=True` embed audio. Mixed scenes would drop embedded audio. Fix: `_has_audio_stream` probes each clip; silent legs get `anullsrc` padding; all legs normalized to `48kHz stereo fltp` before acrossfade.

4. **xfade_concat video-only path (Lane V #24 F1)** — Fixed. When ALL inputs lack audio, `alab=None` and the FFmpeg command omits `-map [alab]` and `-c:a` entirely. Downstream `_assemble_final` handles the dialogue mux separately regardless.

5. **`validate_lora_quality` is a stub** (`prep/lora_training.py:515`) — returns `LORA_VALIDATION_SKIPPED=-1.0`. ArcFace gate planned but not implemented. `train_character_lora` sets `quality_score=None` when sentinel is returned.

6. **Topaz path is local-only** — `prep/topaz_upscale.py` is a no-op unless `tvai-cli`/`veai`/`ffmpeg+tvai_up` is on PATH. No cloud fallback; callers must handle `None` return and fall back to `upscale_video_seedvr2`.

7. **Lipsync gate uses settings dict, not `config.settings.Settings`** — `_sync_gate_settings` reads from the per-project `global_settings` dict. Calling it with no args defaults to `(True, 0.65)`. The `config.settings.Settings` object (env-derived) never carried `lipsync_quality_validation` or `lipsync_validation_threshold`.

8. **SyncNet scoring requires `syncnet_python` package** — not in project requirements; if absent, falls back to duration-match heuristic which only catches gross mismatches (20%+ length discrepancy), not subtle drift.

9. **Dialogue-mode SDK version sensitivity** — `_try_dialogue_mode` catches `AttributeError` if the installed ElevenLabs SDK doesn't expose `client.text_to_dialogue`. Falls through silently to per-line loop. No version pin enforces the required SDK shape.

10. **Suno CDN `403` with default urllib UA** — `generate_suno_v5` downloads with a browser User-Agent via `requests` (`_SUNO_DOWNLOAD_UA`). Legacy `urllib.request.urlretrieve` calls in the same file (other providers) do NOT have this workaround.

11. **BGM mastering uses `generate_fal_bgm` directly** in `_ensure_bgm` (`cinema_pipeline.py:627`), bypassing `generate_bgm`'s Suno→FAL router. To use Suno V5 for BGM, the pipeline would need to call `generate_bgm` with `prefer_provider="AUTO"` instead.

12. **`_assemble_final` reads mood from `settings.get("mood")` not from per-scene mood** — the color grade preset is a single project-level value mapped from `global_settings["mood"]`. All scenes get the same grade.

13. **`assess_motion_quality` requires OpenCV** — uses `cv2.calcOpticalFlowFarneback`; not gracefully skipped if `cv2` is absent. `diagnose_clip` would raise at `from phase_c_ffmpeg import assess_motion_quality` if `cv2` not installed.

14. **`face_swap_video_frames` uses FaceFusion with CPU-only execution providers** — the CLI call hardcodes `--execution-providers cpu`. GPU-accelerated FaceFusion requires changing this to `cuda` or `coreml`.

15. **`phase_c_assembly.py` is the image-generation module** — the skill source-map implies this file is about "assembly"; it is actually the keyframe/broll image generator (ComfyUI+PuLID, FLUX Kontext). The actual final-video assembly is in `cinema_pipeline._assemble_final` calling `phase_c_ffmpeg`.

16. **VEO_NATIVE is the only `native_audio: True` engine in API_REGISTRY** (`domain/scene_decomposer.py:43`). Sora-Native, Kling-Native, etc. all produce silent video. The F1b mandatory lipsync pass covers all non-embedded dialogue takes.

17. **`foley_audio_paths` is populated via `_runstate.foley_audio_paths`** — `_ensure_scene_foley` appends to `self._runstate.foley_audio_paths`; `_assemble_final` reads `self.foley_audio_paths`. If `_runstate` is not yet initialized (e.g., direct `assemble_approved_takes` call without a full pipeline run), foley track is empty.

### Citations

- `phase_c_ffmpeg.py:43` — `generate_ai_video` signature
- `phase_c_ffmpeg.py:91–101` — `_record_video_cascade` closure
- `phase_c_ffmpeg.py:122–179` — `try_next_api` fallback cascade + `api_engines` filter + `cascade_retry_limit`
- `phase_c_ffmpeg.py:265–290` — VEO_NATIVE `generate_audio` flag (`shot_type=="landscape" or has_dialogue`)
- `phase_c_ffmpeg.py:769–788` — `stitch_modules` (concat demuxer)
- `phase_c_ffmpeg.py:795–887` — `split_video_into_segments` (storyboard split)
- `phase_c_ffmpeg.py:894–998` — `assess_motion_quality` (optical flow; thresholds at lines 955–997)
- `phase_c_ffmpeg.py:1006–1015` — `COLOR_GRADE_PRESETS`
- `phase_c_ffmpeg.py:1018–1054` — `apply_color_grade`
- `phase_c_ffmpeg.py:1057–1100` — `adjust_speed` (atempo chain)
- `phase_c_ffmpeg.py:1103–1195` — `two_pass_loudnorm`
- `phase_c_ffmpeg.py:1212–1224` — `_has_audio_stream`
- `phase_c_ffmpeg.py:1232–1298` — `_build_xfade_filtergraph` (mixed audio-presence fix)
- `phase_c_ffmpeg.py:1301–1350` — `xfade_concat`
- `phase_c_vision.py:15–26` — `_get_shared_validator`
- `phase_c_vision.py:52–104` — `face_swap_video_frames` (PixVerse → FaceFusion)
- `phase_c_vision.py:153–239` — `validate_shot_quality_vision` (GPT-4o)
- `phase_c_vision.py:242–343` — `validate_identity_vision` (Claude)
- `phase_c_vision.py:346–422` — `validate_scene_coherence_vision` (Gemini)
- `lip_sync.py:1–23` — module docstring (mode overview)
- `lip_sync.py:44–50` — `PrerequisiteResult`
- `lip_sync.py:175–364` — `lipsync_overlay` (cascade + SyncNet gate)
- `lip_sync.py:371–424` — `validate_lipsync_quality`
- `lip_sync.py:427–441` — `_sync_gate_settings`
- `lip_sync.py:468–675` — `lipsync_generation` (Hedra → Kling → Omnihuman → Aurora)
- `lip_sync.py:682–734` — `generate_lip_sync_video` router
- `lip_sync.py:735–788` — `generate_rife_interpolation`
- `lip_sync.py:791–844` — `upscale_video_seedvr2`
- `phase_c_assembly.py:72–394` — `generate_ai_broll` (ComfyUI + ControlNet + IP-Adapter)
- `phase_c_assembly.py:415–581` — `_fal_flux_fallback` (Kontext → FLUX-Pro → Schnell → Pollinations)
- `prep/lora_training.py:99–112` — `DEFAULT_TRAIN_CONFIG`
- `prep/lora_training.py:116–128` — `LoraStatus`
- `prep/lora_training.py:153–232` — `prepare_character_lora_dataset`
- `prep/lora_training.py:376–505` — `train_character_lora`
- `prep/lora_training.py:512–533` — `validate_lora_quality` (stub)
- `prep/topaz_upscale.py:41–49` — `_TOPAZ_MODEL_RECOMMENDATIONS`
- `prep/topaz_upscale.py:75–146` — `upscale_with_topaz`
- `audio/dialogue.py:45–115` — `generate_cartesia`
- `audio/dialogue.py:122–174` — `_resolve_tts_provider`
- `audio/dialogue.py:177–249` — `_try_dialogue_mode`
- `audio/dialogue.py:252–283` — `_maybe_save_alignment`
- `audio/dialogue.py:286–515` — `generate_dialogue_voiceover`
- `audio/music.py:32–81` — `MUSIC_MASTERING_PRESETS`
- `audio/music.py:139–252` — `generate_suno_v5`
- `audio/music.py:255–274` — `generate_bgm` (router)
- `audio/music.py:279–372` — `generate_fal_bgm`
- `audio/music.py:379–427` — `master_music`
- `audio/foley.py:29–102` — `_build_foley_prompt`
- `audio/foley.py:109–188` — `generate_stability_foley`
- `audio/alignment.py:30–35` — model caches + `_MODEL_LOCK`
- `audio/alignment.py:37–54` — `WordTiming`, `AlignmentResult`
- `audio/alignment.py:67–150` — `_try_whisperx`
- `audio/alignment.py:217–252` — `align_audio_to_text`
- `audio/effects.py:28–85` — `VOICE_EFFECTS`
- `audio/effects.py:88–153` — `apply_au_plugin`
- `audio/effects.py:156–215` — `apply_pedalboard_chain`
- `audio/effects.py:230–284` — `apply_voice_effect`
- `cinema_pipeline.py:481–524` — `_ensure_scene_audio`
- `cinema_pipeline.py:526–546` — `_ensure_bgm`
- `cinema_pipeline.py:548–590` — `_ensure_scene_foley`
- `cinema_pipeline.py:1102–1116` — `_apply_final_loudnorm`
- `cinema_pipeline.py:1118–1182` — `_concat_foley_track`, `_concat_dialogue_track`
- `cinema_pipeline.py:1184–1499` — `_assemble_final` (normalize → stitch → grade → mix → loudnorm)
- `cinema_pipeline.py:1270–1311` — xfade vs hard-cut stitch decision
- `cinema_pipeline.py:1313–1336` — mood-to-grade mapping + `apply_color_grade` call
- `cinema_pipeline.py:1338–1460` — 3-track audio mix filtergraph + standalone-dialogue vs embedded-voice path
- `cinema/shots/controller.py:70–97` — module imports (face_swap, lip_sync, rife, upscale)
- `cinema/shots/controller.py:1208–1312` — F1a/F1b native-audio tagging + mandatory lipsync pass
- `cinema/shots/controller.py:1680–1818` — `apply_correction` action dispatch
- `cinema/shots/controller.py:1639–1646` — `assess_motion_quality` in `diagnose_clip`
- `cinema/auto_approve.py:98` — `final_min_lipsync` default 0.8
- `cinema/auto_approve.py:425–464` — `_best_take_lipsync` (dialogue-aware defaults)
- `domain/scene_decomposer.py:42–43` — API_REGISTRY VEO_NATIVE with `native_audio: True`
- `domain/scene_decomposer.py:121–127` — `PURPOSE_API_RANKING` (dialogue_close_up, action_motion, etc.)

---

## 12. cost/report/docs/config — Cross-cutting services + CONFIG/OPERATION surface

*Subsystem key: `crosscutting-docs-config`*

### Purpose

Four modules provide pipeline-wide infrastructure: **cost_tracker.py** (durable spend ledger + budget gate for every LLM and API call), **reporter.py** (legacy diagnostic/status printer, currently an orphan with no production callers), **cleanup.py** (file-lifecycle manager that purges temp/ artifacts after assembly), and **cinema/logging_config.py** (structured JSON logging that installs a root-logger handler before any pipeline imports). The **config/settings.py** singleton centralizes all env-var reads into one frozen dataclass; the `.env.example` + OPERATIONS.md §3 are the authoritative operator contract for every knob.

---

### Modules

| Module | Path | One-line role | Verified LOC |
|---|---|---|---|
| Cost tracker | `cost_tracker.py` | SQLite-backed per-API and LLM spend ledger with budget gate | 533 |
| Reporter | `reporter.py` | Legacy glob/log diagnostic printer (no production callers; orphan) | 52 |
| Cleanup | `cleanup.py` | Deletes intermediate temp/ artifacts post-assembly; configurable retention | 154 |
| Logging config | `cinema/logging_config.py` | Installs JSON-line root logger; reads `CINEMA_LOG_LEVEL` | 114 |
| Settings | `config/settings.py` | Frozen `Settings` dataclass wrapping all env vars; `lru_cache` singleton | 141 |

---

### Key functions & classes (the micro level)

#### cost_tracker.py

**`API_COST_USD: dict[str, float]`** — `cost_tracker.py:43`
Table of per-call USD estimates keyed by API name (uppercase). 20 entries covering video (KLING_NATIVE $0.50, SORA_NATIVE $0.80, VEO_NATIVE $0.30, LTX $0.10, RUNWAY_GEN4 $0.50), image (COMFYUI_PULID $0.04, FLUX_PRO $0.05, POLLINATIONS $0.00, QUALITY_MAX $0.40), and audio (STABILITY_FOLEY $0.03, ELEVENLABS $0.01, SUNO_V5 $0.50, FAL_STABLE_AUDIO $0.10, CARTESIA_SONIC_2 $0.008). These are ±30% estimates; operators must calibrate against invoices.

**`PRICING: dict[str, dict]`** — `cost_tracker.py:76`
Per-1M-token pricing table for LLMs: Anthropic (claude-sonnet-4-6 $3/$15, claude-opus-4-20250918 $5/$25, claude-haiku-4-5 $1/$5), OpenAI (gpt-4.1 $2/$8, gpt-4o $2.50/$10, o4-mini $1.10/$4.40), Google (gemini-2.5-flash $0.30/$2.50, gemini-2.5-pro $1.25/$10).

**`class CostTracker`** — `cost_tracker.py:131`
Constructor: `CostTracker(db_path="data/experiments.db", budget_usd=None)`. Opens SQLite connection at `db_path`; `budget_usd=None` disables gate. Creates `cost_log` table on first use. Holds `self.spent_usd: float` as in-process accumulator (resets per process — NOT loaded from SQLite on init).

**`CostTracker.log()`** — `cost_tracker.py:178`
Base insert: `(provider, model, operation, cost_usd, input_tokens, output_tokens, shot_id, video_id)` → `cost_log` row with UTC ISO timestamp. Returns `CostEntry` dataclass.

**`CostTracker.log_llm()`** — `cost_tracker.py:213`
Takes `(model, operation, input_tokens, output_tokens, shot_id, video_id)`. Auto-detects provider via `_detect_provider(model)`. Computes cost from `PRICING[model]`. **Gotcha:** unknown model emits `warnings.warn` + `print` but records `$0.00` — silent budget gap. Primary logging path for all LLM calls.

**`CostTracker.record_api_call()`** — `cost_tracker.py:275`
Takes `(api_name, cost_usd=None, operation, shot_id, video_id)`. Looks up `API_COST_USD[api_name.upper()]` if `cost_usd` not supplied. Updates `self.spent_usd`. Only call on success path. Primary logging path for video/image/audio API calls.

**`CostTracker.log_api()`** — `cost_tracker.py:254`
Direct cost insert with no lookup. Used by performance capture modules (`viggle.py`, `driving_video.py`, `live_portrait.py`, `act_one.py`).

**`CostTracker.would_exceed(api_name)`** — `cost_tracker.py:335`
Pre-call gate: `(self.spent_usd + API_COST_USD[api_name]) > self.budget_usd`. Returns `False` when `budget_usd=None`. Used in `cinema/shots/controller.py:562` before video generation.

**`CostTracker.is_over_budget()`** — `cost_tracker.py:345`
Post-call gate. Used in `cinema/shots/controller.py:1014` to pause pipeline via `lifecycle.pause()` when budget is exceeded.

**`CostTracker.get_video_cost(video_id)`** — `cost_tracker.py:358`
Returns dict: `{total_usd, llm_usd, api_usd, breakdown_by_provider, breakdown_by_operation, shot_count}`. LLM spend is inferred by `input_tokens > 0 or output_tokens > 0` on each row.

**`CostTracker.get_session_cost(lookback_hours=24.0)`** — `cost_tracker.py:401`
Rolling-window total; NOT process-bounded. Returns float.

**`CostTracker.get_cost_per_second(video_id, video_duration_seconds)`** — `cost_tracker.py:416`
`total_usd / video_duration_seconds`. Returns 0.0 if duration ≤ 0.

**`CostTracker.check_budget(budget_remaining_usd, estimated_cost_usd)`** — `cost_tracker.py:427`
Returns `(bool, list[str])`. When over budget, the list contains 5 hardcoded human-readable alternatives (switch to cheaper APIs, reduce tokens, etc.).

**`CostTracker.get_summary()`** — `cost_tracker.py:455`
Returns formatted ASCII report: total spend, LLM call count, API call count, token totals, spend-by-provider bar chart, spend-by-operation, avg cost/LLM call, cost/1K input tokens.

**`CostTracker.close()`** — `cost_tracker.py:531`
Closes SQLite connection. Not called by pipeline (PipelineCore holds open connection for process lifetime).

**`_detect_provider(model: str) -> str`** — `cost_tracker.py:102`
Heuristic: "claude" → "anthropic", "gpt"/"o…" → "openai", "gemini" → "google", else "unknown".

#### reporter.py

**`generate_report()`** — `reporter.py:6`
Globs `temp_foley_*.mp3`, `temp_img_*.jpg`, `temp_vid_*.mp4` from CWD. Checks mtime stall on the latest video file. Reads `CRASH_REPORT.txt` and `macstudio.log` (last 10 lines) if present. Hardcodes totals of 21/20/20 — these appear to be from a legacy project structure and are no longer meaningful. **No production callers (confirmed via grep — ARCHITECTURE.md §17).**

#### cleanup.py

**`CLEANUP_RULES: dict`** — `cleanup.py:34`
Retention policy keyed by category. Always-delete: `*_norm.mp4`, `interp_*.mp4`, `stitched.mp4`, `swapped_*.mp4`, `lastframe_*.*`, `chain_last_*.*`, `transition_*.mp4`, `storyboard_*.mp4`, `upscale_*.mp4`, `temp_dialogue_line_*.mp3`. Keep-by-default: `img_*.jpg`, `vid_*.mp4`, `foley_*.mp3`, `audio_*.mp3`, `bgm_*.mp3`. Keep-by-default items are deleted only in `aggressive=True` mode.

**`cleanup_project(project_id, aggressive=False, dry_run=False)`** — `cleanup.py:56`
Resolves `project_dir/temp/` via `get_project_dir()`. Iterates `CLEANUP_RULES`, deletes matched files. Returns `{files_deleted, bytes_freed, mb_freed, details, mode}`. Non-fatal by caller design — `cinema_pipeline.py:808-814` wraps in try/except.

**`cleanup_all_projects(aggressive=False, dry_run=False)`** — `cleanup.py:117`
Iterates `list_projects()`, calls `cleanup_project` for each. Returns aggregate stats.

**`get_project_disk_usage(project_id)`** — `cleanup.py:139`
Walks `temp/`, `characters/`, `locations/`, `exports/` subdirs. Returns dict with MB values per subdir + total. Used by `api_disk_usage` at `web_server.py:2571`.

#### cinema/logging_config.py

**`_JsonFormatter`** — `cinema/logging_config.py:68`
Custom `logging.Formatter`. Emits one JSON object per record with top-level keys: `ts` (ISO), `level`, `logger`, `msg`, plus any `extra={...}` kwargs promoted to top-level. Traceback under `exc_info` key. Non-serializable extras wrapped in `repr()`.

**`setup_logging(level=None)`** — `cinema/logging_config.py:97`
Idempotent: clears existing root handlers then adds a single `StreamHandler(sys.stdout)` with `_JsonFormatter`. Reads `CINEMA_LOG_LEVEL` env if `level` not passed; defaults to "INFO". Pins `DeepFace`, `tensorflow`, `matplotlib`, `PIL`, `urllib3` at WARNING. Called at module level in `web_server.py:29` (before any cinema imports) and in `cinema_pipeline.py:1513-1515` (when run as `__main__`).

#### config/settings.py

**`Settings` (frozen dataclass)** — `config/settings.py:49`
28 typed fields covering LLM keys, video API keys, audio keys, performance-capture keys, Google Cloud, research, ComfyUI URL, paths, tuning integers, and web server config. **Rule: only API keys + infra paths live here; project UI knobs must flow through `get_project_setting(ctx, ...)`.**

**`get_settings() -> Settings`** — `config/settings.py:137`
`@lru_cache(maxsize=1)` factory. Calls `Settings.from_env()` once. Exposed as module-level `settings = get_settings()`.

**`_parse_cors_origins(raw: str) -> tuple[str, ...]`** — `config/settings.py:33`
Parses `WEB_CORS_ORIGINS` value: empty → localhost-only default; comma-separated → tuple; `*` → `("*",)` (wide-open).

---

### Data IN → OUT

**cost_tracker.py:**
- IN: `(model, operation, tokens)` from LLM callers; `(api_name, cost_usd)` from API callers; `(video_id)` for queries; `budget_usd` from `global_settings.budget_limit_usd` at init.
- OUT: `CostEntry` dataclass on each log call; SQLite rows in `cost_log`; formatted summary string; cost breakdown dicts; budget boolean gates.

**reporter.py:**
- IN: CWD glob patterns + optional `CRASH_REPORT.txt` + optional `macstudio.log`.
- OUT: Print to stdout only.

**cleanup.py:**
- IN: `project_id`, `aggressive`, `dry_run` flags.
- OUT: File deletions from `<project_dir>/temp/`; stats dict.

**cinema/logging_config.py:**
- IN: `CINEMA_LOG_LEVEL` env; `extra={}` kwargs on logger calls.
- OUT: JSON-line records to `sys.stdout`.

**config/settings.py:**
- IN: `.env` file (loaded at import via `load_dotenv`); environment variables.
- OUT: Frozen `Settings` singleton; individual field access like `settings.kling_access_key`.

---

### Connects to (other subsystems)

**cost_tracker.py:**
- `cinema/core.py:54,113` — `PipelineCore` constructs `CostTracker(budget_usd=...)` from `project.global_settings.budget_limit_usd`. Direct instantiation.
- `cinema/shots/controller.py:213-224, 562, 995-1023` — `ShotController.cost_tracker` is a proxy to `PipelineCore.cost_tracker`. Calls `record_api_call()` after each video/image generation; calls `is_over_budget()` post-generation to trigger `lifecycle.pause()`.
- `cinema/phases/motion_render.py:188` — calls `record_api_call()` after motion renders.
- `audio/foley.py:177-181`, `audio/music.py:239-243, 362-363`, `audio/dialogue.py:415-457` — each constructs a fresh `CostTracker()` (no-arg, default DB) for isolated logging. **These do NOT share the core's tracker instance or budget.**
- `performance/viggle.py:29`, `performance/driving_video.py:35`, `performance/live_portrait.py:30`, `performance/act_one.py:32` — same pattern: fresh `CostTracker()` via `log_api()`.
- `domain/character_manager.py:323-328` — calls `record_api_call()` for ComfyUI character image gen.
- `web_research.py:169-172, 209-212` — calls `log_llm()` for research LLM calls.
- `web_server.py:2509-2514` — `api_cost_live` re-uses `cached_core.cost_tracker` when available, else creates a fresh `CostTracker()` for the query.
- `cinema_pipeline.py:818` — calls `get_video_cost(video_id)` to include cost summary in pipeline completion log.

**cleanup.py:**
- `project_manager.py` (root shim → `domain/project_manager.py`) — `get_project_dir()` and `list_projects()`.
- `cinema_pipeline.py:808-814` — called automatically post-assembly (non-aggressive, non-dry-run).
- `web_server.py:2483-2492` — `api_cleanup` endpoint (with optional `aggressive` + `dry_run`).
- `web_server.py:2527-2533` — `api_cleanup_all` endpoint.
- `web_server.py:2496` — `api_disk_usage` uses `get_project_disk_usage()`.

**cinema/logging_config.py:**
- `web_server.py:27-29` — `setup_logging()` called before any cinema imports so all module-level loggers inherit the JSON formatter.
- `cinema_pipeline.py:1513-1515` — `setup_logging()` called when run as `__main__`.
- All production modules: use `logging.getLogger(__name__)` and emit `logger.info/debug/warning/exception(...)` with `extra={}` for structured fields.

**config/settings.py:**
- `cinema/core.py` — reads `settings.experiments_db_path` (declared but NOT passed to `CostTracker` — see Gotchas).
- `performance/motion_gate.py:50` — `settings.motion_gate_samples` sets `_NUM_SAMPLE_PAIRS` at module load.
- `performance/_cache.py:27` — `settings.performance_cache_dir` as fallback (env var checked first).
- `performance/act_one.py:72` — `settings.runwayml_api_secret` with env fallback.
- `performance/driving_video.py:55-56` — `settings.hedra_api_key`, `settings.fal_key`.
- `performance/viggle.py:56` — `settings.viggle_api_key`.
- `web_server.py` — `env_settings` (alias for `settings`) used for `web_bind_host`, `web_cors_origins` at process startup.

---

### User-facing surface & capability knobs

#### Env vars — full consolidated table

##### API keys (in `.env` / shell)

| Variable | Required? | Default | Effect |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | LLMEnsemble, ChiefDirector, scene decomp |
| `OPENAI_API_KEY` | Yes | — | LLMEnsemble, style director, dialogue writer, scene decomp fallback |
| `GEMINI_API_KEY` | Optional | — | Opt-in Gemini dispatch via `models=[...]` |
| `GOOGLE_API_KEY` | Optional | — | Veo direct API path |
| `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` | Recommended | — | KLING_NATIVE engine (JWT auth); primary video |
| `FAL_KEY` | Recommended | — | FAL routes: Sora, Veo (proxy), Kling 3.0, LTX (proxy), Hedra, all lipsync, music, FLUX image fallback |
| `LTX_API_KEY` | Optional | — | LTX_NATIVE direct (preferred over FAL proxy) |
| `RUNWAYML_API_SECRET` | Optional | — | RUNWAY_GEN4, RUNWAY (gen3a_turbo), Act-One performance |
| `SEEDANCE_API_KEY` | Optional | — | SEEDANCE engine (action cascade only) |
| `ELEVENLABS_API_KEY` | Yes (audio path) | — | TTS narration + dialogue voiceover |
| `CARTESIA_API_KEY` | Optional | — | Cartesia Sonic 2 alternate TTS |
| `STABILITY_API_KEY` | Optional | — | Stable Audio 2 foley/BGM (currently dormant — `audio/` not wired) |
| `SUNO_API_KEY` (+ `SUNO_TOKEN` legacy alias) | Optional | — | Suno V5 BGM |
| `SUNO_API_BASE` | Optional | `https://api.suno.ai/v1` | Suno V5 endpoint override |
| `VIGGLE_API_KEY` | Optional | — | Viggle Mode A motion retargeting |
| `HEDRA_API_KEY` | Optional | — | Direct Hedra REST fallback (FAL proxy preferred) |
| `GOOGLE_CLOUD_PROJECT` | Required for VEO_NATIVE/Vertex | — | Vertex AI project ID |
| `GOOGLE_CLOUD_LOCATION` | Optional | `us-central1` | Vertex AI region |
| `FIRECRAWL_API_KEY` | Optional | — | Style director + scene decomp web research |
| `TAVILY_API_KEY` | Optional | — | Same; preferred over Firecrawl |
| `PEXELS_API_KEY` | Optional | — | Stock footage fallback |

##### Infrastructure paths + tuning

| Variable | Default | Effect |
|---|---|---|
| `COMFYUI_SERVER_URL` | `http://127.0.0.1:8188` | Pod address for image gen (production + max tier) |
| `EXPERIMENTS_DB_PATH` | `data/experiments.db` | SQLite cost tracker DB path (declared in `Settings` but **not wired to `CostTracker`** — see Gotchas) |
| `PERFORMANCE_CACHE_DIR` | `data/cache/driving` | SHA256-keyed driving-video cache for Mode-B synthesis |
| `MOTION_GATE_SAMPLES` | `8` | Frame-pair sample count for `motion_gate.score_motion_fidelity`; read once at module load |

##### Web server

| Variable | Default | Effect | Maximize how |
|---|---|---|---|
| `WEB_BIND_HOST` | `127.0.0.1` | Flask bind address | `0.0.0.0` for LAN/multi-device; tighten `WEB_CORS_ORIGINS` |
| `WEB_CORS_ORIGINS` | `http://localhost:8080,http://localhost:5173` | CORS allowlist | `*` for wide-open; comma-separated for specific LAN IPs |

##### Feature flags (CINEMA_* pattern)

| Variable | Class | Default | Truthy values | Effect |
|---|---|---|---|---|
| `CINEMA_LOG_LEVEL` | infra | `INFO` | Any Python log level string | Sets root logger level; `DEBUG` for verbose pipeline tracing |
| `CINEMA_STRICT_SCHEMA` | A (opt-in) | OFF | `1`, `true`, `TRUE`, `yes` | Makes `_validate_project()` raise `ValidationError` instead of warn on schema mismatch |
| `CINEMA_AUTO_APPROVE_MOTION` | A (opt-in) | OFF | `1`, `true`, `yes` (case-insensitive) | Wires motion-gate auto-approve rules into `PERFORMANCE_REVIEW` gate |
| `CINEMA_DIRECTORIAL_ITERATION` | B (opt-out) | ON | anything not `0`/`false`/`no` | Enables `/shots/<sid>/iterate` endpoint; set to `0` to disable |
| `CINEMA_SCREENING_STAGE` | B (opt-out) | ON | anything not `0`/`false`/`no` | Enables screening endpoints (`/assemble/screen`, `/screening/approve`); set to `0` to skip screening gate |

##### Project-level knobs (in `global_settings` dict, not env vars)

| Field | Type | Effect |
|---|---|---|
| `budget_limit_usd` | float or null | Sets `CostTracker.budget_usd`; pipeline pauses via `lifecycle.pause()` when exceeded |
| `competitive_generation` | bool | When True, LLMEnsemble runs Anthropic + OpenAI in parallel quorum (doubles LLM cost) |
| `quality_tier` | str | `"production"` (ComfyUI PuLID) vs `"max"` (N=8 adaptive best-of with SUPIR) |
| `scene_transitions` | bool | When True, routes per-scene concat through `xfade_concat` (cross-dissolve); default hard-cut |

#### Docs — what each covers and where to look

| Need | Document | Key sections |
|---|---|---|
| Quick start (30 seconds) | `README.md` | Entire file (92 lines) |
| All env vars, defaults, effect | `OPERATIONS.md §3`, `.env.example` | Authoritative combined reference |
| Run/start/stop/troubleshoot | `OPERATIONS.md §4, §9` | Flask start, cancel API, common errors |
| Pod setup (ComfyUI, models) | `OPERATIONS.md §5, §6` | RunPod spec, bootstrap script, workflow JSONs |
| Cost per shot / per project | `OPERATIONS.md §10` | Per-provider rough estimates |
| Code-level architectural truth | `ARCHITECTURE.md` | §4.3 (PipelineCore), §7.7 (CINEMA_* flags), §13.8 (settings), §15 (smoke), §17 (dead code) |
| Feature wired/stubbed/parked | `docs/pipeline_status.toml` | 8 entries (2026-05-29 baseline); `scripts/status.py` for rendered view |
| Settled architectural decisions | `DECISIONS.md` | ADR-013 (verification), ADR-014 (motion gate), ADR-016 (GitNexus removal), ADR-019 (doc-maint) |

---

### Control & data flow

**Logging setup:**
1. `web_server.py` module loads → `setup_logging()` called at line 29 → root logger gets `_JsonFormatter(StreamHandler(stdout))` → all subsequent module-level `logging.getLogger(__name__)` calls inherit JSON handler.
2. `CINEMA_LOG_LEVEL` env read at that moment; DEBUG enables pipeline tracing.

**CostTracker lifecycle during a pipeline run:**
1. `web_server.py` receives `POST /api/projects/<pid>/generate`.
2. `build_pipeline_core(pid)` constructs `CostTracker(budget_usd=project["global_settings"]["budget_limit_usd"])` — `spent_usd` starts at 0.0.
3. `PipelineCore` stored in `_running_cores[pid]` (lock-guarded).
4. Per shot: `ShotController.cost_tracker.would_exceed(api_name)` checked before video gen; `record_api_call()` called on success; `is_over_budget()` checked after.
5. Audio modules (`dialogue.py`, `music.py`, `foley.py`) and performance modules create **fresh** `CostTracker()` instances (separate SQLite connections to the same DB) — these accumulate in DB but do NOT update the core's `spent_usd` counter.
6. At pipeline completion: `cinema_pipeline.py:818` calls `get_video_cost(video_id)` and logs the breakdown.
7. `web_server.py:2500` `api_cost_live` re-uses `cached_core.cost_tracker.conn` when pipeline is running; falls back to fresh `CostTracker()` when idle.

**Cleanup lifecycle:**
1. `cinema_pipeline._assemble_final()` completes the final video file.
2. Immediately after: `from cleanup import cleanup_project` → `cleanup_project(project_id, aggressive=False)` called at `cinema_pipeline.py:808`.
3. Standard mode deletes only the always-delete patterns. Generated media (`img_*.jpg`, `vid_*.mp4`, `audio_*.mp3`, `foley_*.mp3`, `bgm_*.mp3`) are preserved.
4. Operator can trigger aggressive cleanup via `POST /api/projects/<pid>/cleanup` with `{"aggressive": true}` — deletes all temp including generated media.

**Settings load:**
1. `from config.settings import settings` (at module load by any consumer) → `load_dotenv(_PROJECT_ROOT / ".env", override=True)` runs once → `Settings.from_env()` called once → `@lru_cache` freezes the singleton.
2. All subsequent `settings.field` accesses are dict lookups on the frozen dataclass.
3. `CINEMA_*` behavioral flags are NOT in `Settings` — they are read directly via `os.environ.get(...)` at call time (live reads, not cached at startup).

---

### Gotchas, divergences & doc-drift

**1. `EXPERIMENTS_DB_PATH` is read into `settings.experiments_db_path` but never passed to `CostTracker`** (verified `cinema/core.py:113`). `CostTracker` defaults to `"data/experiments.db"` regardless. Setting `EXPERIMENTS_DB_PATH` in `.env` does nothing. `OPERATIONS.md §3` implies it works. This is a silent misconfiguration hazard — budget governance and cost queries all use the hardcoded default.

**2. Audio/performance module `CostTracker()` instances are isolated from the core's budget gate.** `audio/dialogue.py`, `audio/music.py`, `audio/foley.py`, `performance/viggle.py`, etc. each construct `CostTracker()` with no `budget_usd`. Their spend accumulates in the DB but does NOT add to `PipelineCore.cost_tracker.spent_usd`. The budget gate at `ShotController` only accounts for video/image generation costs; audio API costs run uncapped.

**3. `CostTracker.spent_usd` is NOT loaded from SQLite on `__init__`**. It starts at 0.0 each process. If the server is restarted mid-project, the in-process `spent_usd` resets, so `is_over_budget()` will not fire even if the historical SQLite total exceeds `budget_usd`. Budget governance is per-process-run, not cumulative lifetime.

**4. `reporter.py` is a dead orphan** confirmed via grep (ARCHITECTURE.md §17, verified 2026-05-29). Hardcoded counts (21 foley tracks, 20 images, 20 videos) are from a legacy project structure. The file globs from CWD not from project dirs. Do not attempt to wire it — it is a removal candidate.

**5. `CINEMA_STRICT_SCHEMA` parser is inconsistent with `CINEMA_AUTO_APPROVE_MOTION`** (documented in ARCHITECTURE.md §7.7.2). `CINEMA_STRICT_SCHEMA` uses a tuple `in ("1", "true", "TRUE", "yes")` (does NOT accept `"True"` Python capitalization). `CINEMA_AUTO_APPROVE_MOTION` uses `.strip().lower() in {"1", "true", "yes"}` (case-insensitive). All new flags should use the latter form.

**6. `cleanup.py` imports from root `project_manager` shim**, not `domain.project_manager` directly (`cleanup.py:30`). The shim is a `from domain.project_manager import *` — functionally identical but callers should eventually be migrated per the shim's own docstring.

**7. `pipeline_status.toml` is a partial manifest** (8 components as of 2026-05-29). Stubbed/partial features include `hires_fix` (flag may now be injected via `quality_max.py` overlay params — under verification, Part-3 audit ticket), `lora_validation` (returns -1.0 unconditionally), `batch_scene_optimize` (zero callers), and `multi_identity_validation` (zero callers). None of these are wirable by env var alone — all require code changes. (`storyboard_mode` was previously listed here as stubbed; it is **wired** end-to-end via `motion_render._get_storyboard_mode` → `_run_storyboard_scene` (F2b, `tests/unit/test_f2b_storyboard_mode.py`) — corrected 2026-06-03.)

**8. `reporter.py` globs from CWD, not project dirs.** The old pipeline emitted `temp_foley_*.mp3` etc. to CWD. Post-pivot, artifacts are in `data/projects/<pid>/temp/`. The reporter would find nothing even if called.

**9. `SUNO_TOKEN` legacy alias is silently accepted** (`config/settings.py:117`): `suno_api_key = _env("SUNO_API_KEY") or _env("SUNO_TOKEN")`. Old deployments using `SUNO_TOKEN` will still work.

**10. ARCHITECTURE.md has no dedicated `cinema/logging_config.py` section.** Coverage is only in §3 (web_server note) and the module's own docstring. The `CINEMA_LOG_LEVEL` env var appears in `logging_config.py:104` but is absent from OPERATIONS.md §3 env var table.

---

### Citations

| Claim | File:line |
|---|---|
| `API_COST_USD` table | `cost_tracker.py:43-69` |
| `PRICING` table | `cost_tracker.py:76-90` |
| `CostTracker.__init__` signature | `cost_tracker.py:139-151` |
| `CostTracker.log_llm` unknown-model warning | `cost_tracker.py:231-238` |
| `CostTracker.record_api_call` success-path-only note | `cost_tracker.py:286-290` |
| `CostTracker.would_exceed` | `cost_tracker.py:335-343` |
| `CostTracker.is_over_budget` | `cost_tracker.py:345-352` |
| `CostTracker.get_video_cost` LLM heuristic | `cost_tracker.py:380-384` |
| `CostTracker.get_summary` | `cost_tracker.py:455-525` |
| `generate_report()` globs from CWD | `reporter.py:6-52` |
| reporter.py is orphan | `ARCHITECTURE.md:1527` |
| `CLEANUP_RULES` always-delete vs configurable | `cleanup.py:34-53` |
| `cleanup_project` non-fatal wrapping | `cinema_pipeline.py:808-814` |
| `cleanup_project` aggressive mode | `cleanup.py:56-57` |
| `get_project_disk_usage` subdirs | `cleanup.py:139-141` |
| `_JsonFormatter` extra-field promotion | `cinema/logging_config.py:68-76` |
| `setup_logging` idempotent, CINEMA_LOG_LEVEL | `cinema/logging_config.py:97-114` |
| `setup_logging` called before imports in web_server | `web_server.py:27-29` |
| `setup_logging` in cinema_pipeline `__main__` | `cinema_pipeline.py:1513-1515` |
| `Settings` dataclass fields | `config/settings.py:48-98` |
| `Settings.from_env()` SUNO_TOKEN alias | `config/settings.py:117` |
| `settings` singleton via `lru_cache` | `config/settings.py:136-141` |
| `WEB_CORS_ORIGINS` parse logic | `config/settings.py:33-45` |
| `build_pipeline_core` budget_usd extraction | `cinema/core.py:75-89` |
| `CostTracker` not passed db_path from settings | `cinema/core.py:113` |
| `EXPERIMENTS_DB_PATH` declared in Settings but not wired | `config/settings.py:89, 128` vs `cinema/core.py:113` |
| `spent_usd` in-process only, resets on restart | `cost_tracker.py:147-148` |
| Audio modules use isolated `CostTracker()` | `audio/dialogue.py:420-457`, `audio/music.py:242-363`, `audio/foley.py:180-181` |
| `ShotController.cost_tracker` proxy | `cinema/shots/controller.py:213-224` |
| Budget pause on `is_over_budget` | `cinema/shots/controller.py:1014-1023` |
| `api_cost_live` re-uses cached core tracker | `web_server.py:2578-2583` |
| `api_cleanup` endpoint params | `web_server.py:2558-2570` |
| `api_cleanup_all` endpoint | `web_server.py:2604-2611` |
| `CINEMA_STRICT_SCHEMA` literal-case parser gotcha | `domain/project_manager.py:633-634`, `ARCHITECTURE.md:606-616` |
| `CINEMA_AUTO_APPROVE_MOTION` case-insensitive parser | `cinema/auto_approve.py:577-579` |
| `CINEMA_DIRECTORIAL_ITERATION` default-ON (Class B) | `cinema/shots/controller.py:111` |
| `CINEMA_SCREENING_STAGE` default-ON (Class B) | `cinema/screening.py:127` |
| `pipeline_status.toml` stubbed features | `docs/pipeline_status.toml:35-72` |
| `cleanup.py` imports from root shim | `cleanup.py:30` |
| root `project_manager.py` is a shim | `domain/project_manager.py:1-9` |
| `MOTION_GATE_SAMPLES` read at module load | `performance/motion_gate.py:50` |
| `PERFORMANCE_CACHE_DIR` env checked first, settings as fallback | `performance/_cache.py:27` |
| OPERATIONS.md §3 env var table | `OPERATIONS.md:85-149` |
| OPERATIONS.md §10 cost estimates | `OPERATIONS.md:442-463` |
| ARCHITECTURE.md §13.8 settings rule | `ARCHITECTURE.md:1369-1378` |
| ARCHITECTURE.md §7.7.3 two-class flag taxonomy | `ARCHITECTURE.md:645-758` |
| `CINEMA_LOG_LEVEL` absent from OPERATIONS.md §3 | `OPERATIONS.md:85-149` (not present) |
