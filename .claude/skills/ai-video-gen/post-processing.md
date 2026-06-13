# Post-Processing Pipeline

The pipeline from raw generated video to final export: identity validation → face swap → lip sync → frame interpolation → upscaling → FFmpeg assembly.

---

## 1. Identity Validation

**Source**: `identity/validator.py`, `phase_c_vision.py`

### Adaptive Frame Sampling
Extracts frames from generated video for identity comparison:
- Frame count varies by shot type and video duration
- Portrait: 2.0x density (face is primary subject)
- Action: 1.5x density (motion requires more samples)
- Medium/Wide: 1.0x density
- Landscape: 0.0x (skip validation entirely)

### Per-Frame Analysis
Each frame produces:
- `face_detected`: Boolean
- `face_confidence`: Detection confidence score
- `face_area_ratio`: Face area / total frame area
- `face_angle_estimate`: "frontal", "three_quarter", "profile"
- `similarity`: 0.0–1.0 score vs character reference embedding
- `failure_reason`: Enum if failed (see character-consistency.md)

### Validation Result
- **Pass**: `mean_similarity >= threshold` for the shot type
- **Fail**: Triggers face swap pipeline or shot re-generation
- **Rolling stats**: Fed back to PuLID weight adjustment system

---

## 2. Face Swap

**Source**: `phase_c_vision.py`

Applied when identity validation fails and re-generation is not viable.

### Cascade Priority
1. **FAL PixVerse swap** (cloud, no local GPU required)
   - Best for single-face swaps
   - Preserves expression and lighting
2. **FaceFusion CLI** (local, requires full install)
   - More control over parameters
   - Handles multi-face scenarios

### When to Use Face Swap vs Re-Generate
- **Face swap**: When the video motion/composition is good but face identity drifted
- **Re-generate**: When the video has fundamental issues (wrong pose, bad composition)
- **Accept as-is**: For wide shots where face is small (SMALL_FACE_REGION)

---

## 3. Lip Sync

**Source**: `lip_sync.py`

Two operational modes for audio-visual synchronization.

### Mode 1: OVERLAY — Default for Cinematic Shots

**How it works**: Takes existing video + audio → overlays lip movement on the mouth region ONLY.

**Preserves**: 100% of camera movement, body motion, lighting, composition, and cinematography.

**Best for**: Any shot that already has good camera work from video generation.

**Fallback chain**: sync.so v3 (`fal-ai/sync-lipsync/v3`, ATTEMPT 0) → MuseTalk (`fal-ai/musetalk`, ATTEMPT 1) → LatentSync (ATTEMPT 2) → Sync Lipsync v2 (`fal-ai/sync-lipsync/v2`, ATTEMPT 3)

**Prerequisites**:
- Video must have detectable face
- Audio must be mono or stereo
- Duration must reasonably match

### Mode 2: GENERATION — For Dialogue Shots

**How it works**: Takes still image + audio → generates full-body talking video from scratch.

**Creates**: Head movement, gestures, expressions correlated with speech.

**Replaces**: Entire video (loses any existing camera/motion from video gen).

**Best for**: Interview-style, direct-to-camera dialogue shots.

**Fallback chain**: Hedra Character-3 (direct `api.hedra.com`; `fal-ai/hedra/character-3` proxy is dead/404) → Kling Lip Sync (`fal-ai/kling-video/lipsync/audio-to-video`) → Omnihuman v1.5 (`fal-ai/bytedance/omnihuman/v1.5`) → Creatify Aurora

**Prerequisites**:
- Front-facing portrait image
- Clean background preferred
- Audio duration < 60 seconds

### Smart Router
`generate_lip_sync_video()` auto-selects mode:
- If `existing_video` provided → **OVERLAY** (preserve cinematic video)
- If `image` only → **GENERATION** (create from scratch)
- User can force specific mode via parameter

### Decision Guide

| Scenario | Mode | Rationale |
|----------|------|-----------|
| Character talking during action | Overlay | Preserve motion, add lip sync |
| Interview/monologue shot | Generation | Better expressions from scratch |
| Wide shot with distant face | Skip | Face too small for lip sync |
| Close-up dialogue | Overlay | Preserve Kling's face quality |
| Multiple speakers | Overlay per speaker | Preserve composition |

---

## 4. Frame Interpolation

**Source**: `lip_sync.py` (RIFE integration)

### RIFE (Real-Time Intermediate Flow Estimation)
- Interpolates between frames to increase frame rate
- **30fps → 60fps** (multiplier = 2, which gives 3x FPS in some configs)
- Cloud-based via FAL
- Reduces frame-to-frame flicker
- Applied after lip sync, before upscaling

### When to Apply
- Always for final export quality
- Skip for draft/preview renders
- Especially important after lip sync overlay (smooths boundary artifacts)

### Dialogue / audio safety (re-mux)
- `fal-ai/rife/video` returns **video-only** output — bare RIFE strips the audio track by design (its schema has no audio field).
- `generate_rife_interpolation` therefore re-muxes the **source clip's** audio back onto the interpolated video (`_restore_audio_track`: `ffmpeg -map 0:v:0 -map 1:a:0? -c copy -shortest`). Without this, a lip-synced / native-audio / TTS-overlaid take goes **silent** — and because auto-RIFE is default-on for dialogue takes (`_maybe_auto_rife`), the silent clip rebinds the take and the assembler suppresses the scene-TTS re-mux (`dialogue_audio_in_clip=True` still claims the clip carries audio) → silent dialogue in the final export.
- **Audio integrity over smoothing:** if the re-mux fails, `generate_rife_interpolation` returns `None` and the caller keeps the original audio-bearing clip rather than a silent interpolated one.
- Pinned by `tests/unit/test_rife_audio_remux.py` (function level) + `tests/unit/test_auto_rife_audio_integration.py` (through the controller, real ffmpeg).

---

## 5. Video Upscaling

**Source**: `lip_sync.py` (SeedVR2); Real-ESRGAN is in the ComfyUI workflow (`pulid.json`)

### SeedVR2 (Preferred)
- **Temporally consistent** upscaling — no inter-frame flicker
- Superior to per-frame upscaling approaches
- Cloud-based via FAL
- Best for: All final exports

### Real-ESRGAN 4x (Fallback)
- Per-frame upscaling
- Can introduce temporal inconsistency (shimmer between frames)
- Available in ComfyUI workflow (`pulid.json` nodes 500-502)
- Upscales to 2688x1536 (2.7K cinema resolution)
- Uses Lanczos resampling

### When to Use Which
| Scenario | Method | Rationale |
|----------|--------|-----------|
| Final export | SeedVR2 | Temporal consistency |
| ComfyUI pipeline | Real-ESRGAN | Built into workflow |
| Quick preview | Neither | Save compute |
| 4K source (LTX) | Neither | Already at target resolution |

---

## 6. Transitions

Assembly uses **hard cuts only** — no AI-generated transition clips. Wan FLF2V transition generation does not exist in the pipeline (`workflow_selector.py` explicitly states "Assembly uses HARD CUTS only"). Mood-aware transition generation via video APIs is not implemented.

---

## 7. FFmpeg Assembly

**Source**: `phase_c_ffmpeg.py`

The final assembly stage combines all generated assets into a complete video.

### Per-Scene Assembly (`stitch_modules()` — `phase_c_ffmpeg.py:949`)
1. Concatenate shot video clips in order
2. Insert hard cuts between shots (no AI transition clips)
3. Produce per-scene stitched video

### Master Assembly (`cinema_pipeline.py:_assemble_final()`)
Combines everything into the final export:

```
Input:
  - Video clips (per scene, stitched via stitch_modules)
  - TTS voiceover audio
  - Background music
  - Foley/sound effects
  - SRT subtitles

Processing:
  1. Normalize all clips to consistent codec/resolution
  2. Apply color grading LUT
  3. Mix audio tracks (voice + BGM + foley)
  4. Burn subtitles or embed SRT
  5. Apply timeline effects (motion blur, depth)

Output:
  - Final MP4 with all tracks merged
```

Note: `execute_master_ffmpeg_assembly()` and `normalize_clip()` do not exist in `phase_c_ffmpeg.py`.

### Color Grading Presets
| Preset | Description |
|--------|-------------|
| `warm_cinema` | Warm tones, slight orange in highlights |
| `cool_noir` | Cold tones, blue shadows, reduced saturation |
| `vibrant` | Boosted saturation, slight brightness lift |
| `desaturated` | Muted colors, slight contrast boost |
| `golden_hour` | Warm golden tones, lifted shadows |
| `moonlight` | Cool, desaturated, dark |
| `high_contrast` | Crushed blacks, bright highlights |
| `pastel` | Soft, low contrast, lifted blacks |

### Audio Mixing
- **Voice**: Primary track, normalization applied
- **BGM**: Mixed at lower level (~-12dB relative to voice)
- **Foley**: Scene-specific sound effects, mixed to match action
- **Silence trimming**: Applied to TTS output for natural pacing

---

## Pipeline Order Summary

```
Generated Video
    ↓
Identity Validation (DeepFace)
    ├── Pass → Continue
    └── Fail → Face Swap (PixVerse/FaceFusion) → Validate Again
    ↓
Lip Sync (if dialogue)
    ├── Existing video → Overlay (MuseTalk)
    └── Image only → Generation (Omnihuman)
    ↓
Frame Interpolation (RIFE: 30→60fps)
    ↓
Upscaling (SeedVR2 or Real-ESRGAN)
    ↓
Per-Clip Normalization (FFmpeg: codec, resolution, effects)
    ↓
Scene Stitching (stitch_modules — hard cuts, no AI transitions)
    ↓
Master Assembly (_assemble_final — video + voice + BGM + foley + subtitles)
    ↓
Final Export (.mp4)
```
