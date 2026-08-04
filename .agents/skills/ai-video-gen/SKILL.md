---
name: "ai-video-gen"
description: "Use when working on AI video generation, cinema pipeline, shot routing, video API selection (Gemini Omni, Kling, Sora, Veo, LTX, Runway), character consistency, identity validation, continuity systems, prompt engineering for video, lip sync, face swap, post-processing, or any work involving the cinematic video production pipeline."
---

# AI Video Generation Expert

This pipeline transforms scripts into photorealistic cinematic video through a multi-phase architecture:

```
Scene Decomposition → Continuity Enhancement → Image Gen (FLUX+PuLID)
    → Policy-gated Video Provider Cascade → Identity Validation → Face Swap (if needed)
    → Lip Sync → Frame Interpolation (RIFE) → Upscale (SeedVR2)
    → FFmpeg Assembly (color grade + audio + subtitles)
```

## API Selection Decision Tree

Choose the primary API based on shot type. Each has an ordered fallback cascade:

| Shot Type | Primary API | Why | Fallback Chain |
|-----------|------------|-----|----------------|
| **Portrait** | GEMINI_OMNI | Google-first primary (WS2) — native audio, repaired + re-admitted 2026-07-30 | VEO_NATIVE → KLING_3_0 (fal Kling v3 Pro, `elements` identity binding) → RUNWAY_GEN4 → SEEDANCE |
| **Medium** | GEMINI_OMNI | Google-first primary (WS2) | VEO_NATIVE → KLING_3_0 → RUNWAY_GEN4 → SEEDANCE → LTX |
| **Wide** | GEMINI_OMNI | Google-first primary (WS2) | VEO_NATIVE → LTX (4K, depth-aware, cheapest) → KLING_3_0 → RUNWAY_GEN4 |
| **Action** | GEMINI_OMNI | Google-first primary (WS2) | VEO_NATIVE → SEEDANCE (#1 AA i2v arena, 2026-07; multi-reference ≤9 images binds multi-character action) → KLING_3_0 → RUNWAY_GEN4 → LTX |
| **Landscape** | GEMINI_OMNI | Google-first primary (WS2) | VEO_NATIVE → LTX (no face needed, 4K, lowest cost) → KLING_3_0 |

GEMINI_OMNI (Gemini Omni Flash, Preview tier) became the primary for every shot
type in the Google-first migration (WS2), then was repaired and re-admitted
2026-07-30 (Slice 3: inline-base64 decoding, URI/Files-API polling+download,
and failed/empty-terminal handling fixed in `gemini_omni_native.py`) — it
needs `GOOGLE_API_KEY` or `GEMINI_API_KEY`; without either it is
runtime-unavailable and the cascade starts at VEO_NATIVE. VEO_NATIVE is the
shared first fallback everywhere; only its Vertex/ADC backend supports native
audio, while its Developer-API backend requires F1b (see dialogue routing
below). SEEDANCE remains the action purpose's strongest non-Google fallback
(still #1 AA i2v arena, 2026-07; multi-reference up to 9 images binds
multi-character action). The Seedance dispatch is fal-based:
`bytedance/seedance-2.0/image-to-video`, or `.../reference-to-video` (keyframe
first, ≤9 images) when multi-angle refs exist (`phase_c_ffmpeg.py`,
`workflow_selector.py`). SORA_NATIVE is deprecated compatibility only: an
explicit pre-sunset pin may still dispatch, but automatic templates, optimizer
suggestions, and fallback cascades must never select it. The FAL-proxied
**SORA_2 is already fully RETIRED/UNSUPPORTED** (not selectable, not
dispatchable, not spendable) — do not route new work to it, in code or prompts.

LTX (`ltx_native.py`, native `ltx-2-3-pro` profile) accepts only 6/8/10-second
clips (6s default) — snap or reject any other requested duration before the
network call (`LTXVideoAPI.nearest_supported_duration` / `DURATION_SECONDS`);
its FAL fallback profile is audio-off (silent) by contract.

**Performance capture** (talking-head driving-video transfer — a separate axis
from base video generation above; `domain/performance.py`'s ENGINE_ACT_ONE /
ENGINE_LIVE_PORTRAIT / ENGINE_VIGGLE, dispatched by `performance/_router.py`):
Runway's engine migrated from Act-One (retired — no longer constructible on
the Runway API) to **Act-Two** (`performance/act_two.py`). The routing engine
name stays `ACT_ONE` / catalog key `RUNWAY_ACT_ONE` for backward-compat with
existing cost/routing data, but it dispatches the live `act_two` model over
the same `RUNWAYML_API_SECRET` credential. **Viggle is uncontained as of
2026-08-01 (ADR-082)** — its adapter (`performance/viggle.py`) was rewritten to
the official `apis.viggle.ai/v1/renders` contract and `domain/performance.py`
rule 3 now routes action-without-dialogue shots to `ENGINE_VIGGLE`. Catalog
state is `LIMITED`, not `SUPPORTED`: contract-correct and unit-tested, never
exercised against the live API, so treat the first real render as the
verification run.

**Cascade logic**: Try primary → on failure, next in chain → if all exhausted, wait 30s for quota refresh → retry 1 additional full cycle by default (`MAX_CASCADE_RETRIES = 1` in `phase_c_ffmpeg.py`; the `cascade_retry_limit` UI knob raises it per project).

## Critical Numbers

### PuLID Weight by Shot Type (ComfyUI image gen)
| Shot | Weight | start_at | end_at | Denoise | Rationale |
|------|--------|----------|--------|---------|-----------|
| Portrait | 1.0 | 0.0 | 1.0 | 0.25 | Maximum face lock |
| Medium | 0.9 | 0.0 | 1.0 | 0.35 | Strong face, scene balance |
| Wide | 0.65 | 0.0 | 0.9 | 0.45 | Environment priority |
| Action | 0.8 | 0.0 | 1.0 | 0.40 | Identity through motion |
| Landscape | 0.0 | 0.0 | 0.0 | 0.55 | No face lock |

**`start_at = 0.0` across the production tier** (FLUX coarse-identity window — bind from step 0). The prior SDXL-era values (portrait 0.20 / medium 0.25 / wide 0.35 / action 0.30) were a structural no-op on FLUX and re-suppressed the node swap at runtime; fixed 2026-06-13 (production `pulid.json` → FLUX-native `ApplyPulidFlux`; `workflow_selector.WORKFLOW_TEMPLATES`; validated OFF 0.6205 → ON 0.8779; DECISIONS.md ADR-025).

### Identity Validation Thresholds
| Shot | Strict | Standard | Lenient |
|------|--------|----------|---------|
| Portrait | 0.75 | 0.70 | 0.60 |
| Medium | 0.70 | 0.65 | 0.55 |
| Wide | 0.60 | 0.55 | 0.45 |
| Action | 0.65 | 0.60 | 0.50 |
| Landscape | 0.0 | 0.0 | 0.0 |

Thresholds degrade linearly from the selected mode (strict or standard) → lenient across retry attempts. Landscape is 0.0 everywhere — no face gate.

### Temporal Denoise (img2img chaining)
| Context | Denoise | Why |
|---------|---------|-----|
| First shot of scene | 0.55 | Maximum creative freedom |
| Same location, second shot (index 1) | 0.40 | Slight creative room before locking down |
| Same location, third shot onward | 0.30 | Tightest consistency |
| Location change within scene | 0.50 | New environment, keep style |

The 0.40/0.30 split is by shot index within the scene — there is no time-skip detection (`domain/continuity_engine.py`, TemporalConsistencyManager).

### Sampler Constants (always)
- **Sampler**: dpmpp_2m (higher-order solver, sharper results)
- **Scheduler**: sgm_uniform (optimized sigma for FLUX flow-matching)
- **Guidance**: 3.0–4.0 (3.5 is the FLUX sweet spot for character scenes)

## Quality Gates

### 1. Chief Director (Metacognitive QA)
LLM layer (Claude → GPT-4o fallback) that validates ALL pipeline outputs. Can REJECT and REWRITE prompts violating structural constraints. Missing clients, malformed replies, or unusable modifications produce REVIEW_REQUIRED, never synthetic approval.

### 2. Scene Coherence Score
```
score = 0.4 * color_consistency + 0.3 * lighting_consistency + 0.3 * composition_similarity
```
- Color: HSV histogram correlation + k-means palette drift detection
- Lighting: Sobel gradient angular consistency (light direction)
- Composition: Brightness distribution, exposure shift

**Thresholds**: color_drift > 0.3 → flag | lighting < 0.5 → flag | brightness_delta > 0.15 → flag

### 3. Identity Validation
Adaptive frame sampling (3–10 frames based on shot type + duration). Per-frame diagnostics: face_detected, angle_estimate, similarity score, failure_reason. Rolling stats feed PuLID weight adjustment with three branches (`identity/validator.py` `get_rolling_stats`): success_rate < 0.5 → +0.10, success_rate < 0.8 → +0.05, success_rate == 1.0 with mean_sim > 0.80 → −0.05; FACE_ANGLE_EXTREME / SMALL_FACE_REGION frames are skipped. Per-result deltas (`_compute_pulid_delta`): clear failure → +0.10, close miss (>0.55) → +0.05, strong match (>0.80) → −0.05.

## Prompt Structure

Every video generation prompt uses 5 structured sections:

```
MOTION: [camera movement] + [actor movement]
SUBJECT: [character preservation rules]
PHYSICS: [gravity, cloth, momentum, shadows]
TEMPORAL: [frame-to-frame consistency]
QUALITY: [photorealism enforcement]
```

See `prompt-engineering.md` for API-specific templates and the negative prompt.

## Photorealism Formula

> Visible skin pores with subsurface scattering, shallow depth of field f/1.4–2.8 with circular bokeh, natural film grain ISO 400, micro-detail in fabric weave and material texture, volumetric atmospheric lighting, no AI artifacts, no smooth plastic skin, no over-saturated colors.

This is appended to every image generation prompt via the Style Director.

## Reference Files

| You need to... | Read this file |
|----------------|----------------|
| Debug an API call or check auth/params | `api-reference.md` |
| Classify a shot type or tune workflow params | `shot-routing.md` |
| Fix identity drift or adjust PuLID | `character-consistency.md` |
| Understand continuity, style rules, or coherence scoring | `continuity-and-style.md` |
| Write or improve generation prompts | `prompt-engineering.md` |
| Work on face swap, lip sync, upscale, or FFmpeg | `post-processing.md` |
| Work with ComfyUI workflows or PuLID nodes | See `comfyui-mastery/SKILL.md` |

## Source Map

| Concept | Source File |
|---------|------------|
| Pipeline orchestrator | `cinema_pipeline.py` |
| Video generation + cascade | `phase_c_ffmpeg.py` |
| Shot-type routing + workflow params | `workflow_selector.py` |
| Typed provider/engine catalog (lifecycle, product support, runtime gates) | `domain/provider_catalog.py`, `domain/video_engine_policy.py` |
| Scene → shots breakdown | `domain/scene_decomposer.py` (root `scene_decomposer.py` is a re-export shim) |
| Continuity (4 subsystems) | `domain/continuity_engine.py` (root file is a shim) |
| Character management | `domain/character_manager.py` (root file is a shim) |
| Identity validation | `identity/validator.py`, `identity/types.py` |
| Coherence analysis | `coherence_analyzer.py` |
| Style direction | `llm/style_director.py` |
| Chief Director QA | `llm/chief_director.py` |
| Shared LLM pipeline context | `pipeline_context.py` → `config/prompts/pipeline_context.md` |
| Lip sync | `lip_sync.py` |
| Face swap + DeepFace | `phase_c_vision.py` |
| Image gen (FLUX+PuLID) | `phase_c_assembly.py` |
| Audio (TTS + BGM + foley) | `audio/` package: `audio/dialogue.py` (TTS), `audio/music.py` (BGM), `audio/foley.py` (legacy `phase_b_audio.py` deleted) |
| Kling API | `kling_native.py` |
| Sora API | `sora_native.py` |
| Veo API | `veo_native.py` |
| Gemini Omni API (Google-first primary) | `gemini_omni_native.py` |
| LTX API | `ltx_native.py` |
| Performance capture (Act-Two, LivePortrait, Viggle) | `performance/` package: `performance/act_two.py` (Runway, migrated from Act-One), `performance/live_portrait.py`, `performance/viggle.py` (LIMITED — see ADR-082); dispatched by `performance/_router.py` |
| ComfyUI workflows | `pulid.json` (production, 22 nodes) — the only image tier since the max tier was retired (WS1; DECISIONS.md ADR-065) |

## Common Failure Modes

### 1. Identity Drift Across Shots
**Symptom**: Character looks different between shots. **Diagnose**: Check PuLID weight vs shot type, verify reference images loaded, check identity_validator rolling stats. **Fix**: Increase PuLID weight, add subject binding references for Kling, use face swap as post-process.

### 2. Color Palette Shift Between Scenes
**Symptom**: Jarring color changes. **Diagnose**: Run coherence_analyzer, check color_drift score. **Fix**: Tighten denoise for img2img chaining, apply consistent LUT in FFmpeg, ensure location seeds are deterministic.

### 3. API Quota Exhaustion
**Symptom**: All APIs returning errors. **Diagnose**: Check cascade logs for "exhausted" messages; Veo quota cooldown is the TTL timestamp `_VEO_QUOTA_EXHAUSTED_UNTIL` checked via `_veo_quota_blocked()` (`phase_c_ffmpeg.py`, auto-expires after 30 min). **Fix**: Wait for the 30s cascade pause / TTL expiry, verify API keys, check billing limits, consider LTX (cheapest) for non-critical shots.

### 4. Lip Sync Prerequisites Not Met
**Symptom**: Lip sync fails or produces artifacts. **Diagnose**: Check video format (codec, resolution), audio format (mono/stereo, duration match), face visibility in first frame. **Fix**: Ensure front-facing face in frame, match audio duration to video, use generation mode (Omnihuman) for interview shots instead of overlay.

### 5. Temporal Discontinuity (Flickering/Jumping)
**Symptom**: Frame-to-frame flicker or object teleportation. **Diagnose**: Check denoise value (too high = inconsistency), verify temporal img2img chain is active, check if scene boundary reset happened mid-shot. **Fix**: Lower denoise, ensure consecutive shots chain from previous output, apply RIFE frame interpolation.

## Integrated Capabilities

The pipeline now uses these previously-idle tools:

### ComfyUI Production Workflow (`phase_c_assembly.py`)
- **img2img chaining** (nodes 200-201): Load and VAE-encode the previous shot, then rewire the sampler latent for temporal consistency
- **No dynamic ControlNet/IP-Adapter branch**: the former nodes 400-402 and 410-411 were structurally invalid for the production FLUX graph and are not injected
- **ReActor face swap** (ComfyUI-native, was injected via the retired `quality_max.py` max tier — no longer available in-graph post-WS1; face swap now runs as a post-process via `phase_c_vision.py` DeepFace)

### Quality-Gated Post-Processing
- **Motion quality assessment**: `assess_motion_quality()` (`phase_c_ffmpeg.py`, called from `cinema/shots/controller.py`) runs optical flow analysis → auto-triggers RIFE if jittery
- **Lip sync routing**: `generate_lip_sync_video(mode='auto'|'overlay'|'generation')` in `lip_sync.py`; `mode='skip'` short-circuits to None (original video kept) — there is no `recommend_lip_sync_mode()` helper (deleted as dead code in 475a36a)
- **Color grading**: `apply_color_grade()` (`phase_c_ffmpeg.py`) maps project mood to FFmpeg preset (suspense→cool_noir, hopeful→golden_hour)
- **Audio mastering**: `master_music()` applies cinema_master preset (EQ + compression) to BGM before assembly

### Shot-Type-Aware Improvements (`phase_c_ffmpeg.py`)
- **Negative prompts per shot type**: Portrait adds "closed eyes, blown highlights"; action adds "frozen pose, weightless movement"
- **Smart Sora durations**: 8s for action/wide (full physics arcs), 4s for portrait/medium (minimize drift)
- **LTX camera motion mapping**: Pipeline motions → LTX's 15 native camera params
- **LTX 4K for landscape**: Automatically uses 4K resolution for landscape shots

## LLM Integration

The pipeline's LLMs are equipped with skill knowledge:

- **Shared context block**: scene decomposer, Chief Director, and style director all inject the same `<PIPELINE_CONTEXT>` block (`pipeline_context.py` loading `config/prompts/pipeline_context.md`) — it carries the per-shot-type video-API guidance, cost ordering, PuLID/identity parameters, and camera-motion notes.
- **Scene Decomposer** (`domain/scene_decomposer.py:431`): uses `<PIPELINE_CONTEXT>` to make intelligent `target_api` decisions instead of defaulting to AUTO.
- **Chief Director** (`llm/chief_director.py:283`): uses `<PIPELINE_CONTEXT>` for smarter prompt mutations when retrying failed generations.
- **Video Generator** (`phase_c_ffmpeg.py`): Uses shot-type-aware negative prompts (portrait adds "closed eyes, blown highlights"; action adds "frozen pose, weightless movement") and smart duration selection per API (Sora: 8s for action, 4s for portrait).
