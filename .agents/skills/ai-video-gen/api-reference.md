# Video Generation API Reference

## Kling 3.0 Native (`kling_native.py`)

**Auth**: JWT (HS256) via `KLING_ACCESS_KEY` + `KLING_SECRET_KEY`. Tokens cached 30 min, auto-refresh at <5 min remaining.

**Base URL**: `https://api.klingai.com`

**Image-to-Video**:
- Model: `kling-v1-6`, Mode: `pro`
- Duration: `"5"` (string, 5 seconds optimal)
- CFG Scale: 0.5
- `face_consistency`: Boolean — set `True` for portrait/medium shots
- `image_references`: List of additional character angle images for subject binding
- Negative prompt supported

**Storyboard Mode** (unique to Kling):
- Up to **6 shots** in unified latent space
- Max **15 seconds** total duration
- Per-shot minimum: 1 second
- `multi_prompt`: Array of `{prompt, duration}` dicts
- Face consistency enabled by default
- Best for: multi-angle character sequences maintaining identity

**Polling**: Exponential backoff — 3s, 5s, 8s, 12s, 15s (capped). Timeout: 600s.

**Wisdom**:
- 5s is the sweet spot — longer durations increase temporal drift
- Always use `pro` mode for character content
- 2–3 additional reference angles (profile, 3/4 view) significantly improve consistency
- Subject binding + face_consistency together = strongest identity lock of all APIs
- Tasks typically complete in 30–90s after submission

---

## Sora 2 Native (`sora_native.py`)

**Auth**: OpenAI API key via `OPENAI_API_KEY`

**SDK**: `openai.OpenAI` client

**Image-to-Video**:
- Model: `"sora-2"`
- Duration: **must be exactly** `4`, `8`, `12`, `16`, or `20` (integer seconds) — invalid values default to 4
- Resolution: `"480p"`, `"720p"`, or `"1080p"`
- Input images auto-resized to **1280x720** (LANCZOS, JPEG quality 90)
- Uses `client.videos.create_and_poll()` — SDK handles polling automatically
- Download: `client.videos.download_content(video.id)` with streaming iter_bytes

**Sunset**: September 2026 (announced)

**Wisdom**:
- **Best motion physics** of all APIs — cloth simulation, body momentum, weight-aware movement
- Primary choice for action/dynamic scenes
- No explicit character binding — relies on start frame quality + prompt engineering
- Duration lock is strict: validate before submission
- Natural film grain is a strength — don't fight it with prompts

---

## Veo 3.1 Native (`veo_native.py`)

**Auth**: Google Generative AI SDK via `GOOGLE_API_KEY`

**SDK**: `google.genai` with `types.Image.from_file(location=path)`

**Image-to-Video**:
- Model: `"veo-3.1-generate-preview"`
- Duration: `"5s"`, `"6s"`, or `"8s"` (string with 's' suffix)
- Resolution: `"720p"` or `"1080p"`
- Aspect ratio: `"16:9"` (hardcoded)
- `person_generation`: `"allow_adult"`
- `reference_images`: Up to **3** character preservation images
- `generate_audio`: Boolean — native synced audio generation

**First + Last Frame Control** (unique to Veo):
- `generate_video_with_frames(first_frame, last_frame, prompt, duration)`
- Veo smoothly interpolates between start and end compositions
- Deterministic endpoints — ideal for shot-to-shot transitions

**Polling**: Manual 10s intervals, logging every 60s. No explicit timeout cap.

**Wisdom**:
- First+last frame control is unmatched by other APIs — use for transitions
- Reference images (up to 3) lock character appearance without explicit face flag
- `"6s"` is the sweet spot for cinematic pacing
- Native audio is useful for dialogue/narration scenes
- Best for landscape/environment shots and keyframe-controlled transitions
- Quota issues occur — pipeline tracks `_veo_quota_exhausted` globally

---

## LTX Video 2.3 (`ltx_native.py`)

**Auth**: Hybrid mode
- Primary: `LTX_API_KEY` → native API at `https://api.ltx.video/v1`
- Fallback: `FAL_KEY` → FAL proxy at `fal-ai/ltx-2/image-to-video`
- Auto-detects at init; tries native first

**Image-to-Video (native)**:
- Model: `"ltx-2-3-pro"`
- Duration: integer seconds (converted to frames: `duration * 24`)
- Resolution: `"480p"` (854x480), `"720p"`/`"1080p"` (1920x1080), `"4k"` (3840x2160)
- **Camera motion** parameter: `dolly_in`, `dolly_out`, `jib_up`, `jib_down`, `pan_left`, `pan_right`, `tilt_up`, `tilt_down`, `zoom_in`, `zoom_out`, `crane_up`, `crane_down`, `truck_left`, `truck_right`, `static`
- **No polling** — returns MP4 bytes directly (fastest response of all APIs)

**Keyframe Transition** (like Veo):
- `generate_transition(start_frame, end_frame, prompt, duration)`
- Smooth interpolation between two compositions

**4K Convenience**:
- `generate_4k(image_path, prompt)` — auto-selects 4K resolution, 4s duration

**Wisdom**:
- **Cheapest** cost per video across all APIs
- **4K support** is unique — no other API generates at 3840x2160
- Camera motion parameters add cinematic movement without prompt engineering
- Direct byte stream = no polling overhead = fastest turnaround
- True 720p not natively supported — mapped to 1080p internally
- Best for: wide/landscape/environment shots (no face distortion at distance)
- Keyframe transition shared with Veo — use for cut-to-cut scenes

---

## Runway Gen-4 (`phase_c_ffmpeg.py`)

**Auth**: RunwayML SDK via `RUNWAYML_API_SECRET`

**Image-to-Video**:
- Model: `"gen4"`
- Duration: 10 seconds
- Ratio: `"16:9"`
- Image input: base64 data URI (`data:image/jpeg;base64,...`)
- Style lock: up to **3 reference images** for style consistency
- Poll: `client.tasks.retrieve(task_id)` with 5s intervals

**Wisdom**:
- Strong style lock with reference images
- Good balance between face consistency and scene quality
- 10s fixed duration — no variable length
- Secondary fallback in most cascade chains

---

## API Capabilities Matrix

| Feature | Kling 3.0 | Sora 2 | Veo 3.1 | LTX 2.3 | Runway Gen-4 |
|---------|-----------|--------|---------|---------|-------------|
| Character Binding | Subject binding | Prompt only | References (3) | Prompt only | Style lock (3) |
| Face Consistency Flag | Boolean | No | No | No | No |
| Duration | 5s optimal | 4,8,12,16,20 | 5s,6s,8s | Flexible | 10s fixed |
| Max Resolution | 1080p | 1080p | 1080p | **4K** | 1080p |
| Storyboard | 6 shots/15s | No | No | No | No |
| First+Last Frame | No | No | Yes | Yes | No |
| Native Audio | No | No | Yes | No | No |
| Camera Motion Params | No | No | No | **15 types** | No |
| Polling Required | Yes (backoff) | Yes (SDK auto) | Yes (10s manual) | **No (direct)** | Yes (5s) |
| Relative Cost | $$ | $$$$ | $$$ | **$** | $$$ |
| Best For | **Portraits/face** | **Action/motion** | **Transitions** | **Landscape/4K** | **Style lock** |

---

## FAL Proxy Fallbacks

When native APIs fail, these FAL endpoints provide redundancy:

| API | FAL Model ID | Notes |
|-----|-------------|-------|
| Kling | `fal-ai/kling-video/v3/pro/image-to-video` | Subject binding supported |
| Sora | `fal-ai/openai/sora-2/image-to-video` | 25s continuous generation |
| Veo | `fal-ai/google/veo/image-to-video` | Reference images supported |

All FAL proxies use `FAL_KEY` environment variable and `fal_client.subscribe()` with polling.

---

## Environment Variables

```bash
KLING_ACCESS_KEY       # Kling native JWT
KLING_SECRET_KEY       # Kling native JWT
OPENAI_API_KEY         # Sora 2 (also used for scene decomposition)
GOOGLE_API_KEY         # Veo 3.1
LTX_API_KEY            # LTX native (optional if FAL_KEY set)
RUNWAYML_API_SECRET    # Runway Gen-4
FAL_KEY                # FAL proxy fallbacks + FLUX image gen + lip sync + upscale
ELEVENLABS_API_KEY     # Voiceover (Phase B)
ANTHROPIC_API_KEY      # Chief Director QA (Claude)
```
