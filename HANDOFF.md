# Session Handoff — Content Cinema Pipeline

**Last session:** 2026-05-23 — large refactor, audit, Python 3.13 migration, settings plumbing rewrite, dead-code purge, orphan UI knob sweep. **39+ tasks completed. No commits created.** All changes are in working tree.

## TL;DR for the next session

- Repo: `/Users/hyungkoookkim/Content`
- **Single entry point**: `web_server.py` → `cinema_pipeline.py:CinemaPipeline` (interactive cinema pipeline with review gates + SSE)
- **CLI is gone.** `main.py`, `phase_a_generator.py`, `llm/blueprint_director.py`, `cinema/phases/{blueprint,generation,audio,assembly,vision}.py`, `prep/lut_generator.py`, `recover_assembly.py`, `test_assembly.py`, `vbench_evaluator.py`, `comfyui_workflow_gen.py` — all deleted. Don't recreate them.
- **Python 3.13 required.** `pyproject.toml` declares `requires-python = ">=3.11"`. `requirements.txt` is direct-deps only (~40 lines); old frozen pins preserved in `requirements-lock-py39.txt` for reference.
- **Settings architecture rebuilt.** Use `from cinema.context import get_project_setting; get_project_setting(ctx, key, default)` for all per-project UI knobs. **Never use `getattr(settings, X)` for project-knob keys** — `config.settings.Settings` carries env-derived API keys only. The plumbing for `ctx["global_settings"]` is in `cinema_pipeline.py:711` (constructor) and consumed by 9+ wired sites.
- **IdentityValidator is a process singleton** via `phase_c_vision._get_shared_validator()`. Don't construct fresh instances; the singleton lets `validator.history` accumulate so `get_rolling_stats` → `workflow_selector.get_adaptive_pulid_weight` actually works.

## First thing to run

```bash
cd ~/Content
.venv/bin/python -c "import cinema_pipeline; print('OK')"
git status --short  # confirm working tree matches handoff expectations
```

If `import cinema_pipeline` doesn't print `OK`, the venv is broken — recreate:

```bash
rm -rf .venv
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

## Architecture as of this handoff

```
web_server.py                          ← Flask + SSE entry
  └→ cinema_pipeline.py:CinemaPipeline ← orchestrator (~990 lines, was 1252)
      ├→ cinema/phases/keyframe_render.py (KeyframeRenderPhase)
      ├→ cinema/phases/performance.py     (PerformanceCapturePhase)
      ├→ cinema/phases/motion_render.py   (MotionRenderPhase)
      ├→ cinema/shots/controller.py       (per-shot work — most user knobs land here)
      ├→ cinema/review/controller.py
      └→ cinema/checkpoint.py
```

Shared infrastructure under `cinema/`:
- `cinema/context.py` — `PipelineContext` dataclass + `get_project_setting(ctx, key, default)` helper
- `cinema/pipeline.py` — generic Phase iterator (no current callers; forward-compatible primitive)
- `cinema/phases/base.py` — Phase protocol + PhaseResult
- `cinema/core.py` — `PipelineCore` (long-lived services per project; no longer includes vbench)
- `cinema/lifecycle.py` — cancel / pause / progress

Domain: `audio/`, `llm/`, `identity/`, `performance/`, `domain/`, `prep/`, `config/`.
Video router: `phase_c_ffmpeg.py:generate_ai_video` (cascade across Kling/Sora/Veo/LTX/Runway natives).
Per-shot image gen: `phase_c_assembly.py:generate_ai_broll` (+ optional `quality_max.generate_ai_broll_max`).

## What this session shipped (chronological)

### 1. YouTube residue cleanup (rounds 1-2)
Deleted `phase_0_topic.py`, `phase_d_upload.py`, `phase_e_learning.py`, `sanitize_metadata.py`, `run_example.py`, `used_topics.txt`, `CALIBRATION_MATRIX.txt`, `RAILWAY_GUIDE.md`, `firebase-debug.log`, `docs/CODEBASE_DUMP.md`, `data/experiments.db`. Scrubbed all references.

### 2. Dark-code fixes (round 3)
- Deleted ReActor dead branches (`if False` block in `phase_c_assembly.py` + `reactor_*` params in `workflow_selector.py` + ReActor branch in `quality_max._inject_post_passes`)
- Deleted orphan `get_shot_workflow_summary`
- **Wired `generate_tts_routed` through `generate_voiceover`** so the UI's `tts_provider` knob actually works
- Promoted Pedalboard to a hard dependency

### 3. Quality features added then lost with CLI (round 4)
Last-frame chaining, programmatic LUT (`prep/lut_generator.py`) — both lived in `main.py` and were deleted in round 6. **`phase_c_ffmpeg.two_pass_loudnorm` survives** and is callable from anywhere.

### 4. 4-agent comprehensive audit (round 5)
- Agent A: orchestration
- Agent B: audio + LLM
- Agent C: video + identity + quality
- Agent D: UI ↔ backend wiring

Surfaced 40+ orphan UI knobs (the `tts_provider` pattern at scale), broken TTS fix (wrong source object), dead VBench/quality-tracker pipeline, dead `comfyui_workflow_gen.py`, dead lip_sync methods, IdentityValidator fresh-per-call bug.

### 5. Settings plumbing rebuilt (round 5b)
- Added `global_settings: dict` field to `PipelineContext`
- Added `get_project_setting(ctx, key, default)` helper in `cinema/context.py`
- `cinema_pipeline.py` now threads `project["global_settings"]` into ctx at construction
- Migrated 8 broken `getattr(settings, X)` sites across `audio/voiceover.py`, `audio/foley.py`, `audio/music.py`, `audio/dialogue.py`, `lip_sync.py` to use the helper OR accept a `settings: dict` kwarg from the caller

### 6. CLI full removal + Python modernization (round 6)
- Deleted 11 CLI/YouTube files
- Trimmed `phase_c_assembly.py` from 711 → 558 lines (removed `assemble_final_video`, `scale_to_widescreen`, `__main__`; kept `generate_ai_broll` + `RunPodComfyUI`)
- Renamed `requirements-frozen-py39.txt` → `requirements.txt`, rewrote as direct-deps only (40 lines vs 153 frozen pins)
- Added `pyproject.toml` with `requires-python = ">=3.11"`
- Stripped orphan deps: `basicsr`, `realesrgan`, `moviepy`, `gfpgan`, `facefusion`, `facexlib`, `numba`, `llvmlite`. Added `tf-keras>=2.16` (TF 2.16+/Keras 3 vs deepface compat shim).

### 7. Final cleanup + bug fixes (round 7)
- Deleted `vbench_evaluator.py` (878 LOC) + `comfyui_workflow_gen.py` (584 LOC)
- Updated `cinema/core.py`, `cinema_pipeline.py`, `web_server.py` to remove vbench refs
- Trimmed `cinema_pipeline.py` head imports (26 dead, mostly leftover from controller-extraction refactor) + dead methods (`_frame_interpolate`, `_upscale_video`, `cleanup_temp`)
- **Fixed IdentityValidator singleton** in `phase_c_vision.py` (`_get_shared_validator()` lazy factory) — adaptive PuLID feedback loop now actually accumulates state

### 8. Orphan UI knob sweep (round 8)
- Dispatched classification agent on ~40 orphan UI knobs
- **Deleted 10 UI keys** from `web/src/types/project.ts` + 4 settings .tsx files + `EditorialShell.tsx` + `lib/guidance.ts` presets:
  - `master_seed`, `reactor_enabled`, `codeformer_weight`, `rife_enabled`, `video_upscale_enabled` (backends deleted this session)
  - `vbench_overall_threshold`, `temporal_flicker_tolerance`, `regression_sensitivity` (vbench pipeline gone)
  - `quality_judge_llm`, `competitive_generation` (no consumers anywhere)
- **Wired 9 knobs** to their consumption sites:

| Knob | Backend wire site |
|---|---|
| `identity_strictness` | `cinema/shots/controller.py:413` — overrides per-shot identity threshold |
| `identity_retry_max` | `cinema/shots/controller.py:756` — replaces hardcoded `max_attempts=1` |
| `motion_quality_threshold` | `cinema/shots/controller.py:784` — overrides per-shot-type floor |
| `coherence_threshold` | `cinema/shots/controller.py:914` — triggers regenerate when coherence < floor |
| `face_swap_enabled` | `cinema/shots/controller.py:971` — hard gate on operator action |
| `lip_sync_mode` | `cinema/shots/controller.py:989` — passes user mode to lipsync engine |
| `color_grade_preset` | `cinema/shots/controller.py:1006` — operator-action color grade default |
| `music_mastering` | `cinema_pipeline.py:493` — passes preset to `master_music` |
| **React** Continuity Engine sliders | `web/src/components/settings/AdvancedSection.tsx:99-117` — controlled inputs + `onChange` (was uncontrolled — slider moved but never persisted) |

### 9. UI ↔ backend audit, second pass (post-pivot)

Cross-referenced every `update('<key>', ...)` in `web/src/components/settings/*.tsx` against every `get_project_setting`/`global_settings[]` read in Python.

**Deleted UI for 15 still-orphan keys** (commit `25b5337`, partially repaired in `4859027`):
* AudioSection: `narration_mode`, `narrator_voice`, `voice_effect`
* AudioSyncSection: `room_tone_matching`, `prosody_continuity`, `music_provider`, `foley_provider`, `purpose_overrides` (plus the `PurposeMatrix` and `ProviderSelect` helpers)
* AdvancedSection: `pag_scale`, `controlnet_depth_strength` (both use hardcoded shot-type defaults from `workflow_selector.py`, never UI), `ip_adapter_style_weight`, `comfyui_upscale`, `quality_cost_weight`
* ProductionSection: `default_video_api`
* BudgetSection: `cost_optimization` (section was deleted then re-created with just `budget_limit_usd`)
* Also stripped from `domain/project_manager.py` defaults (commit `439dcab`) and `web/src/lib/guidance.ts` PRODUCTION_PRESETS

**Restored 3 UI keys** wired by parallel commits during the audit window (commit `4859027`):
* `budget_limit_usd` — wired in `cinema/core.py:102` (CostTracker gate) by commit `5445049`
* `creative_llm` — wired in `llm/chief_director.py:85` (per-call model override) by commit `64d968d`
* `adaptive_pulid` — wired in `domain/continuity_engine.py:511` (gate for `get_adaptive_pulid_weight`) by commit `75c470d`

**Other settings work this session** (chronological):
* `176033d` — validated the 7 max-tier halt knobs in `_MAX_TIER_KNOB_SCHEMA` (extended commit `37aea4f`'s ComfyControls validation)
* `8a8b0a0` — dropped stale "wire up via get_project_setting" comments in `audio/music.py` and `audio/foley.py` that referenced the now-deleted UI keys

**Process lesson:** the orphan grep was run ~14 minutes before the deletion commit, and three parallel commits landed in that window wiring up keys I was about to delete. Re-grep candidates against HEAD as the LAST step before any commit that deletes ≥5 keys/files/symbols. (Saved as memory: `feedback_re-verify-before-destructive-commits.md`.)

## OPEN WORK — prioritized

### 🔴 1. Wire the remaining UI knobs (mostly resolved)

Status: most rows CLOSED by post-pivot work — `ec8b1d9` (max-tier 21-knob bundle), `19be241` (video-cascade ctx + `api_engines` filter + `cascade_retry_limit`), `5445049` (`budget_limit_usd` via CostTracker), `64d968d` (`creative_llm`), `75c470d` (`adaptive_pulid`). The deletion sweep in Round 9 closed the rest by removing UI surface.

Still open:

| Function | Knobs unblocked | LOC est |
|---|---|---|
| `workflow_selector.get_workflow_params(shot_type, settings=None)` — add settings, overlay | `flux_guidance`, `comfyui_sampler`, `comfyui_steps` | 20 |

(`comfyui_upscale`, `cost_optimization`, `quality_cost_weight` were UI orphans — removed in `25b5337`, so no longer on the wire-up list.)

#### ASK USER before wiring — RESOLVED

Round 9 resolved every "ASK USER" item by deleting the UI control:
* `narration_mode`, `narrator_voice`, `voice_effect` — deleted (`generate_voiceover` consumer was never wired into the cinema pipeline)
* `purpose_overrides` — deleted (PurposeMatrix UI removed; per-purpose routing falls back to PURPOSE_API_RANKING)
* `room_tone_matching`, `prosody_continuity` — deleted (require real feature work to implement)
* `lipsync_engine_priority` — KEPT (still in UI; `lip_sync` consumers exist and the engine-priority list is read)

### 🟠 2. Re-add lost quality features to cinema pipeline (if desired)

These were added to `main.py` then deleted with the CLI:
- **Last-frame chaining** — thread `lip_sync.extract_last_frame` output as next shot's start image. Implementation site: `cinema/shots/controller.py:390` (`generate_ai_broll` call) OR `phase_c_ffmpeg.generate_ai_video` wrapper. ~30 LOC.
- **Programmatic LUT from Blueprint palette** — `prep/lut_generator.py` was deleted but the recipe is documented in this session's history. The cinema pipeline's `_assemble_final` method (in `cinema_pipeline.py`) is where it'd be wired. ~120 LOC for the generator + ~10 LOC wire-up. NB: there's no Blueprint Director anymore in the cinema pipeline path (llm/blueprint_director was deleted) — needs a replacement palette source (style_director? new field on project?).
- **Two-pass loudnorm** — function still exists at `phase_c_ffmpeg.py:two_pass_loudnorm`. Just needs to be called in `cinema_pipeline.py:_assemble_final` after the single-pass mix. ~5 LOC.

### 🟠 3. Other audit findings still open

- **`cinema/shots/controller.py:881` calls deprecated `validate_identity_image`** — the wrappers in `phase_c_vision.py:25-89` are all marked DEPRECATED in their docstrings but still used. Consider direct `_get_shared_validator().validate_video()` calls for rich diagnostics (character_results, primary_failure_reason, suggested_pulid_adjustment) instead of the bool-only wrappers.
- **VEO fal.ai branch** silently drops chained start-frame (`phase_c_ffmpeg.py:484-494`) when `multi_angle_refs` is supplied. Moot until last-frame chaining is re-added.
- **SEEDANCE branch unreachable** (`phase_c_ffmpeg.py:714`) — 200+ LOC of multi-character SEEDANCE integration. Never appears in any cascade. Either wire into `WORKFLOW_TEMPLATES` or delete.
- **Native API methods dark**: `veo.generate_video_4k`, `veo.generate_video_with_frames`, `veo.generate_with_audio`, `ltx.generate_transition`, `ltx.generate_4k`, `generate_kling_storyboard`, `lip_sync.generate_transition_clip`, `recommend_lip_sync_mode`, `lipsync_act_one`. Decide per case.
- **VBench-style quality routing** — `quality_tracker.log_shot_quality` has only test callers. `workflow_selector.get_optimal_api` + `get_dynamic_workflow` have zero production callers. Now that `vbench_evaluator.py` is gone, this whole adaptive-routing surface needs a decision: revive with a simpler scorer or delete the unreachable functions.
- ~~**Env vars sneaking past `config/settings.py`**~~ — CLOSED by `9ecd572` (absorbed all 3 stray env-var reads into `config.Settings`).
- **Dead web endpoints**: `web_server.py:340-358 /api/optimize-shot-prompt` (no frontend caller); `web_server.py:310-322 GET /api/language-defaults/<language>` (no frontend caller).

### 🟡 4. Commit hygiene

**Nothing has been committed this session.** Recommend staging in logical chunks. Suggested order:

```bash
# Chunk 1: YouTube cleanup
git add -A *.txt CALIBRATION_MATRIX.txt RAILWAY_GUIDE.md firebase-debug.log docs/CODEBASE_DUMP.md \
  phase_0_topic.py phase_d_upload.py phase_e_learning.py sanitize_metadata.py \
  used_topics.txt run_example.py cinema/phases/{topic,upload,learning}.py
git commit -m "chore: remove YouTube generator residue"

# Chunk 2: Dark-code fixes
git add quality_max.py workflow_selector.py phase_c_assembly.py \
  audio/voiceover.py audio/effects.py audio/music.py
git commit -m "fix(dark-code): remove ReActor dead branches, get_shot_workflow_summary; wire generate_tts_routed; pedalboard hard dep"

# Chunk 3: Settings plumbing rewrite
git add cinema/context.py cinema_pipeline.py audio/voiceover.py audio/foley.py \
  audio/music.py audio/dialogue.py lip_sync.py
git commit -m "fix(settings): add get_project_setting helper; migrate 8 broken getattr sites"

# Chunk 4: CLI removal + Python modernization
git add -A  # picks up the 11 deleted files + cinema/__init__.py + cinema/pipeline.py \
            # + llm/__init__.py + domain/scene_decomposer.py + requirements.txt \
            # + requirements-lock-py39.txt + pyproject.toml + phase_c_assembly.py trim
git commit -m "refactor: remove CLI/YouTube generator; modernize to Python 3.11+"

# Chunk 5: Final cleanup
git add cinema/core.py cinema_pipeline.py phase_c_vision.py web_server.py
git commit -m "fix: delete vbench_evaluator + comfyui_workflow_gen (dead); singleton IdentityValidator; tidy cinema_pipeline imports"

# Chunk 6: UI knob wire-up
git add web/src/types/project.ts web/src/components/settings/ \
  web/src/components/EditorialShell.tsx web/src/lib/guidance.ts \
  cinema/shots/controller.py cinema_pipeline.py
git commit -m "feat(settings): wire 9 UI knobs to backend; delete 10 orphan/dead UI keys; fix Continuity Engine slider persistence bug"

# Chunk 7: Docs
git add AGENTS.md CLAUDE.md HANDOFF.md docs/REFACTOR_HANDOFF.md \
  docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md config/prompts/pipeline_context.md
git commit -m "docs: update for post-pivot single-entry-point architecture"
```

## Don't break these

- `cinema/context.py:get_project_setting(ctx, key, default)` — canonical read path for all per-project UI knobs. Replicating the `getattr(settings, X)` pattern brings the silent-failure bug right back.
- `phase_c_vision.py:_get_shared_validator()` — process-singleton for `IdentityValidator`. **Don't** construct fresh `IdentityValidator(vision_fallback=...)` in new wrappers; use the factory so `history` accumulates.
- `phase_c_assembly.py:generate_ai_broll` + `RunPodComfyUI` — still consumed by `cinema/shots/controller.py:88,390` and `quality_max.py`. **Don't delete.**
- `phase_c_ffmpeg.py` is the video router for the entire production pipeline. The `two_pass_loudnorm` function is small + useful — keep it even though no current caller.
- `cinema/pipeline.py:CinemaPipeline` (the typed driver) has no callers but is preserved as a forward-compatible primitive. Don't delete.
- `requirements.txt` is now direct-deps only. **Don't `pip freeze > requirements.txt`** — that would reintroduce the frozen-lock fragility. Keep `requirements-lock-py39.txt` as historical reference only.

## Memory files for context

`/Users/hyungkoookkim/.claude/projects/-Users-hyungkoookkim-Content/memory/`:
- `MEMORY.md` — index
- `project_two_entry_points.md` — pivot from YouTube to cinema; CLI deletion record
- `feedback_re-verify-before-destructive-commits.md` — re-grep candidates against HEAD as the last step before any commit that deletes ≥5 keys/files/symbols; long audit windows + parallel work = stale orphan lists

## Useful greps for the next session

```bash
# Find anything still using the broken settings.X pattern for project knobs
grep -rn --include='*.py' "getattr(settings\|getattr(_s" . | grep -v -E ".venv|node_modules|web|\.git"

# Find anything referencing deleted modules
grep -rn --include='*.py' -E "from (main|phase_a_generator|llm.blueprint_director|prep.lut_generator|vbench_evaluator|comfyui_workflow_gen|cinema.phases.(blueprint|generation|audio|assembly|vision))" .

# Find UI knobs not consumed by backend
# For each setting name S in web/src/types/project.ts:
grep -rn --include='*.py' "get_project_setting.*\"S\"\|global_settings\[\"S\"\]\|settings\.get(\"S\"" .
# If zero hits → orphan.

# Confirm cinema pipeline still imports
.venv/bin/python -c "import cinema_pipeline; print('OK')"
```

## Smoke test

```bash
.venv/bin/python -c "
import cinema_pipeline
from cinema.context import PipelineContext, get_project_setting
from phase_c_vision import _get_shared_validator
v1 = _get_shared_validator(); v2 = _get_shared_validator()
assert v1 is v2, 'IdentityValidator singleton broken'
ctx = PipelineContext(global_settings={'tts_provider': 'CARTESIA_SONIC_2', 'identity_strictness': 0.8})
assert get_project_setting(ctx, 'tts_provider') == 'CARTESIA_SONIC_2'
assert get_project_setting(ctx, 'identity_strictness') == 0.8
print('OK')
"
.venv/bin/python -m pytest tests/unit -x -q
.venv/bin/python -m pytest tests/integration -x -q --maxfail=3  # several need API keys
```
