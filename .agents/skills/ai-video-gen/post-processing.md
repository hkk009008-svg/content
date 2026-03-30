# Post-Processing Pipeline

The pipeline from raw generated video to final export: identity validation → face swap → lip sync → frame interpolation → upscaling → FFmpeg assembly.

---

## 1. Identity Validation

**Source**: `identity_validator.py`, `phase_c_vision.py`

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

### Mode 1: OVERLAY (MuseTalk) — Default for Cinematic Shots

**How it works**: Takes existing video + audio → overlays lip movement on the mouth region ONLY.

**Preserves**: 100% of camera movement, body motion, lighting, composition, and cinematography.

**Best for**: Any shot that already has good camera work from video generation.

**FAL endpoint**: `fal-ai/musetalk`

**Fallback chain**: MuseTalk → LatentSync → Sync Lipsync v2

**Prerequisites**:
- Video must have detectable face
- Audio must be mono or stereo
- Duration must reasonably match

### Mode 2: GENERATION (Omnihuman v1.5) — For Dialogue Shots

**How it works**: Takes still image + audio → generates full-body talking video from scratch.

**Creates**: Head movement, gestures, expressions correlated with speech.

**Replaces**: Entire video (loses any existing camera/motion from video gen).

**Best for**: Interview-style, direct-to-camera dialogue shots.

**FAL endpoint**: `fal-ai/bytedance/omnihuman/v1.5`

**Fallback chain**: Kling native lip sync → Omnihuman v1.5 → Creatify Aurora

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

---

## 5. Video Upscaling

**Source**: `lip_sync.py`, `phase_c_ffmpeg.py`

### SeedVR2 (Preferred)
- **Temporally consistent** upscaling — no inter-frame flicker
- Superior to per-frame upscaling approaches
- Cloud-based via FAL
- Best for: All final exports

### Real-ESRGAN 4x (Fallback)
- Per-frame upscaling
- Can introduce temporal inconsistency (shimmer between frames)
- Available in ComfyUI workflow (`Pulid.json` nodes 500-502)
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

## 6. Transition Generation

**Source**: `lip_sync.py`

### Wan FLF2V (First-Last Frame to Video)
- Generates smooth transition clips between two keyframes
- Input: start frame (end of shot N) + end frame (start of shot N+1)
- Duration: typically 1–2 seconds
- Creates seamless motion between cuts

### Mood-Aware Transitions
From `_build_transition_prompt()`:
- Dark → Light: "sunrise-like illumination"
- Light → Dark: "colors desaturating, shadows deepening"
- Same mood: "smooth continuous flow"
- Cross-mood: "cinematic match cut"

---

## 7. FFmpeg Assembly

**Source**: `phase_c_ffmpeg.py`

The final assembly stage combines all generated assets into a complete video.

### Per-Scene Assembly (`stitch_modules()`)
1. Concatenate shot video clips in order
2. Insert transition clips between shots
3. Apply per-clip visual effects via `normalize_clip()`

### normalize_clip() — Per-Clip Effect Application
Applies visual effects to individual clips:
- Color grading presets (warm_cinema, cinematic, etc.)
- Consistent codec normalization (h264, yuv420p)
- Resolution normalization (ensure all clips match)
- Frame rate normalization

### Master Assembly (`execute_master_ffmpeg_assembly()`)
Combines everything into the final export:

```
Input:
  - Video clips (per scene, stitched)
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

### Color Grading Presets
| Preset | Description |
|--------|-------------|
| `warm_cinema` | Warm tones, slight orange in highlights |
| `cinematic` | Standard film look, slightly desaturated |
| `cool_blue` | Cold tones, blue shadows |
| `high_contrast` | Crushed blacks, bright highlights |
| `film_noir` | High contrast B&W |
| `dreamy` | Low contrast, lifted blacks |

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
Scene Stitching (shots + transitions)
    ↓
Master Assembly (video + voice + BGM + foley + subtitles)
    ↓
Final Export (.mp4)
```
