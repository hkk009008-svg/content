# Content — Architecture & Truth Map

> **Verified against source on 2026-05-24.** Every claim here was cross-checked
> against the code by parallel investigators. If you find a divergence between
> this file and the code, fix this file in the same change that exposes the
> drift.
>
> This file is the *truth layer*. `CLAUDE.md` is the *process layer*
> (the impact-analysis method, session-start protocol, multi-task orchestration). When
> they disagree about facts, **this file wins**.

---

## Quick navigation

- §1 [Macro flow](#1-macro-flow)
- §2 [Component topology](#2-component-topology)
- §3 [Entry point — `web_server.py`](#3-entry-point--web_serverpy)
- §4 [Orchestrator — `cinema_pipeline.py` + `cinema/`](#4-orchestrator--cinema_pipelinepy--cinema)
- §5 [Phase protocol & three phases](#5-phase-protocol--three-phases)
- §6 [Gate mechanism — predicate-poll](#6-gate-mechanism--predicate-poll)
- §7 [Story prep — decompose, dialogue, continuity](#7-story-prep--decompose-dialogue-continuity)
- §8 [Image generation — production + max-tier N=8](#8-image-generation--production--max-tier-n8)
- §9 [Video routing — 5 templates × 11 engines](#9-video-routing--5-templates--11-engines)
- §10 [Performance capture & lipsync](#10-performance-capture--lipsync)
- §11 [Identity validation — GhostFaceNet singleton](#11-identity-validation--ghostfacenet-singleton)
- §12 [Audio pipeline](#12-audio-pipeline)
- §13 [LLM coordination](#13-llm-coordination)
- §14 [Frontend — React 19 + Vite](#14-frontend--react-19--vite)
- §15 [Invariants & smoke test](#15-invariants--smoke-test)
- §16 [Known bugs & latent issues](#16-known-bugs--latent-issues)
- §17 [Dead code & cleanup candidates](#17-dead-code--cleanup-candidates)
- §18 [Keeping this file fresh](#18-keeping-this-file-fresh)

---

## 1. Macro flow

Operator drives the pipeline through a web UI. The Flask server spawns one
daemon thread per project; that thread runs `CinemaPipeline.generate()` which
sequences a story-prep stage, three Phase classes (keyframe → performance →
motion), and an assembly stage, with **four operator review gates** between
them.

```
[OPERATOR] ──HTTP──▶ web_server.py (Flask, 59 routes)
                         │  daemon thread per project (POST /generate)
                         ▼
                cinema_pipeline.py:CinemaPipeline.generate()
                  ├─ composes: PipelineCore + ThreadedLifecycle
                  │            + RunState + ShotController
                  │            + ReviewController + CheckpointStore
                  ▼
      ┌────────┬──────────┬─────────┬──────────┬──────────┬──────────┐
      ▼        ▼          ▼         ▼          ▼          ▼          ▼
    STYLE   AUDIO    DECOMPOSE  PLAN_REV  KEYFRAME  KEYFRAME_REV  PERFORMANCE
   (GPT-4o) (BGM)   (per-scene  ⏸ GATE 1  (per-shot)  ⏸ GATE 2    (A/B mode)
                    + Director              image gen)
                    validate)
                                                                     │
                                                                     ▼
                                                              PERFORMANCE_REV
                                                              ⏸ GATE 3 (open
                                                              when all shots
                                                              SKIP or done)
                                                                     │
                                                                     ▼
                                                                   MOTION
                                                                  (video API
                                                                   cascade)
                                                                     │
                                                                     ▼
                                                                  REVIEW
                                                                  ⏸ GATE 4
                                                                     │
                                                                     ▼
                                                                  ASSEMBLY
                                                                 (stitch +
                                                                  LUT + R128
                                                                  loudnorm)
```

**13 published stages** (`web/src/hooks/usePipelineState.ts:5-19`):
`STYLE → AUDIO → DECOMPOSE → DIRECTOR → PLAN_REVIEW → KEYFRAME →
KEYFRAME_REVIEW → PERFORMANCE → PERFORMANCE_REVIEW → MOTION → REVIEW →
SCENE_PREVIEW → ASSEMBLY`.

---

## 2. Component topology

| Layer | Primary file(s) | Owns |
|---|---|---|
| HTTP | [web_server.py](web_server.py) | Flask + SSE + CORS. Spawns pipeline daemon. Caches `PipelineCore` per project (lock-guarded). |
| Orchestrator | [cinema_pipeline.py](cinema_pipeline.py) | Big `generate()` method. 53 forwarder methods autogenerated by [tools/gen_delegates.py](tools/gen_delegates.py). |
| Substrate | [cinema/context.py](cinema/context.py), [cinema/core.py](cinema/core.py), [cinema/lifecycle.py](cinema/lifecycle.py), [cinema/runstate.py](cinema/runstate.py), [cinema/checkpoint.py](cinema/checkpoint.py), [cinema/services.py](cinema/services.py) | `PipelineContext` (dataclass+dict), `PipelineCore` (long-lived deps), `ThreadedLifecycle` (cancel/pause/gate Events), `RunState` (per-run mutable), `CheckpointStore` (atomic JSON), `services` (cheap state snapshots). |
| Phases | [cinema/phases/](cinema/phases/) — `base.py`, `keyframe_render.py`, `performance.py`, `motion_render.py` | Phase protocol + 3 thin shot-iterating phases. |
| Shot work | [cinema/shots/controller.py](cinema/shots/controller.py) (1266 LOC) | `generate_keyframe_take`, `generate_performance_take`, `generate_motion_take`, `regenerate_shot`, `restart_shot`, `diagnose_clip`, `apply_correction`, `generate_scene_preview`. |
| Review/gates | [cinema/review/controller.py](cinema/review/controller.py) | Gate predicate-poll. **`PERFORMANCE_REVIEW` is not in `_gate_satisfied`** — opens implicitly. |
| Story prep | [domain/](domain/) — `scene_decomposer.py`, `dialogue_writer.py`, `continuity_engine.py`, `character_manager.py`, `location_manager.py`, `project_manager.py`, `language_defaults.py`, `shot_types.py`, `performance.py` | Filelock-guarded JSON CRUD (10s). LLM persona "CineDecompose v1.0" with 8 HardConstraints + 9 Tripwires. |
| LLM | [llm/](llm/) — `ensemble.py`, `chief_director.py`, `style_director.py`, `prompt_optimizer.py`, `negative_prompts.py` | Parallel quorum (not fallback), then a judge picks. Anthropic + OpenAI + **Gemini opt-in**. |
| Identity | [identity/](identity/), [face_validator_gate.py](face_validator_gate.py), [phase_c_vision.py](phase_c_vision.py) | **GhostFaceNet via DeepFace** (NOT ArcFace). Singleton via double-checked locking; 4 access paths converge. |
| Image gen | [phase_c_assembly.py](phase_c_assembly.py), [quality_max.py](quality_max.py), [pulid.json](pulid.json), [pulid_max.json](pulid_max.json) | Production = RunPodComfyUI + PuLID. Max = N=8 adaptive best-of + SUPIR + 4K downsample. |
| Video gen | [workflow_selector.py](workflow_selector.py), [phase_c_ffmpeg.py](phase_c_ffmpeg.py), [kling_native.py](kling_native.py), [sora_native.py](sora_native.py), [veo_native.py](veo_native.py), [ltx_native.py](ltx_native.py) | 5 shot-type templates × 11-engine dispatch. Runway + Seedance dispatched inline (no adapter file). |
| Performance | [performance/](performance/) — `_router.py`, `act_one.py`, `live_portrait.py`, `viggle.py`, `driving_video.py`, `motion_gate.py`, `identity_gate.py`, helpers `_cache.py`/`_net.py`/`_poll.py` | Per-provider semaphores. Mode B autopilot Hedra-FAL → Hedra-direct → SadTalker, content-hash cached. |
| Lipsync | [lip_sync.py](lip_sync.py) | Overlay cascade (4 cloud engines) vs generation cascade (4 cloud engines). SyncNet quality gate. |
| Audio | [audio/](audio/) — `voiceover.py`, `dialogue.py`, `music.py`, `foley.py`, `effects.py`, `alignment.py`, `srt.py`, `_client.py` | ElevenLabs SDK singleton. Pedalboard hard dep. WhisperX forced alignment. |
| Frontend | [web/src/](web/src/) | React 19 + Vite 6 + Tailwind 3. 3-mode `useState` (no router). Two strict palettes. |

---

## 3. Entry point — `web_server.py`

**1697 LOC, 59 `@app.route` decorators, 58 view functions** (one handler binds
two URLs — `/assemble` + `/proceed-assembly`, [web_server.py:1545-1546](web_server.py:1545)).

### 3.1 Route inventory (grouped)

| Group | Count | Examples |
|---|---|---|
| Static frontend | 2 | `GET /`, `GET /<path>` |
| Config / cost | 3 | `GET /api/config`, `POST /api/cost-estimate` |
| Project CRUD | 5 | `POST/GET/PUT/DELETE /api/projects[/<pid>]` |
| Characters + LoRA + style-board | 10 | `POST /api/projects/<pid>/characters`, `POST .../train-lora`, … |
| Objects | 3 | `POST/PUT/DELETE /api/projects/<pid>/objects` |
| Locations | 3 | same shape |
| Scenes + dialogue + decompose | 7 | `POST .../scenes/<sid>/decompose`, `POST .../style-rules` |
| Pipeline lifecycle + SSE | 7 | `POST /generate`, `GET /stream`, `POST /cancel`, `POST /pause`, `POST /resume`, `GET /pipeline-state`, `GET /checkpoint` |
| Gate approvals + shot ops | 12 | `POST /shots/<sid>/plan/approve`, `POST .../keyframes/<take>/approve`, `POST .../final/<take>/approve`, `POST .../restart`, `POST .../regenerate`, `POST .../correct`, `POST .../diagnose` |
| Assembly + cleanup + cost + files | 8 | `POST /assemble`, `GET /file`, `GET /export`, `POST /api/cleanup-all` |

### 3.2 Threading & lifecycle storage

| Symbol | Lock? | Lives at |
|---|---|---|
| `_progress_queues: dict[pid, Queue]` | no (GIL-atomic `dict.get`) | [web_server.py:71](web_server.py:71) |
| `_running_pipelines: dict[pid, CinemaPipeline]` | no | [web_server.py:72](web_server.py:72) |
| `_running_cores: dict[pid, PipelineCore]` | `_cores_lock` | [web_server.py:108-109](web_server.py:108) |
| `_lora_training_threads` | `_lora_training_lock` | [web_server.py:685-686](web_server.py:685) |

Pipeline worker: `threading.Thread(target=run_pipeline, daemon=True)`
spawned by `POST /generate` ([web_server.py:1505](web_server.py:1505)).
**Cancellation is cooperative** — `pipeline.cancel()` flips a flag the worker
polls; the HTTP handler returns immediately and the worker may take seconds to
wind down.

### 3.3 SSE wiring

- `_ensure_progress_queue(pid)` creates a `queue.Queue` keyed by project.
- Pipeline thread builds a callback via
  `web_services.make_progress_callback(q)` and passes it into `CinemaPipeline`.
- `GET /api/projects/<pid>/stream` opens an EventSource. Generator at
  [web_server.py:1530-1544](web_server.py:1530) does `q.get(timeout=30)`;
  on timeout emits HEARTBEAT, on `None` sentinel emits END and breaks.
- Pipeline thread writes `None` to the queue in `finally`
  ([web_server.py:1503](web_server.py:1503)) after success or error.
- **Queue is released on run completion** (Bundle-C 3.2, 2026-05-24) —
  the `run_pipeline` daemon's `finally` block now pops `_progress_queues[pid]`
  after sending the `None` sentinel, gated on identity-check to avoid racing
  a concurrent `/generate` that already replaced the entry.

### 3.4 CORS / auth

- **No auth.** No decorator across all 59 routes.
- **CORS defaults to localhost.** `CORS(app, origins=list(env_settings.web_cors_origins))`
  at [web_server.py:68](web_server.py:68). Default `web_cors_origins`
  is localhost-only (`http://localhost:8080` + Vite dev port `5173`). Opt into
  wide-open with `WEB_CORS_ORIGINS=*`. Banner warning emitted when wide-open.

### 3.5 cinema/services.py usage (no-pipeline-spin path)

Two endpoints avoid constructing `CinemaPipeline`:
- `GET /api/projects/<pid>/checkpoint` → `checkpoint_info(pid)` ([web_server.py:1511](web_server.py:1511))
- `GET /api/projects/<pid>/pipeline-state` → `state_snapshot(pid)` only when no
  live pipeline exists ([web_server.py:1976](web_server.py:1976)).

Rationale: instantiating `CinemaPipeline` also instantiates
`ContinuityEngine + ChiefDirector + LLMEnsemble + CostTracker`, which is heavy
for a state-read endpoint.

### 3.6 Gate approval endpoints

| Gate | Endpoint | Backing call |
|---|---|---|
| PLAN_REVIEW | `POST /api/projects/<pid>/shots/<sid>/plan/approve` (and `/reject`) | `pipeline.approve_shot_plan(sid, approved=True)` |
| KEYFRAME_REVIEW | `POST .../shots/<sid>/keyframes/<take_id>/approve` | `pipeline.approve_take(sid, take_id, "keyframe")` |
| PERFORMANCE_REVIEW | `POST .../shots/<sid>/performance/<take_id>/approve` | `pipeline.approve_take(sid, take_id, "performance")` |
| REVIEW | `POST .../shots/<sid>/final/<take_id>/approve` | `pipeline.approve_take(sid, take_id, "final")` |

`_get_stage_pipeline(pid)` ([web_server.py:183-190](web_server.py:183)) returns
the live `CinemaPipeline` if running, else instantiates a fresh one sharing
the cached `PipelineCore` — so **operators can approve plans even when no
worker is active**, because gate state lives in `project.json`, not in memory.

---

## 4. Orchestrator — `cinema_pipeline.py` + `cinema/`

`CinemaPipeline.__init__` composes everything ([cinema_pipeline.py:43-93](cinema_pipeline.py:43)):

| Attribute | Type | Source |
|---|---|---|
| `self._core` | `PipelineCore` | [cinema/core.py:62-102](cinema/core.py:62) `build_pipeline_core(pid)` |
| `self.lifecycle` | `ThreadedLifecycle` | [cinema/lifecycle.py:110](cinema/lifecycle.py:110), fresh per pipeline |
| `self._runstate` | `RunState` | [cinema/runstate.py:60](cinema/runstate.py:60), fresh per `__init__` |
| `self._shot_ctrl` | `ShotController` | [cinema/shots/controller.py](cinema/shots/controller.py) |
| `self._review_ctrl` | `ReviewController` | [cinema/review/controller.py](cinema/review/controller.py) |
| `self._checkpoint` | `CheckpointStore` | [cinema/checkpoint.py:43](cinema/checkpoint.py:43) |

All four sub-controllers share the same `RunState` reference — mutations
propagate by reference. Forwarder block at
[cinema_pipeline.py:135-296](cinema_pipeline.py:135) (`# GENERATED BEGIN/END`,
~161 lines, 53 delegate methods) preserves backward compat for legacy callers.

### 4.1 `generate()` phase sequence

| Step | What happens | File:line |
|---|---|---|
| 1 | `_refresh_project_snapshot()`; early-return if no scenes | [cinema_pipeline.py:432-436](cinema_pipeline.py:432) |
| 2 | If `resume=True`: `_restore_from_checkpoint()` + `_rebuild_review_clips` | :876-878 |
| 3 | STYLE — `generate_style_rules` → persist | :881-914 |
| 4 | `_ensure_bgm(settings)` (FAL Stable Audio, 47s hard cap) | :916 |
| 5 | Per scene: decompose (competitive or single) → ChiefDirector validate → ensure scene audio → checkpoint | :918-977 |
| 6 | **GATE 1 PLAN_REVIEW** @ 25% | :979 |
| 7 | Build `PipelineContext` with lifecycle + global_settings + language | :992-997 |
| 8 | **KeyframeRenderPhase.run(ctx)** | :1009-1013 |
| 9 | Cancellation check | :1015-1017 |
| 10 | **GATE 2 KEYFRAME_REVIEW** @ 55% | :1019 |
| 11 | Refresh project snapshot | :1023 |
| 12 | **PerformanceCapturePhase.run(ctx)** | :1039-1043 |
| 13 | Cancellation check | :1045-1047 |
| 14 | **GATE 3 PERFORMANCE_REVIEW** @ 65% — bypassed when every shot has `performance_engine=="SKIP"` or `approved_performance_take_id`. Emits `PERFORMANCE_SKIPPED_GATE` event. | :1052-1073 |
| 15 | **MotionRenderPhase.run(ctx)** | :1086-1090 |
| 16 | Cancellation check | :1092-1094 |
| 17 | Refresh + `_rebuild_review_clips` + checkpoint | :1096-1098 |
| 18 | **GATE 4 REVIEW** @ 82% → on satisfaction call `proceed_to_assembly()` | :1099 |
| 19 | `assemble_approved_takes()` → `_assemble_final(...)`: stitch (hard cuts; opt-in scene-boundary cross-dissolve, default-off `scene_transitions`) + color grade + BGM mix + two-pass loudnorm → final mp4 | :1106-1110 |

### 4.2 `PipelineContext` ([cinema/context.py](cinema/context.py))

Dataclass + dict API. Fields:

- **Core:** `topic`, `language` (default `"English"`), `master_image_seed`.
- **Per-project UI:** `global_settings: dict` (mirrors React `project.global_settings`).
- **Lifecycle:** `lifecycle: LifecycleService = field(default_factory=NullLifecycle)`.
- **Script:** `script_data`, `production_blueprint`, `full_text`, `full_description`.
- **Audio:** `audio_path`, `voice_id`, `foley_audio_paths`, `music_vibe`, `video_pacing`, `story_tension`.
- **Output:** `final_video_path`, `final_thumbnail_path`, `metadata_path`.
- **Workspace:** `downloaded_vids: list`.
- **Max-quality:** `prev_shot_latent`, `char_lora_paths`, `style_reference_paths`.

Dict API methods at [cinema/context.py:111-143](cinema/context.py:111):
`__getitem__`, `__setitem__`, `__contains__`, `__iter__`, `get`, `update`,
`keys`, `items`, `values`, plus `as_dict()`. `__setitem__` falls back to
`setattr` so legacy code can write undeclared keys.

**Helper to read project UI knobs:**

```python
from cinema.context import get_project_setting
value = get_project_setting(ctx, "knob_name", default)
```

`get_project_setting` is the canonical fix for the historical
`getattr(settings, ...)` bug: env-derived `config.settings.Settings` is
frozen and holds API keys ONLY — UI knobs MUST come from `ctx.global_settings`
via this helper.

### 4.3 `PipelineCore` ([cinema/core.py](cinema/core.py))

Long-lived per-project deps (cached in `web_server._running_cores`):

| Field | Type | Construction |
|---|---|---|
| `project` | `dict` | `load_project(pid)` |
| `project_dir` / `temp_dir` / `export_dir` | `str` | derived paths |
| `continuity` | `ContinuityEngine` | constructed with `project` |
| `director` | `ChiefDirector` | constructed with `project` |
| `cost_tracker` | `CostTracker` | with `budget_usd` from `global_settings.budget_limit_usd` |
| `ensemble` | `LLMEnsemble` | with `settings=global_settings` |

### 4.4 `ThreadedLifecycle` ([cinema/lifecycle.py](cinema/lifecycle.py))

| Primitive | Type | Purpose |
|---|---|---|
| `_cancelled` | `bool` | Cooperative cancel flag; polled by phases |
| `_paused` | `bool` | Mirror for `is_paused()` |
| `_resume_event` | `threading.Event` (init set) | `pause()` clears; `check_pause()` waits |
| `_gate_events` | `Dict[str, threading.Event]` | Per-gate wake-up; lazy-created |
| `_gate_lock` | `threading.Lock` | Guards `_gate_events` dict only |
| `_progress_cb` | `Optional[Callable]` | Injected; `None` swallows |

`NullLifecycle` ([cinema/lifecycle.py:70-107](cinema/lifecycle.py:70)) is the
`PipelineContext.lifecycle` default + the test lifecycle: every check is
no-op, `wait_for_gate` returns True immediately. It is NOT wired into
`CinemaPipeline` (which always builds `ThreadedLifecycle`); the prior
non-interactive `main.py` CLI that used it was removed in the web-only pivot.

**Headless runs** — `CinemaPipeline(headless=True)` keeps `ThreadedLifecycle`
but sets `RunState.headless`, so `ReviewController._wait_for_gate` raises
`GateNotSatisfiedError` (naming the unsatisfied shots + reasons) instead of
polling a review gate forever when auto-approve can't clear it. This closes
the cycle-17 stall where an inline `CinemaPipeline().generate()` hung at
PLAN_REVIEW: the plan auto-approve rule reads `shot["director_review"]`, which
nothing wrote until `record_director_review_on_shots`
([cinema/auto_approve.py](cinema/auto_approve.py)) now persists the
ChiefDirector verdict at the validation step ([cinema_pipeline.py](cinema_pipeline.py)).

`cancel()` does THREE things atomically:
1. `_cancelled = True`
2. `_resume_event.set()` (unblock paused waiter)
3. `ev.set()` on EVERY existing gate Event

### 4.5 `RunState` ([cinema/runstate.py](cinema/runstate.py))

Per-run mutable. All collection fields use `default_factory`:

- `shot_results: dict` — shot_id → `{image, video, identity_score, status, take_id}`
- `review_clips: dict` — shot_id → review-clip manifest
- `scene_clips: dict` — scene_id → list of clip paths
- `scene_audio: dict` — scene_id → audio path
- `failed_shots: list`
- `current_stage / current_scene_id / current_shot_id: str` — progress triple
- `completed_scene_indices: set` — checkpoint-resume bookkeeping

### 4.6 `CheckpointStore` ([cinema/checkpoint.py](cinema/checkpoint.py))

**Atomic write** ([cinema/checkpoint.py:87-113](cinema/checkpoint.py:87)):
`tempfile.mkstemp(suffix=".json.tmp", dir=temp_dir)` →
`os.fdopen(fd, "w").write(json)` → `os.replace(tmp, path)` (POSIX atomic
rename). On any `BaseException`, the temp file is removed.

**Persisted fields:** `project_id`, `current_stage`, `current_scene_id`,
`current_shot_id`, `completed_scene_indices` (sorted list — JSON has no sets),
`scene_clips`, `scene_audio`, `shot_results`, `failed_shots`.

**On resume:** missing `image`/`video` paths set to None with
`status="lost"` ([cinema/checkpoint.py:117-134](cinema/checkpoint.py:117)).

File: `<temp_dir>/pipeline_state.json` (constant `CHECKPOINT_FILE`).

### 4.7 `services.py` (cheap snapshots)

| Function | Purpose | File |
|---|---|---|
| `state_snapshot(pid) -> dict` | Same shape as `CinemaPipeline.get_state()` minus in-memory fields | [cinema/services.py:61-97](cinema/services.py:61) |
| `checkpoint_info(pid) -> dict` | Reads `temp/pipeline_state.json` directly | [cinema/services.py:100-133](cinema/services.py:100) |
| `_project_gate_status(project)` | `{total_shots, plans_approved, keyframes_approved, motions_generated, finals_approved}` | [cinema/services.py:48-58](cinema/services.py:48) |

### 4.8 `cinema/pipeline.py` — generic driver (zero callers)

A generic `CinemaPipeline` class living at `cinema/pipeline.py` exists as a
preserved primitive but has **zero callers in production**. The orchestrator
class at the **repo root** (`cinema_pipeline.py:CinemaPipeline`) is a
different class with the same name; it does NOT inherit from nor use the
generic driver.

---

## 5. Phase protocol & three phases

`cinema/phases/base.py` ([cinema/phases/base.py:38-81](cinema/phases/base.py:38)):

```python
@dataclass
class PhaseResult:
    ok: bool
    message: str = ""
    elapsed_s: float = 0.0

@runtime_checkable
class Phase(Protocol):
    name: str
    def run(self, ctx: PipelineContext) -> PhaseResult: ...
```

Each phase is a **thin shot-iterating loop** that delegates to
`ShotController`. Partial failures don't fail the phase — `ok=True` is
hardcoded, with `on_failure(scene, shot, err)` invoked per-shot.

| Phase | Skip condition (per-shot) | Calls into |
|---|---|---|
| **KeyframeRenderPhase** | `shot["approved_keyframe_take_id"]` truthy | `ShotController.generate_keyframe_take(scene_id, shot_id)` |
| **PerformanceCapturePhase** | `approved_performance_take_id` OR `performance_engine=="SKIP"` OR `approved_keyframe_take_id` absent | `ShotController.generate_performance_take` |
| **MotionRenderPhase** | `shot["approved_final_take_id"]` (already finalized in prior run) | `ShotController.generate_motion_take` |

### 5.1 `ShotController` API ([cinema/shots/controller.py](cinema/shots/controller.py))

| Method | Calls out to | Returns |
|---|---|---|
| `generate_keyframe_take` | `style_director.style_rules_to_prompt_suffix` → `continuity.enhance_shot_prompt` → `llm.prompt_optimizer.optimize_shot_prompt` → `phase_c_assembly.generate_ai_broll` → `_get_shared_validator().validate_image` | `{success, take, image, identity_score}` |
| `generate_performance_take` | `domain.performance.route_performance_engine` → optional `driving_video.synth_driving_face_from_audio` (Mode B) → `performance._router.dispatch(engine, ...)` → `performance.identity_gate.validate_performance_take` | `{success, take, video, engine}` or `{success, skipped, engine}` |
| `generate_motion_take` | `workflow_selector.classify_shot_type` + `WORKFLOW_TEMPLATES` → `phase_c_ffmpeg.generate_ai_video` → `continuity.validate_shot` → `performance.motion_gate.score_motion_fidelity` | `{success, take, video, identity_score}` |
| `regenerate_shot` | One-shot compat wrapper: delegates to motion if keyframe approved, else keyframe | |
| `restart_shot` | Clears all approval pointers (preserves take history) → `generate_keyframe_take` | |
| `diagnose_clip` | `_get_shared_validator().validate_image` + `assess_motion_quality` + `assess_coherence` → records `{tool, reason}` recommendations | |
| `apply_correction` | Dispatches by action: `regenerate_image`/`regenerate_video`/`face_swap`/`lip_sync`/`rife`/`upscale`/`color_grade`/`speed`. `voice_regen` is hard-error. | |
| `generate_scene_preview` | Reuses cached `scene_clips` or rebuilds from `approved_final_take_id` → `stitch_modules` | |

---

## 6. Gate mechanism — predicate-poll

**Important runtime invariant:** gates are NOT event-driven. The worker
thread polls every 500ms by re-reading project state from disk and asking
the predicate.

```python
# cinema/lifecycle.py:182-198
def wait_for_gate(self, name, predicate, poll_interval=0.5) -> bool:
    with self._gate_lock:
        ev = self._gate_events.setdefault(name, threading.Event())
    while not self._cancelled:
        if predicate():
            return True
        ev.wait(timeout=poll_interval)
        ev.clear()
    return False
```

Two unblock paths:
1. **Operator approves via REST** → endpoint mutates `project.json` →
   predicate poll returns True.
2. **`lifecycle.signal_gate(name)`** sets the Event for immediate wake-up
   (optional optimization, ReviewController currently doesn't use it).

Implications:
- Operator approvals work even when SSE is disconnected.
- Approvals survive worker crashes — state lives on disk.
- A 500ms-bounded latency between approval and resume.

### 6.1 `_gate_satisfied` predicates ([cinema/review/controller.py:214-236](cinema/review/controller.py:214))

| Gate | Predicate |
|---|---|
| PLAN_REVIEW | all shots have `plan_status == "approved"` |
| KEYFRAME_REVIEW | all shots have `approved_keyframe_take_id` |
| PERFORMANCE_REVIEW | for every shot: `performance_engine == "SKIP"` OR no `approved_keyframe_take_id` OR `approved_performance_take_id` is set |
| REVIEW | all shots have `approved_final_take_id` |

PERFORMANCE_REVIEW is symmetric with the other three gates as of 2026-05-24:
the predicate at [cinema/review/controller.py:223-235](cinema/review/controller.py:223)
covers all three satisfaction paths (SKIP routing, missing keyframe, explicit
approval). The orchestrator's `all_skipped` short-circuit at
[cinema_pipeline.py:1024-1044](cinema_pipeline.py:1024) is now redundant for
correctness but kept for the explicit `PERFORMANCE_SKIPPED_GATE` UX event.

Approve endpoint: `POST /api/projects/<pid>/shots/<sid>/performance/<take_id>/approve`
→ `pipeline.approve_take(sid, take_id, "performance")` →
sets `shot["approved_performance_take_id"]`.

### 6.2 Take approval mechanics

| `approval_kind` | What it sets |
|---|---|
| `"keyframe"` | `shot["approved_keyframe_take_id"] = take_id` |
| `"final"` | If take is a postprocess variant, walks `source_take_id` chain to underlying motion_take; sets both `approved_motion_take_id` AND `approved_final_take_id` |

Multiple alternates per shot are stored as elements of `keyframe_takes[]`,
`motion_takes[]`, `postprocess_variants[]` arrays. Approval is just setting
the pointer ID; the array is not mutated.

---

## 7. Story prep — decompose, dialogue, continuity

### 7.1 Project lifecycle

1. Operator creates project ([domain/project_manager.py:605](domain/project_manager.py:605)).
2. Operator uploads character photos → FLUX Kontext MAX MULTI generates 5
   multi-angle synthetic refs; GhostFaceNet embedding cached as `embedding.npy`.
3. Operator defines locations → `prompt_fragment` + deterministic seed.
4. Operator creates scenes (`make_scene(...)`).
5. Optional: operator triggers dialogue generation per scene.
6. Optional: operator triggers style-rules generation.
7. Decomposition runs either operator-eager OR pipeline-lazy (see §7.3).
8. ChiefDirector validates each scene's shots → APPROVED/MODIFIED/REJECTED.
9. ContinuityEngine adds character identity, location prompt, physics constraints,
   img2img continuity_config per shot.
10. PLAN_REVIEW gate.

### 7.2 `project_manager.py` defaults

`make_project()` ([domain/project_manager.py:309](domain/project_manager.py:309))
seeds these `global_settings`:

```python
"aspect_ratio": "16:9",
"music_mood": "suspense",
"color_palette": "",
"master_seed": random.randint(100000, 999999),
"style_rules": {},
"budget_limit_usd": 0,
"identity_strictness": 0.60,
"creative_llm": "auto",
"quality_judge_llm": "auto",
"competitive_generation": True,
"adaptive_pulid": True,
"coherence_check_enabled": True,
"color_drift_sensitivity": 0.3,
```

`normalize_project_schema()` ([domain/project_manager.py:540-547](domain/project_manager.py:540))
**actively strips** three legacy keys from any project.json loaded from disk:
`vbench_overall_threshold`, `temporal_flicker_tolerance`, `regression_sensitivity`.

**Filelock:** 10s default timeout via `FileLock(project.lock, timeout=10)`
at [domain/project_manager.py:71](domain/project_manager.py:71).

**Storage:** `domain/projects/<12-hex-id>/` with `project.json`,
`characters/<cid>/`, `locations/<lid>/`, `shots/<sid>/`, `exports/`, `temp/`.

### 7.3 Decomposition has TWO trigger paths

1. **Operator-initiated, eager** — `POST /api/projects/<pid>/scenes/<sid>/decompose`
   ([web_server.py:1348](web_server.py:1348)) calls `decompose_scene` directly.
   UI button on the setup screen.
2. **Pipeline-internal, lazy** — `cinema_pipeline.py:910-947` inside the main
   scene loop, only runs if `scene.get("shots", [])` is empty. Honors
   `settings["competitive_generation"]` (default `True`).

### 7.4 LLM decomposer

| Function | Provider | Tooling |
|---|---|---|
| `decompose_scene` ([domain/scene_decomposer.py:429](domain/scene_decomposer.py:429)) | **GPT-4o only**, via `web_research.run_with_tools` (Tavily + Firecrawl, `max_tool_rounds=2`) | fallback to `_fallback_decompose` |
| `competitive_decompose_scene` ([domain/scene_decomposer.py:617](domain/scene_decomposer.py:617)) | `LLMEnsemble.competitive_generate(task_type="decompose", ...)` — Anthropic + OpenAI in parallel + judge | fallback to single-model |

**Persona:** CineDecompose v1.0 with 5 hard constraints:
- HC1 IDENTITY_FIREWALL — LLM must NEVER describe face/hair/skin/eye color
  (those come from PuLID reference injection downstream)
- HC2 SCHEMA_LOCK
- HC3 LOCATION_LOCK
- HC4 LIGHTING_LOCK
- HC5 FACE_DIRECTION

Plus 4 tripwires and an explicit `[SHOT][SCENE][ACTION][OUTFIT][QUALITY]`
output schema.

**Target shot count:** `max(2, min(5, int(duration / 2.5)))` — so a 5s scene
gets 2 shots; a 12.5s scene gets 5.

**Output per shot:** `prompt, camera, visual_effect, target_api, scene_foley,
characters_in_frame, action_context`. `target_api` IS set per-shot (Rule R5);
falls through to `"AUTO"` if LLM returns an unrecognized key.

### 7.5 `ContinuityEngine` ([domain/continuity_engine.py](domain/continuity_engine.py))

Composes 4 subsystems:

1. `CharacterContinuityTracker` ([:35](domain/continuity_engine.py:35)) — preloads embeddings, builds identity-anchored prompt fragments (respecting HC1), tracks wardrobe via `appearance_log`.
2. `LocationPersistence` ([:234](domain/continuity_engine.py:234)) — wraps `location_manager.get_location_prompt()` + `get_location_seed()`.
3. `PhysicsPromptEngineer` ([:261](domain/continuity_engine.py:261)) — appends physics constraint clauses.
4. `TemporalConsistencyManager` ([:339](domain/continuity_engine.py:339)) — manages img2img chaining with `denoise_strength ∈ {0.30, 0.40, 0.50, 0.55}` based on transition type.

**Key public methods:**
- `enhance_shot_prompt(shot, scene, previous_shot, shot_index, approved_anchor_image)` → returns shot with appended prompt + `continuity_config` dict.
- `validate_shot(video_path, expected_chars, threshold, shot_type, mode, attempt, max_attempts)` — delegates to shared `IdentityValidator`.

### 7.6 Root shim files

These six files at repo root are ~400-byte `from domain.X import *` re-export
shims (verified by `wc -c`):
`character_manager.py`, `continuity_engine.py`, `dialogue_writer.py`,
`location_manager.py`, `project_manager.py`, `scene_decomposer.py`.

**`pipeline_context.py` (645 bytes, NOT a shim)** loads
`config/prompts/pipeline_context.md` into a module-global `PIPELINE_CONTEXT`
string consumed by `domain/scene_decomposer.py`, `domain/dialogue_writer.py`,
`llm/style_director.py`, `llm/chief_director.py`.

### 7.7 Validation & opt-in escalation patterns

Two cross-cutting conventions emerged across Sessions 8, 10, and 12 that shape
how `project_manager.py` and the review pipeline handle schema validation and
feature gating. Both follow a "default-off, ship-the-infrastructure-now,
operator-opts-in-later" shape.

#### 7.7.1 Pydantic schema boundary (Session 8 — `ceb0a32` + `f9b0aff`)

[domain/models.py](domain/models.py) defines a Pydantic v2 `Project` model
([:166](domain/models.py:166)) mirroring the project.json structure
(scenes, characters, locations, shots, takes, settings). The boundary is
enforced via `_validate_project()` at
[domain/project_manager.py:620](domain/project_manager.py:620), called on
both save and load paths through `project_manager.py`.

**Default contract is warn-only.** Any `ValidationError` (or even
non-Validation exceptions) is logged and swallowed; the operation proceeds
with the raw dict. This permissive default was chosen so existing pre-S8
project files don't crash the pipeline mid-run.

The model uses `extra="allow"` so unknown fields don't trigger errors — trades
strict-shape enforcement for forward/backward compatibility.

#### 7.7.2 Opt-in escalation pattern (Sessions 10, 12)

Two env flags formalize an "opt-in production escalation" convention.

**`CINEMA_STRICT_SCHEMA`** (Session 10 — `5f2fe0b`). When set, `_validate_project()`
re-raises `ValidationError` instead of warning, letting callers crash hard
rather than persist invalid schema. Parser at
[domain/project_manager.py:633](domain/project_manager.py:633):

```python
strict = os.environ.get("CINEMA_STRICT_SCHEMA", "").strip() in (
    "1", "true", "TRUE", "yes",
)
```

Literal-case tuple form — does NOT accept `"True"` (Python's `str(True)`) or
other mixed-case truthy values. First caller migration:
`api_generate_dialogue` at [web_server.py:1344](web_server.py:1344) — uses the
canonical migration recipe at
[docs/MIGRATION-PATTERN-pydantic-caller.md](docs/MIGRATION-PATTERN-pydantic-caller.md).

**`CINEMA_AUTO_APPROVE_MOTION`** (Session 12 — `2a25c2d`). When set,
`cinema/review/controller.py`'s `_gate_map` is extended with
`"PERFORMANCE_REVIEW" → "motion"`, wiring the motion-gate auto-approve
rules (themselves shipped tested-but-dead in Session 11) into production.
Helper at [cinema/auto_approve.py:523](cinema/auto_approve.py:523); conditional
at [cinema/review/controller.py:270-271](cinema/review/controller.py:270).
Parser at [cinema/auto_approve.py:532](cinema/auto_approve.py:532):

```python
return os.environ.get("CINEMA_AUTO_APPROVE_MOTION", "").strip().lower() in {
    "1", "true", "yes",
}
```

`.strip().lower()` form — case-insensitive + whitespace-tolerant. Accepts
`"True"`, `"YES"`, `"  1  "`, etc. Deliberately broader than
`CINEMA_STRICT_SCHEMA`'s parser; a future cleanup unifying the two should
prefer Session 12's form ([docs/HANDOFF-roadmap-2026-05-24.md:2470](docs/HANDOFF-roadmap-2026-05-24.md)
documents the divergence).

**Why opt-in over default-on:** Both gates ship tested behavior behind a flag
so v1 defaults don't shift under existing deployments. Operators promote them
to production after validating against their content (calibration data for
motion thresholds; schema-stable project files for strict mode). See
[DECISIONS.md ADR-014](DECISIONS.md) for the motion-gate decision record; the
same rationale applies to `CINEMA_STRICT_SCHEMA`.

#### 7.7.3 Two-class flag taxonomy

Empirically the codebase now uses two classes of `CINEMA_*` env flags
with distinct lifecycle and defaults. Both share the same parser
shape (`.strip().lower()` membership-test against a set of literals);
they differ in which set and which default. The classes are
documented separately so future flags can be classified at design
time rather than retrofitted post-hoc.

##### Class A — Opt-in production escalation (default OFF)

Examples: `CINEMA_STRICT_SCHEMA` (§7.7.2), `CINEMA_AUTO_APPROVE_MOTION`
(§7.7.2).

**Lifecycle:** stays default-off indefinitely. Operators opt in
per-deployment after validating against their content (e.g.,
schema-stable project files for strict mode; calibration data for
motion thresholds). The flag is the public surface of a behavioral
escalation that's safe-by-default-off.

**Parser shape:**
```python
return os.environ.get("CINEMA_<NAME>", "").strip().lower() in {
    "1", "true", "yes",
}
```

**Class A conventions for new flags:**

- **Default off.** Ship tested behavior behind the flag; never
  silently change v1 default behavior.
- **Parse `.strip().lower() in {"1", "true", "yes"}`** (S12's
  broader form per the divergence resolution above).
- **Co-locate the helper with the feature it gates** — not at a
  central feature-flag registry. Operators opt-in per-feature; the
  helper lives where the feature lives.
- **Document via ADR in `DECISIONS.md`** mirroring ADR-014's shape
  (Context → Decision → Consequences → Alternatives → Tracking).

##### Class B — Opt-out UX feature flag (default ON post-validation)

Examples: `CINEMA_DIRECTORIAL_ITERATION` (S15-S18, cycles 8-9; flag-
flipped at v5.1+ ship `8ab0bbb` + flag-flip `44f6beb` on 2026-05-26),
`CINEMA_SCREENING_STAGE` (S19-S21, cycle 9; same flag-flip).

**Lifecycle:** has two phases.

1. **Phase 1 (Class A shape, default OFF) — pre-validation.** While
   the feature is being built + reviewed, the flag stays default-off
   so deployments don't silently pick up incomplete UX. Same parser
   shape as Class A (`in {"1", "true", "yes"}`).
2. **Phase 2 (default ON, explicit opt-out) — post-validation
   flag-flip.** After operator-validation passes (per the
   `BRIEF-operator-validation-*` template + flag-flip-recommendation
   from joint operator+director REPLY), user-principal authorizes
   the flag-flip. The parser inverts to:
   ```python
   return os.environ.get("CINEMA_<NAME>", "").strip().lower() not in {
       "0", "false", "no",
   }
   ```
   Default is now ON; operators set `CINEMA_<NAME>=0` to opt out
   (e.g., a deployment that needs the pre-flip endpoint behavior
   for legacy compatibility).

**Why Class B exists separately from Class A:** Class A's
"default-off forever" works for production escalations where each
deployment needs to make its own validation call. UX features behind
flags are NOT that — they're built behind a flag to defer the
default-flip decision until cross-cutting validation passes (UI
correctness, contract-layer review, browser playthrough). Without
Class B's framing, a long-lived Class A flag for a UX feature
locks the feature in default-off purgatory; engineering investment
doesn't translate to user value.

**Class B conventions for new flags:**

- **Default off during Phase 1.** Same as Class A; ship tested
  behavior behind the flag.
- **Validate via the operator-validation brief template** (see
  `docs/BRIEF-operator-validation-*.md` for the cycle-10
  reference shape).
- **Flip to Phase 2 default-on** after operator + director joint
  flag-flip-recommendation + user-principal authorization. The
  flip is a single semantic-inversion edit + 404 error-message
  refresh + test-fixture update (clear-env → set-env=0).
- **Parser shape inverts the set** (truthy-enable → falsy-disable).
  Whitespace-tolerance + case-insensitivity preserved.
- **Document the flip in DECISIONS.md OR in the bundle ship commit
  body** so the lifecycle is auditable.

##### Cross-reference convention

Endpoint docstrings that gate on a flag should cite the relevant
class:

- Class A: "Feature-flagged behind CINEMA_NAME=1|true|yes (§7.7.3
  Class A opt-in escalation)."
- Class B: "Feature-flagged behind CINEMA_NAME (§7.7.3 Class B
  opt-out UX). Default ON; set CINEMA_NAME=0 to opt out."

##### Class-history pattern summary

Class A appeared first (S10 `CINEMA_STRICT_SCHEMA` + S12
`CINEMA_AUTO_APPROVE_MOTION`); pattern formalized in §7.7.2 +
documented in §7.7.3 (this section). Class B emerged from cycles
8-9 (S15-S21 Surface A + Surface B) — built initially as Class A
(default-off behind flag during operator-validation cycle) +
promoted to Class B at v5.1+ ship 2026-05-26 (proposal `b583305`
+ REPLY `9f032db` + ship `8ab0bbb` + flag-flip `44f6beb`).

Lane V #10 (2026-05-26, operator on `44f6beb`) surfaced the
taxonomy tension; this section's expansion codifies the two-class
shape.

#### 7.7.4 Location-research auto-population (cycle-17 — `8376784`, Part 1 of 2)

A **project-config toggle** (`location_research`, not a `CINEMA_*` env flag)
following the same default-off / ship-infrastructure-now / opt-in-later shape.
When enabled, `create_location_with_images`
([domain/location_manager.py](domain/location_manager.py)) calls the
previously-dead `research_engine.research_location_visual(description)` to fetch
real location photos via Tavily image search, downloads them locally
(`_download_url_to_file` — stdlib urllib, 10s timeout, graceful False-on-error),
and appends them to the location's existing `reference_images` slot —
supplementing user uploads. No Tavily key → `research_location_visual` returns
`[]` → behaviour identical to the no-research path.

**Part 1 (shipped, GPU-independent):** fetch → download → persist, behind the
flag (default OFF), via an additive `auto_research: bool = False` param on
`create_location_with_images`. 8 unit tests; no regressions.

**Part 2 (pending, GPU-gated):** gen-time *consumption* of location
`reference_images` as IP-Adapter / img2img conditioning does NOT yet exist —
`get_location_reference` is currently unconsumed; a location influences
generation today via `prompt_fragment` text + deterministic seed only.

**Known follow-up (on-switch coherence):** the flag's UI default is declared in
`api_engine_defaults` (`/api/config`) but read at runtime from
`project["global_settings"]["location_research"]`; the settings-save path that
persists the toggle must target `global_settings` for the opt-in to take effect
end-to-end. Resolve alongside Part 2 / the api-engine toggle wiring.

---

## 8. Image generation — production + max-tier N=8

### 8.1 Branching

[phase_c_assembly.py:90](phase_c_assembly.py:90):
```python
if quality_tier == "max":
    try: return generate_ai_broll_max(...)  # quality_max.py
    except: pass  # fall through
# production path
```

`quality_tier` is sourced from `settings.get("quality_tier", "production")`
at [cinema/shots/controller.py:375](cinema/shots/controller.py:375). Operator
picks via UI Advanced Settings; no per-shot heuristic.

### 8.2 Production tier — `phase_c_assembly.py`

Three-priority cascade inside `generate_ai_broll`:
1. **ComfyUI + PuLID** ([pulid.json](pulid.json)) — needs `server_url` + workflow JSON.
2. **FAL FLUX Kontext Max Multi** — multi-image refs.
3. **FLUX-Pro v1.1-ultra → FLUX-schnell → Pollinations** — final fallback chain.

Each branch returns `ImageGenResult(path, api_name)` naming the backend that
actually ran (`COMFYUI_PULID` on the pod; `FLUX_KONTEXT`/`FLUX_PRO`/
`FLUX_SCHNELL`/`POLLINATIONS` down the FAL chain; `QUALITY_MAX` for the max
tier), or `None` on total failure. `generate_keyframe_take` records `api_name`
to `cost_log` via `record_api_call`, so a pod generation logs
`provider='comfyui'` — distinguishable from a FAL fallback (`provider='fal'`).
The cost site previously hardcoded the api_name from `quality_tier`,
mislabeling every pod generation as `fal` (e.g. cycle-17 cost_log row 1065).

`RunPodComfyUI` class ([phase_c_assembly.py:12-50](phase_c_assembly.py:12)):

| Method | Endpoint | Notes |
|---|---|---|
| `upload_image(image_path)` | `POST {server}/upload/image` | Returns `name` |
| `queue_prompt(workflow)` | `POST {server}/prompt` | Returns `prompt_id` |
| `get_image(filename, ...)` | `GET {server}/view?...` | Raw bytes |
| `get_history(prompt_id)` | `GET {server}/history/{id}` | For polling |

Polling: 2s × up to 300 iterations (~10 min) in production, 900s default in
quality_max.

### 8.3 Max tier — `quality_max.py` (N=8 adaptive best-of)

Workflow file: [pulid_max.json](pulid_max.json) (cached at module level with
`_WORKFLOW_LOCK`).

**Adaptive halt loop** ([quality_max.py:784-792](quality_max.py:784)):
```
while len(scores) < n_max:
    starting_index = len(scores)
    tasks = [...]  # pre-compute seeds + paths so workers don't race on len(scores)
    with ThreadPoolExecutor(max_workers=parallel_workers) as pool:
        for result in pool.map(_run_candidate, tasks):
            scores.append(result.cs)
    if should_halt(scores).halt: break
```

`parallel_workers` is the project setting `max_quality_parallel_workers`
(default 1, clamp [1, 4]). Default-1 preserves the historical sequential
behavior byte-for-byte. With workers > 1, the ComfyUI submit + poll +
download + score cycles overlap on the same pod; the GPU still serializes
model execution but the I/O + scoring phases run concurrent. Measured
speedup at workers=4 on a 4-candidate batch: ~3.9× wall-clock. `pool.map`
yields in submission order so log + scores ordering is stable regardless
of workers count.

**Halt rule** ([face_validator_gate.py:225-248](face_validator_gate.py:225)) — mode
selected by the `max_halt_rule` config enum, passed as `should_halt(halt_rule=...)`:
- `n >= halt_min_n (default 4) AND best.composite >= halt_threshold_composite (default 0.92)`
- OR `n >= halt_max_n (default 8)` (budget halt — **unconditional for all modes**)
- **`composite_only` (default):** `halt_threshold_arc=0.85` is **informational only** — not gated.
- **`conjunctive`:** also requires `best.arc >= halt_threshold_arc` (the identity floor),
  auto-satisfied for no-character / no-arc shots (`not has_character or not has_arc`) so
  landscape shots still early-halt instead of burning the full budget (T4 + Lane-V guard `bf86262`).
- **`budget_only`:** deferred — falls back to `composite_only` behavior.

**Composite score:** `0.6 * arc + 0.4 * aesthetic`. Missing scores neutral-fall to 0.5.

**Aesthetic scorer:** LAION
`shunk031/aesthetics-predictor-v2-sac-logos-ava1-l14-linearMSE` + CLIP ViT-L/14.

**Workflow injection passes:**
- `_inject_identity` — LoRA, face_anchor, PuLID weight; honors a per-character
  `char_lora_strength` override on node-700 (`0.0` honored; independent
  `strength_model`/`strength_clip` fallbacks preserved when unset), threaded from
  the validated LoRA-gate sweep (see "LoRA quality gate" below)
- `_inject_conditioning` — prompt, CN strengths, Redux refs
- `_inject_sampling` — AYS steps, sampler, PAG, **SLG**, **FreeU**, **DetailDaemon**
- `_inject_latent_source` — EmptyLatent | VAEEncode | LatentBlend
- `_inject_post_passes` — FaceDetailer, **SUPIR**, **hires_fix Pass-2** (when
  `hires_fix_enabled`: node 18 = deepcopy of the node-17 scheduler at gentler
  denoise [default 0.40] + fewer steps [`hires_fix_steps`, default 18, range 5–40],
  re-pointing the node-901 refine-pass sigmas — a photorealism lever vs. the old
  full-denoise=1.0 painterly refine; **pod-unvalidated hypothesis**), final 4K
  resolution (default 3840×2160)

| Technique | What it does | Default params |
|---|---|---|
| **FreeU V2** | Training-free U-Net skip/backbone feature rescaling | `b1=1.3, b2=1.4, s1=0.9, s2=0.2` |
| **SLG** | Skip-Layer Guidance for Diffusion Transformers | `scale=2.5, double_layers="7,8,9", single_layers="10,11"` |
| **DetailDaemon** | Sampler wrapper injecting noise to surface micro-detail | `detail_amount=0.5` |
| **SUPIR V2** | Scaling Up Image Restoration as final post-pass | `steps=50, cfg_scale_start/end=4.0` |
| **Final downsample** | Latent upscale + downsample to target | `(3840, 2160)` |

**No Topaz in the live path.** Operator-side Topaz prep lives in
`prep/topaz_upscale.py`.

**LoRA quality gate** ([prep/lora_quality.py](prep/lora_quality.py)) — before render,
`train_character_lora_gated` runs a bounded train→validate→retrain loop (≤3 trains,
keep-best, reject-if-net-negative). `validate_lora_quality` is the ArcFace oracle: it
sweeps strength × prompts against the reference and picks the best per-character
strength, persisted as `char_lora_strengths` (web `api_train_lora` → status
`record_lora_verdict`; `get_lora_status` surfaces `rejected`/`quality_warning`). The
render path's `_inject_identity` (above) then bakes each LoRA at its **validated**
strength instead of the tier default `1.0` — closing the 1.0-over-bake realism gap
(0.55 beats 1.0; 2026-06-02 char-LoRA finding). Gracefully skips (registers
unvalidated) when ComfyUI/GPU is unreachable; live threshold/baseline/sweep
calibration is GPU-pod (Phase-B) work. Status: `pipeline_status.toml::lora_validation
= wired` (T1, `9f2ace6..6f7df8d`). The old `-1.0` stub in `prep/lora_training.py` is
gone; `prep/lora_training.py::train_character_lora` is now a pure single-train the gate
orchestrates.

### 8.4 Identity-validator integration

`face_validator_gate._get_validator()` returns `identity.get_shared_validator()`
— the canonical singleton. Per-candidate score uses `validate_image(threshold=0.0)`
which appends to the shared `IdentityValidator.history` (see §11).

---

## 9. Video routing — 5 templates × 11 engines

### 9.1 `WORKFLOW_TEMPLATES` ([workflow_selector.py:21-109](workflow_selector.py:21))

| Shot type | `target_api` | `video_fallbacks` |
|---|---|---|
| `portrait` | `KLING_NATIVE` | `["RUNWAY_GEN4", "SORA_NATIVE", "KLING_3_0"]` |
| `medium` | `KLING_NATIVE` | `["RUNWAY_GEN4", "SORA_NATIVE", "LTX"]` |
| `wide` | `LTX` | `["VEO_NATIVE", "KLING_NATIVE", "RUNWAY_GEN4"]` |
| `action` | `SORA_NATIVE` | `["KLING_NATIVE", "RUNWAY_GEN4", "LTX", "SEEDANCE"]` |
| `landscape` | `LTX` | `["VEO_NATIVE", "KLING_NATIVE"]` |

A parallel `MAX_QUALITY_TEMPLATES` dict at [workflow_selector.py:143-370](workflow_selector.py:143)
mirrors these with different fallback orderings.

**SEEDANCE appears only in the `action` cascade** (last fallback). It is
NOT a general multi-character fallback. Two-character dialogue shots
classify as `medium` and route Kling → Runway → Sora → LTX.

### 9.2 `classify_shot_type` keyword map ([workflow_selector.py:411-432](workflow_selector.py:411))

Empty `characters_in_frame` → `landscape`; otherwise concatenate `[SHOT]` +
prompt + camera into a search string, first containment match wins; default `medium`.

| Shot type | Keywords |
|---|---|
| `portrait` | close-up, closeup, close up, portrait, ecu, extreme close, 85mm, **macro**, headshot, face shot, tight shot |
| `action` | tracking, tracking shot, crane, dolly, rapid, chase, running, action, dynamic, handheld, steadicam |
| `wide` | wide shot, wide angle, establishing, 24mm, 16mm, full shot, long shot, master shot, extreme wide |
| `landscape` | landscape, aerial, drone, skyline, panoramic, environment, scenery, no character |
| `medium` | medium, 50mm, mid-shot, waist, hip, american shot, cowboy shot, two-shot |

### 9.3 `MOTION_FIDELITY_FLOORS` ([workflow_selector.py:395-402](workflow_selector.py:395))

| Shot type | Floor |
|---|---|
| `portrait` | 0.42 |
| `medium` | 0.55 |
| `wide` | 0.65 |
| `action` | 0.60 |
| `close_up` | 0.50 |
| `landscape` | None |

(`close_up` is unreachable from `classify_shot_type` since that returns only
the 5 top-level keys, but `normalize_shot_type` may produce it from caller-side
shot type strings.)

### 9.4 `generate_ai_video` dispatch ([phase_c_ffmpeg.py:43-738](phase_c_ffmpeg.py:43))

| Engine | File:line | Adapter | Auth |
|---|---|---|---|
| `KLING_NATIVE` | :179-206 | `kling_native.KlingNativeAPI` | JWT HS256 (KLING_ACCESS_KEY + KLING_SECRET_KEY) |
| `SORA_NATIVE` | :208-243 | `sora_native.SoraNativeAPI` | OPENAI_API_KEY |
| `VEO_NATIVE` | :245-269 | `veo_native.VeoNativeAPI` | Vertex AI or GEMINI_API_KEY |
| `LTX` | :271-307 | `ltx_native.LTXVideoAPI` | LTX_API_KEY OR FAL_KEY |
| `RUNWAY_GEN4` | :309-357 | inline `runwayml` SDK (`gen4`) | RUNWAYML_API_SECRET |
| `SORA_2` | :363-411 | inline `fal_client.subscribe("fal-ai/sora-2/image-to-video")` | FAL_KEY |
| `VEO` | :413-484 | inline `fal_client.subscribe("fal-ai/veo3.1/reference-to-video")` | FAL_KEY (gated by `_veo_quota_blocked`) |
| `KLING_3_0` | :486-569 | inline `fal_client.subscribe("fal-ai/kling-video/v3/pro/...")` | FAL_KEY |
| `FAL_SVD` | :571-629 | inline `fal_client.subscribe("fal-ai/fast-svd")` | FAL_KEY; **not in any cascade** |
| `RUNWAY` | :631-661 | inline `runwayml` SDK (`gen3a_turbo`) | RUNWAYML_API_SECRET |
| `SEEDANCE` | :663-734 | inline `requests.post("https://api.seedance.ai/v1/video/generate")` | SEEDANCE_API_KEY |

### 9.5 Default cascade (when `video_fallbacks=None`)

[phase_c_ffmpeg.py:112-115](phase_c_ffmpeg.py:112):
```python
fallback_list = [
    "KLING_NATIVE", "SORA_NATIVE", "RUNWAY_GEN4",
    "LTX", "VEO_NATIVE", "KLING_3_0", "SORA_2", "VEO", "RUNWAY",
]
```

`FAL_SVD` and `SEEDANCE` are reachable only via explicit `target_api=` or the
`action` cascade.

### 9.6 VEO quota gate

**TTL-based** (commit `feccf61`):
- Variable: `_VEO_QUOTA_EXHAUSTED_UNTIL: float = 0.0` ([phase_c_ffmpeg.py:18](phase_c_ffmpeg.py:18))
- TTL: `_VEO_QUOTA_TTL_S: int = 1800` (30 min) ([:19](phase_c_ffmpeg.py:19))
- Check: `_veo_quota_blocked()` ([:22-28](phase_c_ffmpeg.py:22))
- Set on 429/quota error ([:503-506](phase_c_ffmpeg.py:503))
- Gates only the `VEO` (FAL) branch — NOT `VEO_NATIVE`

### 9.7 Helper functions in `phase_c_ffmpeg.py`

12 functions total. Core: `_veo_quota_blocked`, `generate_ai_video`,
`stitch_modules` (ffmpeg concat demuxer), `split_video_into_segments`,
`assess_motion_quality` (OpenCV Farneback flow →
{smoothness, frozen_ratio, recommendation∈{accept,interpolate,regenerate}}),
`apply_color_grade` (8 named presets + optional LUT3D), `adjust_speed` (setpts
+ atempo), `two_pass_loudnorm` (EBU R128 — pass-1 measure via JSON parse of
stderr, pass-2 normalize; defaults `I=-14 LUFS, LRA=11, TP=-1.5 dBTP`).
**Scene transitions (opt-in, cycle-17):** `xfade_concat` chains per-scene videos
with an xfade (video) + a *conditional* acrossfade — audio is crossfaded only when
every input has an audio stream (`_has_audio_stream`); otherwise the output is
video-only (the default Kling-Native/LTX silent path, where an unconditional
acrossfade referenced a non-existent `[0:a]` and errored → silent hard-cut
fallback; Lane V #24 F1). Probes each scene, clamps the transition to ≤0.4× the
shortest scene, re-encodes once; built on `_probe_duration` +
`_build_xfade_filtergraph` (+ `_fmt`). Raises on ffmpeg failure so `_assemble_final`
falls back to a plain hard-cut concat. Mixed audio-presence inputs (some scenes
with embedded audio, some without) pad the silent legs with `anullsrc` + normalize
every leg, preserving embedded audio across the stitch (Lane V #25 M1, fixed).

---

## 10. Performance capture & lipsync

### 10.1 `performance/_router.dispatch()`

| Engine | Semaphore | Driving video |
|---|---|---|
| `ACT_ONE` | `Semaphore(1)` | Optional (Mode A override of audio-only) |
| `LIVE_PORTRAIT` | `Semaphore(2)` | **Required** — bails to None if absent |
| `VIGGLE` | `Semaphore(1)` | **Required** — Mode A only (no autopilot) |
| `SKIP` / empty | (bypass) | early `return None` |

Limits declared at [performance/_router.py:21-25](performance/_router.py:21).
No timeout on semaphore acquisition — callers block indefinitely. Per-adapter
poll timeouts bound the overall hold time (300s in act_one/live_portrait/viggle,
240s in driving_video helpers).

### 10.2 Mode A vs Mode B

- **Mode A:** operator pre-uploads a driving video. Controller passes
  `driving_video_path` directly to dispatch.
- **Mode B autopilot (ACT_ONE + LIVE_PORTRAIT only):** controller calls
  `driving_video.synth_driving_face_from_audio` BEFORE dispatch to manufacture
  the driving video from TTS audio.

### 10.3 `driving_video.py` cascade ([performance/driving_video.py:243-303](performance/driving_video.py:243))

| Engine | Cloud/Local | Trigger | Endpoint |
|---|---|---|---|
| **Hedra Character-3 via FAL** | cloud | `engine∈("auto","hedra")` AND `FAL_KEY` set | `fal-ai/hedra/character-3` |
| **Hedra direct REST** | cloud | Hedra FAL fails AND `HEDRA_API_KEY` set | `https://api.hedra.com/v1/audio/talking-image` |
| **SadTalker via ComfyUI** | **local** (RunPod/Railway pod) | After Hedra paths fail | `LoadImage + LoadAudio + SadTalker` ComfyUI nodes |
| **Cache hit** | n/a | Content-hash match | Skip API entirely |

Cache key: `SHA256(audio_bytes + keyframe_bytes + rounded_duration)`. Stored
under `data/cache/driving/`. Avoids re-charging Hedra (~$0.05/shot) on
regenerate when inputs unchanged.

Return: `Optional[Tuple[str, str]]` — `(path, provider_name)` where
provider_name ∈ `{"hedra", "sadtalker", "cache"}`.

### 10.4 `motion_gate.py` (advisory only)

`score_motion_fidelity(motion_clip, driving_clip, num_pairs=8)`:

1. Sample N consecutive frame pairs uniformly across each clip.
2. Resize to 320×180 grayscale.
3. Dense Farneback optical flow per pair.
4. **2D histogram of (magnitude × direction)** — 12 bins each → **144 cells total**.
5. Cosine similarity between the two clip-aggregate 144-vectors.

`needs_remotion(score, shot_type)` returns False when score is None
(inconclusive defer to operator) AND when no floor is configured.
**Nothing in `_router.py` or any adapter calls `needs_remotion`** — it's
purely informational for the PERFORMANCE_REVIEW gate.

### 10.5 `identity_gate.py`

`validate_performance_take(video_path, face_anchor, floor=0.70)`:
1. ffmpeg extracts 1-frame at t=1.0s to tempfile PNG.
2. `validator.validate_image(frame, anchor, threshold=0.0)` — appends to
   shared rolling history.
3. Returns raw score; `floor` parameter is **accepted but never used in the
   body** — decision is deferred to the caller / operator gate.

### 10.6 Lipsync ([lip_sync.py](lip_sync.py))

**Dialogue default (F1b overlay pass):** As of 2026-06-03, dialogue shots
(`dialogue_close_up` / `talking_head_full`) default to
**Veo silent video → per-shot TTS → lip-sync OVERLAY** instead of
Veo's embedded voice. This gives Veo's look with a consistent character voice.
The flow is controlled by `dialogue_voice_mode` (see §10.7).

**Overlay cascade** (existing video + audio → lip-sync overlaid, all cloud via FAL):

| Order | Engine | Endpoint |
|---|---|---|
| 0 | sync.so v3 | `fal-ai/sync-lipsync/v3` |
| 1 | MuseTalk | `fal-ai/musetalk` |
| 2 | LatentSync | `fal-ai/latentsync` |
| 3 | Sync Lipsync v2 | `fal-ai/sync-lipsync/v2` |

**Generation cascade** (still image + audio → full talking-head; order-0 is a
direct native call, orders 1–3 cloud via FAL):

| Order | Engine | Endpoint |
|---|---|---|
| 0 | Hedra Character-3 (direct) | `api.hedra.com/web-app/public` ([`hedra_native.HedraAPI`](hedra_native.py:25)) |
| 1 | Kling lipsync | `fal-ai/kling-video/lipsync/audio-to-video` |
| 2 | Omnihuman v1.5 | `fal-ai/bytedance/omnihuman/v1.5` |
| 3 | Creatify Aurora | `fal-ai/creatify/aurora` |

ATTEMPT-0 is now a **direct** Character-3 call —
[`hedra_native.HedraAPI.generate_talking_head`](hedra_native.py:60) →
`api.hedra.com/web-app/public` (model `d1dd37a3-…`), wired `cb31207` to replace
the **dead** `fal-ai/hedra/character-3` FAL proxy (HTTP 404). Flow: create+upload
image asset → create+upload audio asset → POST `/generations` → poll
`/generations/{id}/status` → download. Invoked as ATTEMPT 0 from
[lip_sync.py:559](lip_sync.py:559); key from `settings.hedra_api_key` (`.env`
`HEDRA_API_KEY`). On any failure it returns `None` and the cascade falls through
to Kling → Omnihuman → Creatify.

**SyncNet quality gate** ([lip_sync.py:218-232](lip_sync.py:218)) scores each
engine's output against `lipsync_validation_threshold` (default 0.65).
Below-threshold outputs stashed (`.{engine}.tmp`); if no engine clears the bar,
the **highest-scored stashed candidate** is restored as the final output.

**Dialogue F1b overlay flow (overlay mode, per-shot line present):**
1. Per-shot TTS rendered via `_ensure_shot_audio` (falls back to `_ensure_scene_audio`
   when shot has no own line).
2. Veo duration clamped to ≥ speech length (`_clamp_veo_duration`, {4s,6s,8s}).
3. Veo runs **silent** (`generate_audio=False`); video fallback cascade kept intact
   so a Veo RAI-block falls through to a silent-video engine (overlay still fires).
4. `audio_embedded` NOT set (overlay mode). F1b pass fires:
   `generate_lip_sync_video(existing_video_path=silent_clip, audio_path=shot_tts)`.
5. On overlay success, `take.metadata.dialogue_audio_in_clip=True`; assembler
   suppresses scene-level TTS for that shot (no double-voice).

Key helpers (all in [`cinema/shots/controller.py`](cinema/shots/controller.py)):
- `_dialogue_voice_mode` (`:119`) — resolves mode from `global_settings`.
- `_resolve_dialogue_routing` (`:132`) — sets primary/fallbacks per mode.
- `_should_tag_audio_embedded` (`:182`) — gates the `audio_embedded` tag.
- `_clamp_veo_duration` (`:218`) — clamps speech length to Veo-supported duration.
- `_resolve_f1b_audio` (`:232`) — picks per-shot vs. scene-level TTS audio.

Assembler dedup: `cinema_pipeline.py:_build_scene_packages` (`:667`) counts both
`audio_embedded` and `dialogue_audio_in_clip` (`:692`) to decide TTS suppression.

### 10.7 Cascade-choice via `lip_sync_mode` and `dialogue_voice_mode`

`generate_lip_sync_video(...)` auto-routes:
- `existing_video_path` provided → `overlay`
- only image + audio → `generation`
- Operator forces via `lip_sync_mode ∈ {"auto", "overlay", "generation"}`.

**`dialogue_voice_mode` (new as of 2026-06-03):** controls how dialogue shots get audio.

| Value | Behaviour |
|---|---|
| `"overlay"` **(default)** | Veo runs silent; per-shot TTS is overlaid by F1b. Consistent character voice. RAI-block falls through cascade; overlay still fires. |
| `"native"` | Legacy: Veo generates its own embedded voice. `video_fallbacks=None`. The take is tagged `audio_embedded=True`. F1b overlay pass is skipped. |

Set via `project.global_settings.dialogue_voice_mode` (see OPERATIONS.md §8).

---

## 11. Identity validation — GhostFaceNet singleton

### 11.1 Model

`IdentityValidator` uses **DeepFace's `GhostFaceNet`** model
([identity/validator.py:347, 487, 546](identity/validator.py:347)):
```python
DeepFace.represent(..., model_name="GhostFaceNet", ...)
```

Naming clarification: everything in the codebase that says "ArcFace" actually
runs GhostFaceNet. ArcFace is the loss function GhostFaceNet was trained with;
DeepFace exposes GhostFaceNet as the model.

### 11.2 Singleton via double-checked locking ([identity/__init__.py:58-86](identity/__init__.py:58))

```python
_SHARED_VALIDATOR: Optional[IdentityValidator] = None
_SHARED_VALIDATOR_LOCK = threading.Lock()

def get_shared_validator() -> IdentityValidator:
    if _SHARED_VALIDATOR is not None:
        return _SHARED_VALIDATOR  # fast path
    with _SHARED_VALIDATOR_LOCK:
        if _SHARED_VALIDATOR is None:  # re-check
            _SHARED_VALIDATOR = make_validator()
    return _SHARED_VALIDATOR
```

`make_validator()` lazily imports `phase_c_vision.validate_identity_vision`
inside the function body — so `import identity.validator` does NOT pull
`phase_c_vision` into the import graph until first construction.

### 11.3 Four access paths — all return the same instance

Verified by id-comparison:

| Path | File:line |
|---|---|
| `identity.get_shared_validator()` | [identity/__init__.py:62](identity/__init__.py:62) |
| `phase_c_vision._get_shared_validator()` | [phase_c_vision.py:15](phase_c_vision.py:15) |
| `face_validator_gate._get_validator()` | [face_validator_gate.py:104-119](face_validator_gate.py:104) |
| `performance.identity_gate._get_validator()` | [performance/identity_gate.py:34-40](performance/identity_gate.py:34) |

### 11.4 Per-shot thresholds ([identity/types.py:92-98](identity/types.py:92))

| Shot type | strict | standard | lenient |
|---|---|---|---|
| portrait | 0.75 | 0.70 | 0.60 |
| medium | 0.70 | 0.65 | 0.55 |
| wide | 0.60 | 0.55 | 0.45 |
| action | 0.65 | 0.60 | 0.50 |
| landscape | 0.0 | 0.0 | 0.0 |

`get_threshold_for_shot(shot_type, mode, attempt, max_attempts)` linearly
interpolates from `mode` to `lenient` over retries.

Project-wide `identity_strictness` setting (default 0.60) overrides per-shot
defaults at [cinema/shots/controller.py:504](cinema/shots/controller.py:504).

### 11.5 Rolling-stats update sites (4 sites total)

`IdentityValidator.history` accumulates from:

1. **Keyframe validation** — `cinema/shots/controller.py:506` and `:1617`
2. **N=8 best-of grading** — `face_validator_gate._arcface_score` → `validate_image(threshold=0.0)`
3. **Performance gate scoring** — `performance/identity_gate._arcface_score` → `validate_image(threshold=0.0)`
4. **Continuity video validation** — `domain/continuity_engine.py:616` → `validate_video`

Consumer: `workflow_selector.get_adaptive_pulid_weight` reads
`identity_validator.get_rolling_stats(character_id)` and adjusts PuLID weight
±0.10. Three return paths all return a float — no None bug.

---

## 12. Audio pipeline

### 12.1 Modules

| File | Role | Provider(s) |
|---|---|---|
| `audio/_client.py` | Shared ElevenLabs SDK singleton | ElevenLabs |
| `audio/voiceover.py` | VOICE_DIRECTIONS dict + delivery-style resolver (lookup only — TTS-generation functions were removed 2026-05-24, see §17) | n/a (data + pure-Python lookup) |
| `audio/dialogue.py` | Multi-character dialogue TTS | ElevenLabs v3 (dialogue endpoint, then per-line fallback) |
| `audio/music.py` | BGM + mastering | FAL Stable Audio (default), Suno V5 (optional) |
| `audio/effects.py` | Voice/music DSP | Pedalboard (hard dep), macOS AU, FFmpeg |
| `audio/alignment.py` | Forced alignment | WhisperX > Whisper word_timestamps |

`audio/__init__.py` is a 20-line docstring with **no exports** — callers reach
into submodules directly.

### 12.2 Voiceover vs dialogue split

- **Voiceover** = narrator (omniscient/documentary), single-line shot TTS,
  50-entry `VOICE_DIRECTIONS` library, cross-provider TTS router.
  7-voice `NARRATOR_VOICES` pool dedicated.
- **Dialogue** = character-line list with per-character `voice_id` mapping.
  Path 1: ElevenLabs v3 Dialogue Mode (single-call multi-speaker).
  Path 2: per-line TTS + ffmpeg concat with `pause_between_lines` silence inserts.
  Optional `.alignment.json` sidecar via `forced_alignment_enabled`.

### 12.3 Pedalboard FX chain

[audio/effects.py:20-25](audio/effects.py:20) imports unconditionally — no
try/except. Effect map at [:180-189](audio/effects.py:180) supports
reverb / compressor / gain / delay / highpass / lowpass / chorus / distortion.

`apply_voice_effect` priority ([:230-284](audio/effects.py:230)):
AU plugin > Pedalboard chain > FFmpeg filter. 14 named FFmpeg presets in
`VOICE_EFFECTS` ([:28-85](audio/effects.py:28)).

### 12.4 What's wired from orchestrator

Only these imports leave `audio/`:

| Caller | Imports | At |
|---|---|---|
| `cinema_pipeline.py` | `audio.dialogue.generate_dialogue_voiceover` | top-level |
| `cinema_pipeline.py` | `audio.music.generate_fal_bgm`, `audio.music.master_music` (lazy) | inside `_ensure_bgm` |
| `audio/dialogue.py` | `audio.voiceover.get_voice_direction` | for delivery → voice-params lookup |
| `web_server.py` | `audio.voiceover.VOICE_DIRECTIONS` | for UI delivery-style dropdown |

The dormant TTS functions previously listed here (`generate_voiceover`,
`generate_narration`, `generate_single_line_audio`, `audio.foley.*`,
`audio.srt.generate_srt`) were deleted on 2026-05-24 (Bundle-D 4.3).
What remains is the live surface only.

### 12.5 BGM duration is hard-coded to 47s

[cinema_pipeline.py:523](cinema_pipeline.py:523):
`generate_fal_bgm(music_mood, bgm_path, duration=47)`. FAL Stable Audio's
practical max; loops in assembly.

### 12.6 Final-assembly audio mux — engine-dependent voice source

`_assemble_final` ([cinema_pipeline.py:1245](cinema_pipeline.py:1245)) muxes the
final video's audio with an FFmpeg `amix` filtergraph over up to three sources
(voice/dialogue + BGM + foley). The **voice source is motion-engine-dependent**:

- **Audio-embedding engines** (Omnihuman, Veo audio-drive): dialogue is baked
  into `stitched.mp4`; the filtergraph binds voice from the embedded stream
  (`[0:a]`), `amix` uses `duration=first`, no `-shortest`.
- **Silent-video engines** (Kling Native image2video — the PA-VIDEO Set-3
  default): motion clips carry **no audio**. `_concat_dialogue_track`
  ([cinema_pipeline.py:1134](cinema_pipeline.py:1134), mirrors
  `_concat_foley_track`) concatenates per-scene dialogue into a standalone track
  muxed as a separate ffmpeg input (`[N:a]`); `amix` uses `duration=longest`
  paired with `-shortest` on the output
  ([:1367](cinema_pipeline.py:1367), [:1384](cinema_pipeline.py:1384)) so audio
  plays through video length with BGM/foley filling any tail past dialogue end.
  The `mix` log label reflects the actual source (`standalone-dialogue+BGM+foley`
  vs `embedded-voice+BGM+foley`).

**Root-cause precision (Tier-B finding C-B2 / advisory LV-1):** the original
symptom — `amix=inputs=3 … matches no streams` → BGM-only fallback with dialogue
+ foley silently dropped — *looked* like a filtergraph bug. It was not: the
filtergraph was correct for embedded-audio engines. The true root cause was the
embedded-audio **assumption** breaking when PA-VIDEO routing defaulted to Kling
Native (silent video). Closed by `b11edd4` (standalone-dialogue mux) +
`ee70fd1` / `e867aac` (`duration=longest` + `-shortest` pairing).

---

## 13. LLM coordination

### 13.1 `LLMEnsemble` ([llm/ensemble.py:93](llm/ensemble.py:93))

**Pattern: parallel quorum, NOT fallback.**

- `competitive_generate(task_type, system_prompt, user_prompt, models=None, judge_model=None, json_mode=False, tool_schema=None)`.
- `ThreadPoolExecutor(max_workers=len(models))` dispatches all models concurrently.
- 120s per-future + as_completed timeout.
- A judge model scores candidates and picks a winner.
- Provider-level failures return `(model, None)`; filtered before judging.
- If only one survives → auto-winner. If judging itself fails → first valid candidate with `scores[idx]=5.0`.

**Default rosters** ([llm/ensemble.py:80-84](llm/ensemble.py:80)):
| Task | Models |
|---|---|
| `script` | `["claude-sonnet-4-20250514", "gpt-4o"]` |
| `decompose` | `["gpt-4o", "claude-sonnet-4-20250514"]` |
| `default` | `["claude-sonnet-4-20250514", "gpt-4o"]` |
| Default judge | `claude-sonnet-4-20250514` |

**Provider routing by model name prefix** ([llm/ensemble.py:231-247](llm/ensemble.py:231)):
- `claude*` → Anthropic
- `gpt*`/`o4*` → OpenAI
- `gemini*` → Gemini (via `google.genai`)

### 13.2 Gemini is opt-in but wired

`_generate_gemini` ([llm/ensemble.py:322-351](llm/ensemble.py:322)) is fully
implemented. Gemini client constructed lazily when `GEMINI_API_KEY` OR
`GOOGLE_API_KEY` is set. Judge override map exposes `gemini-pro → gemini-2.5-pro`.

To dispatch Gemini, pass `models=["gemini-2.5-pro", ...]` explicitly OR set
`quality_judge_llm="gemini-pro"` in project settings.

### 13.3 Anthropic prompt caching

`build_anthropic_system_blocks(text)` ([llm/ensemble.py:40-57](llm/ensemble.py:40))
wraps system prompts as a single content block with
`cache_control={"type": "ephemeral"}` (5-min TTL).

Used in `LLMEnsemble._generate_anthropic` and `ChiefDirector._call_llm`. Cache
hit/creation logged via `[LLM-CACHE]` prefix.

**OpenAI:** no explicit caching (OpenAI has automatic prefix cache, not exposed).
**Gemini:** no caching use.

### 13.4 `ChiefDirector` ([llm/chief_director.py](llm/chief_director.py))

Two distinct validators:

**1. `validate_shot_prompts(shots, scene)` — pre-generation**
Returns `{decision, violations, shots}` where `decision ∈ {APPROVED, REJECTED, MODIFIED}`.
8 HardConstraints (HC1–HC8) + 9 Tripwires (T1–T9).
HC1 = Identity Firewall (no face/skin/hair in prompts).
HC2 = Schema Lock. HC6 = camera-brand → perceptual-token upgrade.
JSON-parse failure → pass-through with `APPROVED` (safety net).

**2. `evaluate_generation_quality(...)` — post-generation**
2×2 matrix on `(identity_passed, coherent)`:

|  | Identity PASS | Identity FAIL |
|---|---|---|
| **Coherent** | `ACCEPT` | mutate `identity_only` |
| **Incoherent** | mutate `style_only` | mutate `aggressive` |

Decision: `RETRY | ACCEPT_LENIENT | FAIL`. Negative-prompt phrases (from
`llm.negative_prompts`) appended based on first failing character's reason.

### 13.5 `style_director.py`

**GPT-4o only** ([llm/style_director.py:106](llm/style_director.py:106)).
`run_with_tools(client, "gpt-4o", ...)` with `max_tool_rounds=3` for proactive
Tavily/Firecrawl research.

Output schema (7 keys): `director_vision`, `cinematography_rules`,
`color_grading_palette`, `lighting_rules`, `sound_design`,
`photorealism_rules`, `composition_rules`.

### 13.6 `prompt_optimizer.py`

`optimize_shot_prompt(...)` runs `competitive_generate(task_type="decompose", json_mode=True)`.
Output schema requires `suggested_video_api ∈ {KLING_NATIVE, SORA_NATIVE,
VEO_NATIVE, LTX, RUNWAY_GEN4, AUTO}`. Sanitized via `_coerce_to_valid_keys`
— unrecognized values collapse to `"AUTO"`.

LLM guidance table in `_OPTIMIZER_SYSTEM_PROMPT`:
```
dialogue_close_up:     KLING_NATIVE or VEO_NATIVE; lipsync=HEDRA_C3
talking_head_full:     VEO_NATIVE;     lipsync=HEDRA_C3 or OMNIHUMAN_V1_5
action_motion:         SORA_NATIVE;    lipsync=null
static_portrait:       KLING_NATIVE;   lipsync=null
establishing_shot:     LTX or VEO_NATIVE; lipsync=null
macro_detail:          SORA_NATIVE or LTX; lipsync=null
style_locked_sequence: RUNWAY_GEN4;    lipsync per dialogue need
```

### 13.7 `negative_prompts.py`

49 lines. `NEGATIVE_PROMPT_BY_FAILURE_REASON` dict keyed off
`identity.types.FailureReason.value` strings. Scope: per-shot, per-take,
post-failure (reactive vocabulary lookup, not upfront constraint builder).
Consumer: `ChiefDirector.evaluate_generation_quality` — uses first failing
character's reason.

### 13.8 `config/settings.py`

`@dataclass(frozen=True) Settings` ([config/settings.py:48](config/settings.py:48)).
**Env-derived API keys + paths ONLY. No UI knobs.** Cached as `@lru_cache(maxsize=1)`
singleton via `get_settings()` ([:137-139](config/settings.py:137)).

Reading project UI knobs from `settings` is a silent-failure bug
(`getattr(settings, "tts_provider", "DEFAULT")` returns the default because
the attribute doesn't exist). All project knobs MUST flow through
`get_project_setting(ctx, key, default)`.

---

## 14. Frontend — React 19 + Vite

### 14.1 Stack

| Lib | Version |
|---|---|
| React | 19.0.0 |
| Vite | 6.0.0 |
| TypeScript | 5.7.0 |
| Tailwind | 3.4.0 |

**No router.** **No query lib.** **No shadcn.** **No date/chart/icon lib.**
Raw `fetch()` everywhere.

### 14.2 Three-mode state machine ([web/src/App.tsx:17](web/src/App.tsx:17))

```tsx
const [mode, setMode] = useState<'setup' | 'pipeline' | 'console'>('setup')
```

Switch dispatch:

| Project? | Mode | Component |
|---|---|---|
| `null` | (n/a) | `ProjectSelector` |
| set | `'setup'` (default) | `EditorialShell` |
| set | `'pipeline'` | `PipelineLayout` |
| set | `'console'` | `DirectorsConsole` |

### 14.3 Two strict palettes ([web/tailwind.config.js:9-47](web/tailwind.config.js:9))

| Palette | Used by | Vibe |
|---|---|---|
| `editorial-*` | `EditorialShell` + `pipeline/*` | cool ivory on paper-black |
| `console-*` | `DirectorsConsole` + `console/*` | warm sepia |

Strict separation — Bundle-C 3.4 (2026-05-24) closed the last leak
(`TakeStrip.tsx` now uses `console-*` exclusively).

### 14.4 SSE consumption

`hooks/useSSE.ts` opens a single `EventSource('/api/projects/${pid}/stream')`,
parses JSON events, closes on `stage==='END'`. No reconnection logic.

`hooks/usePipelineState.ts` is the event router:
- `PAUSED`/`RESUMED` → `setIsPaused`
- `SHOT_FAILED` → `setFailedShots`
- Every event → `setActiveStage` + buffered last-20 `notesBuffer`
- `director_review` → `setDirectorReview`
- Per-shot events → mutate `shotStates: Map<shot_id, Partial<ShotState>>`

Returns 11 action callbacks (pause/resume + 4 gate approvals + 4 shot operations + proceedToAssembly).

### 14.5 Gate approval HTTP map

| Gate | UI location | Endpoint |
|---|---|---|
| PLAN_REVIEW | `ReviewStage.tsx` "Approve Plan" | `POST /api/projects/<pid>/shots/<sid>/plan/approve` |
| KEYFRAME_REVIEW | `ReviewStage.tsx` per-take Approve | `POST .../keyframes/<take_id>/approve` |
| PERFORMANCE_REVIEW | `ReviewStage.tsx` Performance Capture section, Approve button next to Re-record | `POST .../performance/<take_id>/approve` |
| REVIEW | `ReviewStage.tsx` per-take Approve | `POST .../final/<take_id>/approve` |
| Assembly | `ReviewStage.tsx` `onProceedToAssembly()` | `POST /api/projects/<pid>/assemble` |

### 14.6 Settings sections

`SettingsPanel.tsx:36-48` mounts **10 functional sections**:
ProductionSection, MaxQualityTierSection, CostEstimatorSection, BudgetSection,
AudioSection, AudioSyncSection, PostProcessingSection, QualitySection,
ApiEnginesSection, AdvancedSection.

11 `.tsx` files total in `web/src/components/settings/` — the 11th is
`SettingsSection.tsx` (shared header/container helper, not mounted directly).

### 14.7 Dev/build

| Command | What |
|---|---|
| `npm run dev` | Vite dev server on port 3000, proxies `/api → http://localhost:8080` ([web/vite.config.ts:6-9](web/vite.config.ts:6)) |
| `npm run build` | `tsc && vite build` → `web/dist/` |

`web_server.py` serves `web/dist/` as its static folder.

---

## 15. Invariants & smoke test

These invariants are verified by the §3 smoke test below. If any fails, the
codebase is broken OR this file is stale.

1. All `.py` files compile cleanly on Python 3.13.
2. `import cinema_pipeline` succeeds without `TypeError`.
3. `LLMEnsemble()` instantiates.
4. `import identity.validator` does NOT pull `phase_c_vision` (lazy import via
   `identity/__init__.py:make_validator`).
5. `phase_c_vision._get_shared_validator()` returns the same instance across
   calls (singleton).
6. All 4 access paths return the same IdentityValidator instance.
7. `PipelineContext(global_settings={"tts_provider": "CARTESIA_SONIC_2"})`
   + `get_project_setting(ctx, "tts_provider")` returns `"CARTESIA_SONIC_2"`
   (settings plumbing works).
8. `phase_c_assembly.generate_ai_broll` is importable.
9. `cinema/pipeline.py:CinemaPipeline` (the generic driver class) has zero
   callers in production code.

### Smoke test

Single source of truth: [scripts/ci_smoke.py](scripts/ci_smoke.py). Run:

```bash
.venv/bin/python scripts/ci_smoke.py
```

The script verifies the runtime-executable subset of the invariants above
(§15.2, §15.5, §15.6, §15.7, §15.8). Invariants §15.1 (all `.py` compile),
§15.3 (`LLMEnsemble()` instantiates), §15.4 (lazy import isolation), and
§15.9 (zero callers of `cinema/pipeline.py:CinemaPipeline`) are static or
test-suite checks; see the script's module docstring for the split
rationale. Exit 0 = invariants hold; exit 1 = drift.

This script is also the smoke job's command in
[.github/workflows/ci.yml](.github/workflows/ci.yml). If you change the
script, the local check + CI move together.

---

## 16. Known bugs & latent issues

> Test suite state (verified 2026-05-29 cycle-17):
> **1229 pass / 3 skip / 0 fail** in `tests/unit/`. The 3 skips below are
> the only known stragglers. Run `.venv/bin/python -m pytest tests/unit/ -q`
> to verify.

| Severity | Issue | Location |
|---|---|---|
| Low | 3 documented `@unittest.skip` tests in `test_project_persistence.py`. Mock setup hasn't caught up with `project_manager`/`character_manager`/`location_manager` refactors. Mock-only updates, not behavior changes. | `tests/unit/test_project_persistence.py:139,203,232` |
| Cosmetic | BGM duration hard-coded to 47s with no comment. | `cinema_pipeline.py:523` |
| ~~Cosmetic~~ Resolved 2026-05-26 (`9c749b7`) | ~~`datetime.utcnow()` deprecation warnings — migrated to `datetime.now(timezone.utc)` with `.replace("+00:00", "Z")` to preserve existing project.json timestamp suffix shape.~~ | ~~`domain/project_manager.py:133,924`~~ |

---

## 17. Dead code & cleanup candidates

- **`main.py`** — already deleted. Root-shim docstrings still mention it.
- **Root-level module status** (verified 2026-05-29 via `grep -rn 'import <mod>' --include='*.py'`, excluding tests/worktrees):
  - **Load-bearing — do NOT delete without grep:** `research_engine.py` + `web_research.py` (imported by `scene_decomposer.py` / `dialogue_writer.py` / `style_director.py`); `cleanup.py` (`web_server.py`, `cinema_pipeline.py`); `web_services.py` (`web_server.py:59`); `coherence_analyzer.py` (`cinema/shots/controller.py`).
  - *(`reporter.py` was here as a true-orphan candidate; pruned 2026-06-03.)*

---

## 18. Keeping this file fresh

**Session-start protocol** (≤2 min):

1. Run the smoke block (§15). If it fails, the doc is stale OR the working
   tree is broken — fix one or the other before proceeding.
2. Spot-check the §2 component topology:
   - `ls cinema/ cinema/phases/ cinema/review/ cinema/shots/`
   - `wc -l cinema_pipeline.py web_server.py phase_c_ffmpeg.py`
3. `git log --oneline -20` — if any commit touched a module documented here
   since this file was last edited, re-read that section against the new code.
4. **If you find a stale claim:** edit this file first, in the same commit
   (or a `docs:` prep commit right before) the user's task lands. The user
   has stated this as a standing requirement.

**When you change a subsystem:**
- Update the relevant section here in the same PR.
- If you find a divergence the section doesn't mention, fix it inline.
- The doc must say what's true now, not what was true at the last refactor.

**When in doubt:** trust the code; update the prose when it diverges.

---

## 19. Glossary

Domain terms used throughout this codebase. Most are defined in their
section above; this is a flat lookup table for quick reference.

| Term | Meaning |
|---|---|
| **HC1 IDENTITY_FIREWALL** | Hard constraint #1 in CineDecompose: LLM must never describe face/hair/skin/eye color. Identity comes from PuLID reference injection downstream. Violation = pipeline failure. |
| **HC2 SCHEMA_LOCK** | Every shot prompt must contain exactly `[SHOT][SCENE][ACTION][OUTFIT][QUALITY]` in order. |
| **HC3 LOCATION_LOCK / HC4 LIGHTING_LOCK / HC5 FACE_DIRECTION** | Same-scene shots use identical location + lighting; character must face the camera. |
| **PuLID** | "Pure and Lightning ID Customization" — face-locking adapter for diffusion. Per-shot weight (`pulid_weight`) is adaptive via rolling-stats feedback (§11.5). |
| **ArcFace** (loss) vs **GhostFaceNet** (model) | Identity validation uses DeepFace's GhostFaceNet model, trained with ArcFace loss. The codebase says "ArcFace" in many comments; the actual model is GhostFaceNet. |
| **N=8 best-of** | Max-tier image generation strategy: produce up to 8 candidates with different seeds, score each via composite (0.6·ArcFace + 0.4·Aesthetic v2), halt early when threshold met. §8.3 |
| **Composite score** | `0.6 × arc + 0.4 × aesthetic`. The selection metric for N=8 best-of. |
| **FreeU** | Training-free U-Net feature rescaling (skip-connection + backbone). Improves detail. §8.3 |
| **SLG** | Skip-Layer Guidance for Diffusion Transformers — amplifies detail by skipping specific layers in the guided path. §8.3 |
| **DetailDaemon** | Sampler wrapper injecting controlled noise during denoising to surface micro-detail. §8.3 |
| **SUPIR** | "Scaling Up Image Restoration" V2 — final post-pass quality lift, used before 4K downsample. §8.3 |
| **Redux** | FLUX style-reference adapter — accepts image refs to lock style (separate from PuLID identity). §8.3 |
| **Mode A vs Mode B** (performance) | Mode A: operator pre-uploads a driving video. Mode B: orchestrator synthesizes a driving video from TTS audio via Hedra → SadTalker cascade. §10.2-10.3 |
| **Overlay vs Generation** (lipsync) | Overlay: take existing video + audio, lip-sync over the mouth (preserves cinematography). Generation: take still + audio, create talking-head from scratch. §10.6 |
| **Predicate-poll** | Gate model where the worker thread polls disk-state every 500ms via a predicate function. State survives crashes + SSE disconnects. ADR-002, §6. |
| **PipelineContext** (ctx) | Per-run dataclass that ALSO implements the dict API. Carries `global_settings`, lifecycle, audio paths. Use `get_project_setting(ctx, key, default)` for project knobs. ADR-003. |
| **PipelineCore** | Long-lived per-project deps (project dict, continuity engine, chief director, cost tracker, LLM ensemble). Cached in `web_server._running_cores` so it survives across runs. §4.3 |
| **RunState** | Per-run mutable bag (shot_results, scene_clips, current_*, etc.). Fresh per pipeline instance. §4.5 |
| **CheckpointStore** | Atomic JSON resume file at `<project>/temp/pipeline_state.json`. Written via `tempfile + os.replace`. §4.6 |
| **ChiefDirector** | LLM validator (Anthropic by default, OpenAI fallback). Pre-gen: returns APPROVED / REJECTED / MODIFIED for shot prompts. Post-gen: returns RETRY / ACCEPT_LENIENT / FAIL with mutation focus. §13.4 |
| **StyleDirector** | GPT-4o only. Generates `style_rules` (cinematography, lighting, color, sound, photorealism, composition) once per project; injected into every decompose prompt. §13.5 |
| **CineDecompose** | The system persona for scene decomposition: a strict cinematic shot decomposition engine with 8 hard constraints + 9 tripwires. The prompt is now in `_build_cinedecompose_system_prompt` (§7.4). |
| **Cascade** | Ordered fallback chain. Video has a default 9-engine cascade; lipsync has 4-engine overlay + 4-engine generation; performance has Hedra/SadTalker; image gen has ComfyUI → FAL FLUX → schnell → Pollinations. |
| **SyncNet** | Lipsync quality scorer (mouth-audio sync). Used as the gate threshold in `lip_sync.py` cascade decisions. Falls back to duration-match heuristic or neutral 1.0 if scorer not installed. |
| **Take** | A single attempt at a stage's output. Each shot has `keyframe_takes[]`, `performance_takes[]`, `motion_takes[]`, `postprocess_variants[]` — operators approve one of each. |
| **Postprocess variant** | A take derived from another take via `apply_correction` (face_swap, lip_sync, rife, upscale, color_grade, speed). Has `source_take_id` linking back to its parent. |
| **Multi-angle refs** | 5 synthetic character ref images generated via FLUX Kontext MAX MULTI at character-creation time (`angle_45`, `angle_profile`, `angle_back`, `expression_smile`, `lighting_outdoor`). Used by Kling 3.0 elements array + PuLID for multi-view identity locking. |
| **Identity anchor** | The canonical reference image for a character (one of `reference_images[]`, picked via DeepFace face-detection at creation time). Used as the threshold-anchor in all identity validations. |
| **Identity strictness** | Per-project setting (default 0.60) that becomes the threshold for `validate_image` rolling-history `passed` flag. ADR-011. |
| **Adaptive PuLID weight** | `workflow_selector.get_adaptive_pulid_weight(character_id)` returns a per-character PuLID weight adjustment based on `get_rolling_stats(character_id).success_rate`. ±0.10 in either direction. |
| **Continuity engine** | `domain/continuity_engine.py` — composes CharacterContinuityTracker + LocationPersistence + PhysicsPromptEngineer + TemporalConsistencyManager. Output enriches each shot prompt with identity-anchored references, location continuity, physics constraints, and img2img chaining config. §7.5 |

---

*Last verified: 2026-05-24 by parallel investigation across 11 subsystems
+ subsequent point-fixes through 2026-05-24. Glossary section added by
new-director Task 1. All file:line anchors re-audited against current
source & 72 stale line numbers corrected on 2026-05-29 (full sweep,
§15 smoke OK); prose claims not re-verified in that pass. §10.6 generation
cascade updated 2026-06-03 to document the `hedra_native` direct Character-3
ATTEMPT-0 (`cb31207`). §10.6/§10.7 updated 2026-06-03 to document the
Veo+overlay dialogue default + `dialogue_voice_mode` (Chunk 4, Task 9;
anchors scoped to §10.6/§10.7 only — not a whole-file re-verify). §8.3 updated
2026-06-04 (Lane D) to document T1 (LoRA quality gate + validated
`char_lora_strength` override), T3 (hires_fix Pass-2 @ denoise 0.40), and T4
(`conjunctive` identity-floor halt mode); scoped to §8.3 only — not a whole-file
re-verify.*
