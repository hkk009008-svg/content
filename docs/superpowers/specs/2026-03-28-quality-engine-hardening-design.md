# Sub-Project 1: Quality Engine Hardening

**Date:** 2026-03-28
**Status:** Draft
**Scope:** Backend quality improvements — identity, coherence, motion

## Context

The cinema pipeline generates AI video content through a multi-phase process: script → audio → images → video → assembly. Three areas produce inconsistent output quality:

1. **Character face consistency** — faces drift between shots because identity validation uses fixed thresholds, samples only 3 frames, and provides no diagnostic feedback
2. **Visual coherence** — consecutive shots don't feel like the same film because lighting/color consistency is only enforced via text prompts with no visual validation
3. **Video motion quality** — AI-generated videos have artifacts, and the API cascade can loop infinitely when all providers fail

This spec covers backend-only changes. UI improvements (Sub-Project 3) will surface these new metrics later.

---

## Component A: Character Identity System Overhaul

### Problem

- Only 3 frames sampled at fixed positions (25%, 50%, 75%) — misses drift at video start/end
- Single threshold (0.55/0.70) for all shot types — wide shots with tiny faces fail unfairly
- No per-character scoring — if character A passes but B fails, no visibility
- API contract mismatch: `validate_identity()` returns `bool` but callers expect `dict`
- PuLID weights are static — system never learns from identity failures
- No failure analysis — when identity fails, no one knows why

### Solution

#### New file: `identity_types.py`

Shared data structures for the identity system:

- **`FailureReason` enum**: `NO_FACE_DETECTED`, `LOW_CONFIDENCE_DETECTION`, `FACE_ANGLE_EXTREME`, `OCCLUSION`, `WRONG_PERSON`, `MULTIPLE_FACES_AMBIGUOUS`, `SMALL_FACE_REGION`, `POOR_LIGHTING`, `PASSED`

- **`FrameSample` dataclass**: Per-frame analysis — `frame_index`, `face_detected`, `face_confidence`, `face_area_ratio` (bbox area / frame area), `face_angle_estimate` (frontal/three_quarter/profile), `similarity`, `matched`, `failure_reason`

- **`CharacterIdentityResult` dataclass**: Per-character aggregate — `best_similarity`, `mean_similarity`, `min_similarity`, `frame_results[]`, `matched`, `primary_failure_reason`, `suggested_pulid_adjustment` (-0.1 to +0.1)

- **`IdentityValidationResult` dataclass**: Complete result — `passed`, `overall_score`, `character_results{}`, `frames_sampled`, `shot_type`, `threshold_used`. Includes `.get(key)` method for backward compatibility with dict-expecting code.

- **`SHOT_TYPE_THRESHOLDS` dict**:

  | Shot Type  | Strict | Standard | Lenient |
  |-----------|--------|----------|---------|
  | portrait  | 0.75   | 0.70     | 0.60    |
  | medium    | 0.70   | 0.65     | 0.55    |
  | wide      | 0.60   | 0.55     | 0.45    |
  | action    | 0.65   | 0.60     | 0.50    |
  | landscape | 0.0    | 0.0      | 0.0     |

- **`get_threshold_for_shot(shot_type, mode, attempt, max_attempts)`**: Returns threshold adjusted for shot type and retry attempt. On first attempt uses `mode` threshold. On final attempt degrades linearly to `lenient`. Prevents infinite retry loops.

#### New file: `identity_validator.py`

Unified `IdentityValidator` class replacing 4 scattered validate functions:

**`validate_image(image_path, reference_path, character_id, shot_type, threshold)`**
- Validates a single generated image against reference
- Returns `IdentityValidationResult` (backward-compatible via `.get()`)

**`validate_video(video_path, character_configs, shot_type, threshold, mode, attempt, max_attempts)`**
- Validates characters in generated video with adaptive sampling
- `character_configs`: `[{"id", "reference_image", "name"}]`
- Threshold auto-computed from shot_type + mode + attempt if not overridden

**Adaptive frame sampling** (`compute_sample_positions`):
- Base: 1 sample per 0.5 seconds, clamped to [3, 10]
- Portrait: 2x density (face is the whole frame)
- Action: 1.5x (motion needs more samples)
- Wide: 1x (face small, fewer useful frames)
- Always includes anchors at 10%, 50%, 90%

**Per-frame analysis** (`_analyze_frame`):
- Extract frame → detect faces via DeepFace
- Compute: face_area_ratio, face_confidence, face_angle_estimate (w:h ratio heuristic)
- Match against reference embeddings (cosine similarity mapped to 0-1)
- Return `FrameSample` with full diagnostics

**Failure diagnosis** (`_diagnose_failure`):
- Priority chain: no face → low confidence → small face → extreme angle → wrong person → poor lighting
- Analyzed from all FrameSamples for a character

**Rolling history** (`get_rolling_stats(character_id, window=10)`):
- Tracks last N validation results per character
- Returns: `mean_similarity`, `success_rate`, `common_failure`, `suggested_pulid_delta`, `sample_count`
- PuLID delta logic:
  - success_rate < 50% → +0.10 (identity failing badly, boost PuLID)
  - success_rate < 80% → +0.05
  - success_rate = 100% and mean > 0.80 → -0.05 (can reduce for creativity)
  - Otherwise → 0.0

#### Modified: `workflow_selector.py`

New function `get_adaptive_pulid_weight(shot_type, character_id, identity_validator)`:
- Start from static base weight for shot type
- Query `identity_validator.get_rolling_stats(character_id)`
- Apply suggested delta, clamped to [0.0, 1.0]
- Smart: does NOT boost PuLID for `FACE_ANGLE_EXTREME` or `SMALL_FACE_REGION` (PuLID can't help with these)

#### Modified: `continuity_engine.py`

- `ContinuityEngine.__init__`: instantiate shared `IdentityValidator` with pre-loaded embeddings
- `enhance_shot_prompt()`: compute `shot_type` early, get adaptive threshold and PuLID weight, pass through `continuity_config`:
  - `identity_threshold` (was: fixed constant)
  - `shot_type` (new)
  - `pulid_weight_override` (new)
- New method `validate_shot()`: delegates to `self.identity_validator.validate_video()` (with history tracking)

#### Modified: `phase_c_vision.py`

- Wrap existing `validate_identity()`, `validate_identity_image()`, `validate_multi_identity()` as deprecated shims delegating to `IdentityValidator`
- Preserve return types for backward compatibility

#### Modified: `phase_c_assembly.py`

- After `apply_workflow_params()`, check for `pulid_weight_override` in kwargs
- If present, override ComfyUI workflow node 100 weight with adaptive value

#### Modified: `cinema_pipeline.py`

- Image validation loop: use per-shot-type threshold from `continuity_config`
- Video validation loop: pass `shot_type`, `attempt`, `max_attempts` for adaptive threshold
- Pass `pulid_weight_override` kwarg to `generate_ai_broll()`

#### Modified: `chief_director.py`

- `evaluate_generation_quality()`: accept `IdentityValidationResult` instead of raw float
- Build structured diagnostic prompt with per-character failure reasons for smarter LLM mutations

---

## Component B: Visual Coherence Engine

### Problem

- Temporal consistency only uses img2img chaining with fixed denoise (0.45/0.35)
- Physics prompt engineer injects text constraints but never validates visual output
- Style rules are generated once and never re-evaluated against actual images
- No metric for "do these shots look like they belong together?"

### Solution

#### New file: `coherence_analyzer.py`

**`ColorCoherenceAnalyzer`**:
- `extract_color_histogram(image_path)` → histogram (HSV space, 64 bins per channel)
- `compare_histograms(hist_a, hist_b)` → similarity score (0-1, using OpenCV `compareHist` with correlation method)
- `compute_scene_palette(images[])` → dominant colors (k-means with k=5)
- `detect_palette_drift(current_img, scene_palette)` → drift_score (0-1, higher = more drift)

**`CompositionAnalyzer`**:
- `analyze_brightness_distribution(image_path)` → `{mean_brightness, std_brightness, key_type}` (high-key / low-key / balanced)
- `compare_lighting_direction(img_a, img_b)` → consistency_score (gradient direction comparison)
- `detect_exposure_shift(images[])` → max_exposure_delta

**`SceneCoherenceResult` dataclass**:
- `overall_coherence_score`: 0-1 (weighted: 0.4 color + 0.3 lighting + 0.3 composition)
- `color_drift`: float
- `lighting_consistency`: float
- `composition_similarity`: float
- `recommendations`: `["tighten_denoise", "adjust_color_prompt", "match_lighting"]`

#### Modified: `continuity_engine.py` — Context-Aware Denoise

Replace hardcoded denoise with transition-type scaling:

| Transition Type | Denoise | Rationale |
|----------------|---------|-----------|
| Same location, consecutive | 0.30 | Tightest — preserve everything |
| Same location, time skip | 0.40 | Some change expected |
| Location change within scene | 0.50 | New environment, keep character |
| First shot of new scene | 0.55 | Fresh start, max creativity |

`get_denoise_strength(shot_index, previous_shot, current_shot)` now accepts previous_shot context to determine transition type.

#### Modified: `chief_director.py` — Coherence-Aware Mutations

2x2 mutation matrix:

| | Identity PASS | Identity FAIL |
|---|---|---|
| **Coherent** | ACCEPT | Mutate: identity cues only |
| **Incoherent** | Mutate: lighting/color/composition cues | Mutate: aggressive — rework entire prompt |

---

## Component C: Video Motion Quality

### Problem

- Infinite recursion when all video APIs fail (C1 from code review)
- No motion quality metric — can't detect frozen frames, jitter, or warping
- Lip sync mode selection is purely input-based, ignoring content characteristics
- RIFE interpolation applied blindly to all videos regardless of need

### Solution

#### Modified: `phase_c_ffmpeg.py`

**Fix infinite recursion (C1):**
- Add `max_cascade_retries` parameter (default=2)
- After exhausting all APIs × max_retries, hard-fail with descriptive error
- Also fix: add `import json` (C3 from code review)

**New function `assess_motion_quality(video_path)`:**
- Extract 10 uniformly-spaced frames
- Compute optical flow between consecutive pairs (OpenCV Farneback)
- Detect: frame freezing (flow < threshold), jitter (high variance), warp artifacts (extreme gradients)
- Return `MotionQualityResult`:
  - `smoothness_score`: 0-1
  - `artifact_frames`: frame indices with issues
  - `frozen_ratio`: fraction of near-identical frames
  - `recommendation`: `"accept"` | `"interpolate"` | `"regenerate"`

**Smart API selection on retry:**
- Action shots → prioritize Kling 3.0 (best motion)
- Dialogue/talking head → prioritize VEO (better consistency)
- Static/establishing → any API

#### Modified: `lip_sync.py` — Content-Aware Routing

New function `recommend_lip_sync_mode(video_path, shot_type, dialogue_length)`:
- Portrait + dialogue > 3s → GENERATION mode (Omnihuman for better talking heads)
- Camera motion detected → OVERLAY mode (preserve motion)
- Face < 15% of frame → skip lip sync
- Face is profile/back → skip lip sync

#### Modified: `cinema_pipeline.py` — Quality-Gated Post-Processing

After video generation, before assembly:
1. Run `assess_motion_quality()` on raw video
2. `"interpolate"` → apply RIFE
3. `"regenerate"` → retry (counts toward cascade limit)
4. `"accept"` → proceed directly (saves RIFE compute)

---

## Implementation Sequence

### Phase 1: Foundation (no behavior change)
1. Create `identity_types.py`
2. Create `identity_validator.py`

### Phase 2: API Fix (backward compatible)
3. Wrap `phase_c_vision.py` functions as deprecation shims
4. Verify cinema_pipeline.py still works identically

### Phase 3: Adaptive Identity
5. Implement adaptive frame sampling
6. Implement per-frame diagnostics + failure diagnosis
7. Wire per-shot-type thresholds into continuity_engine → cinema_pipeline

### Phase 4: Feedback Loop
8. Implement rolling stats + adaptive PuLID weights
9. Wire through workflow_selector → phase_c_assembly

### Phase 5: Visual Coherence
10. Create `coherence_analyzer.py`
11. Integrate context-aware denoise in continuity_engine
12. Add coherence-aware mutations to chief_director

### Phase 6: Motion Quality
13. Fix infinite recursion + add import json
14. Implement motion quality assessment
15. Add content-aware lip sync routing
16. Add quality-gated post-processing in cinema_pipeline

---

## Verification Plan

### Unit Tests
- `identity_types.py`: Threshold computation for all shot types × retry attempts
- `identity_validator.py`: Frame sampling positions for various durations/shot types
- `coherence_analyzer.py`: Histogram comparison with known-similar and known-different images
- Motion quality: Known-good and known-bad video samples

### Integration Tests
- End-to-end: Generate a 2-scene project, verify identity scores are per-shot-type appropriate
- Verify PuLID weight adaptation after simulated identity failures
- Verify denoise scaling matches transition types
- Verify cascade retry limit terminates (no infinite loop)

### Manual Verification
- Run full pipeline on existing test project
- Compare identity pass rates before/after (expect improvement on wide shots)
- Compare visual coherence between consecutive shots
- Verify no regression in generation time

---

## Files Summary

### New Files
| File | Purpose |
|------|---------|
| `identity_types.py` | Shared dataclasses, enums, threshold tables |
| `identity_validator.py` | Unified identity validation with adaptive sampling, diagnostics, rolling stats |
| `coherence_analyzer.py` | Color/lighting/composition coherence analysis |

### Modified Files
| File | Changes |
|------|---------|
| `phase_c_vision.py` | Deprecated shims → IdentityValidator |
| `continuity_engine.py` | Shared IdentityValidator, adaptive thresholds, context-aware denoise |
| `cinema_pipeline.py` | Per-shot thresholds, PuLID override, quality-gated post-processing |
| `workflow_selector.py` | `get_adaptive_pulid_weight()` |
| `phase_c_assembly.py` | PuLID weight override from continuity_config |
| `chief_director.py` | Structured diagnostics + coherence-aware mutations |
| `phase_c_ffmpeg.py` | Cascade retry limit, motion quality assessment, import json fix |
| `lip_sync.py` | Content-aware mode recommendation |

### Unchanged Files
- `location_manager.py`, `scene_decomposer.py`, `dialogue_writer.py`, `style_director.py`
- `phase_b_audio.py`, `phase_d_upload.py`, `phase_e_learning.py`
- `character_manager.py`, `project_manager.py`
- `web_server.py`, `web/` (UI changes deferred to Sub-Project 3)
