---
name: ai-video-gen
description: Use when working on AI video generation, cinema pipeline, shot routing, video API selection (Kling, Sora, Veo, LTX, Runway), character consistency, identity validation, continuity systems, prompt engineering for video, lip sync, face swap, post-processing, or any work involving the cinematic video production pipeline.
---

# AI Video Generation Expert

This pipeline transforms scripts into photorealistic cinematic video through a multi-phase architecture:

```
Scene Decomposition → Continuity Enhancement → Image Gen (FLUX+PuLID)
    → Video Gen (5 APIs) → Identity Validation → Face Swap (if needed)
    → Lip Sync → Frame Interpolation (RIFE) → Upscale (SeedVR2)
    → FFmpeg Assembly (color grade + audio + subtitles)
```

## API Selection Decision Tree

Choose the primary API based on shot type. Each has an ordered fallback cascade:

| Shot Type | Primary API | Why | Fallback Chain |
|-----------|------------|-----|----------------|
| **Portrait** | KLING_NATIVE | Subject binding + `face_consistency=True` flag | Runway Gen-4 → Sora → Kling FAL |
| **Medium** | KLING_NATIVE | Good face + scene balance | Runway Gen-4 → Sora → LTX |
| **Wide** | LTX | 4K, depth-aware, cheapest | Veo → Kling → Runway |
| **Action** | SORA_NATIVE | Best motion physics, cloth sim, body momentum | Kling → Runway → LTX |
| **Landscape** | LTX | No face needed, 4K, lowest cost | Veo → Kling |

**Cascade logic**: Try primary → on failure, next in chain → if all exhausted, wait 2 min for quota refresh → retry up to 2 full cycles.

## Critical Numbers

### PuLID Weight by Shot Type (ComfyUI image gen)
| Shot | Weight | start_at | end_at | Denoise | Rationale |
|------|--------|----------|--------|---------|-----------|
| Portrait | 1.0 | 0.20 | 1.0 | 0.25 | Maximum face lock |
| Medium | 0.9 | 0.25 | 1.0 | 0.35 | Strong face, scene balance |
| Wide | 0.65 | 0.35 | 0.9 | 0.45 | Environment priority |
| Action | 0.8 | 0.30 | 1.0 | 0.40 | Identity through motion |
| Landscape | 0.0 | 0.0 | 0.0 | 0.55 | No face lock |

### Identity Validation Thresholds
| Shot | Strict | Standard | Lenient |
|------|--------|----------|---------|
| Portrait | 0.75 | 0.70 | 0.60 |
| Medium | 0.70 | 0.65 | 0.55 |
| Wide | 0.60 | 0.55 | 0.45 |
| Action | 0.65 | 0.60 | 0.50 |
| Landscape | — | — | — |

Thresholds degrade linearly from standard → lenient across retry attempts.

### Temporal Denoise (img2img chaining)
| Context | Denoise | Why |
|---------|---------|-----|
| First shot of scene | 0.55 | Maximum creative freedom |
| Same location, consecutive | 0.30 | Tightest consistency |
| Same location, time skip | 0.40 | Allow some change |
| Location change within scene | 0.50 | New environment, keep style |

### Sampler Constants (always)
- **Sampler**: dpmpp_2m (higher-order solver, sharper results)
- **Scheduler**: sgm_uniform (optimized sigma for FLUX flow-matching)
- **Guidance**: 3.0–4.0 (3.5 is the FLUX sweet spot for character scenes)

## Quality Gates

### 1. Chief Director (Metacognitive QA)
LLM layer (Codex → GPT-4o fallback) that validates ALL pipeline outputs. Can REJECT and REWRITE prompts violating structural constraints. Sits above all other LLMs.

### 2. Scene Coherence Score
```
score = 0.4 * color_consistency + 0.3 * lighting_consistency + 0.3 * composition_similarity
```
- Color: HSV histogram correlation + k-means palette drift detection
- Lighting: Sobel gradient angular consistency (light direction)
- Composition: Brightness distribution, exposure shift

**Thresholds**: color_drift > 0.3 → flag | lighting < 0.5 → flag | brightness_delta > 0.15 → flag

### 3. Identity Validation
Adaptive frame sampling (3–10 frames based on shot type + duration). Per-frame diagnostics: face_detected, angle_estimate, similarity score, failure_reason. Rolling stats feed PuLID weight adjustment (+0.10 on failure, −0.05 on pass, skip FACE_ANGLE_EXTREME/SMALL_FACE_REGION).

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
| Scene → shots breakdown | `scene_decomposer.py` |
| Continuity (4 subsystems) | `continuity_engine.py` |
| Character management | `character_manager.py` |
| Identity validation | `identity_validator.py`, `identity_types.py` |
| Coherence analysis | `coherence_analyzer.py` |
| Style direction | `style_director.py` |
| Chief Director QA | `chief_director.py` |
| Lip sync | `lip_sync.py` |
| Face swap + DeepFace | `phase_c_vision.py` |
| Image gen (FLUX+PuLID) | `phase_c_assembly.py` |
| Audio (TTS + BGM + foley) | `phase_b_audio.py` |
| Kling API | `kling_native.py` |
| Sora API | `sora_native.py` |
| Veo API | `veo_native.py` |
| LTX API | `ltx_native.py` |
| ComfyUI workflow | `Pulid.json` |

## Common Failure Modes

### 1. Identity Drift Across Shots
**Symptom**: Character looks different between shots. **Diagnose**: Check PuLID weight vs shot type, verify reference images loaded, check identity_validator rolling stats. **Fix**: Increase PuLID weight, add subject binding references for Kling, use face swap as post-process.

### 2. Color Palette Shift Between Scenes
**Symptom**: Jarring color changes. **Diagnose**: Run coherence_analyzer, check color_drift score. **Fix**: Tighten denoise for img2img chaining, apply consistent LUT in FFmpeg, ensure location seeds are deterministic.

### 3. API Quota Exhaustion
**Symptom**: All APIs returning errors. **Diagnose**: Check cascade logs for "exhausted" messages, look for global quota flags (e.g., `_veo_quota_exhausted`). **Fix**: Wait 2 min for quota refresh, verify API keys, check billing limits, consider LTX (cheapest) for non-critical shots.

### 4. Lip Sync Prerequisites Not Met
**Symptom**: Lip sync fails or produces artifacts. **Diagnose**: Check video format (codec, resolution), audio format (mono/stereo, duration match), face visibility in first frame. **Fix**: Ensure front-facing face in frame, match audio duration to video, use generation mode (Omnihuman) for interview shots instead of overlay.

### 5. Temporal Discontinuity (Flickering/Jumping)
**Symptom**: Frame-to-frame flicker or object teleportation. **Diagnose**: Check denoise value (too high = inconsistency), verify temporal img2img chain is active, check if scene boundary reset happened mid-shot. **Fix**: Lower denoise, ensure consecutive shots chain from previous output, apply RIFE frame interpolation.

## Integrated Capabilities

The pipeline now uses these previously-idle tools:

### ComfyUI Enhanced Workflow (dynamic node injection in `phase_c_assembly.py`)
- **ControlNet Depth** (nodes 400-402): DepthAnythingV2 extracts depth map from prev shot → guides spatial consistency
- **IP-Adapter Style Transfer** (nodes 410-411): Locks color/lighting/atmosphere from previous shot via style-only weight
- **ReActor + CodeFormer** (node 420): Post-generation face swap with face restoration as ComfyUI-native fallback
- **img2img chaining** (nodes 200-201): VAEEncode prev shot → controlled denoise for temporal consistency

### Quality-Gated Post-Processing (`cinema_pipeline.py`)
- **Motion quality assessment**: `assess_motion_quality()` runs optical flow analysis → auto-triggers RIFE if jittery
- **Smart lip sync routing**: `recommend_lip_sync_mode()` analyzes shot type + dialogue length → skip/overlay/generation
- **Color grading**: `apply_color_grade()` maps project mood to FFmpeg preset (suspense→cool_noir, hopeful→golden_hour)
- **Audio mastering**: `master_music()` applies cinema_master preset (EQ + compression) to BGM before assembly

### Shot-Type-Aware Improvements (`phase_c_ffmpeg.py`)
- **Negative prompts per shot type**: Portrait adds "closed eyes, blown highlights"; action adds "frozen pose, weightless movement"
- **Smart Sora durations**: 8s for action/wide (full physics arcs), 4s for portrait/medium (minimize drift)
- **LTX camera motion mapping**: Pipeline motions → LTX's 15 native camera params
- **LTX 4K for landscape**: Automatically uses 4K resolution for landscape shots

## LLM Integration

The pipeline's LLMs are equipped with skill knowledge:

- **Scene Decomposer** (`scene_decomposer.py`): Has `<VIDEO_API_EXPERTISE>` section — knows which API is best per shot type, cost ordering, and camera motion guidance. Makes intelligent `target_api` decisions instead of defaulting to AUTO.
- **Chief Director** (`chief_director.py`): Has `<VIDEO_GENERATION_EXPERTISE>` section — understands PuLID weights, identity thresholds, ComfyUI parameters, and mutation strategies. Makes smarter prompt mutations when retrying failed generations.
- **Video Generator** (`phase_c_ffmpeg.py`): Uses shot-type-aware negative prompts (portrait adds "closed eyes, blown highlights"; action adds "frozen pose, weightless movement") and smart duration selection per API (Sora: 8s for action, 4s for portrait).
