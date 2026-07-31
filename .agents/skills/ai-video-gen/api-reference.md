# Video Generation API Reference

> **The catalog is the source of truth.** `domain/provider_catalog.py`'s `CATALOG`
> carries each engine's typed lifecycle / product-support / parameter facts plus a
> `(selectable, dispatchable, spendable)` flag triple. The prose here is the human
> rationale; where the two disagree, the catalog wins. See the note at the bottom
> on which claims are machine-checked and which are hand-maintained.

## Gemini Omni Flash — PRIMARY (`gemini_omni_native.py`)

**Primary video engine for every shot type** since the Google-first migration
(WS2): `target_api` is `GEMINI_OMNI` for portrait/medium/wide/action/landscape in
`workflow_selector.WORKFLOW_TEMPLATES`, with `VEO_NATIVE` as the shared first
fallback everywhere. Repaired and re-admitted 2026-07-30 (Slice 3) after a broken
spell — inline-base64 decoding, URI/Files-API polling+download, and
failed/empty-terminal handling were all fixed.

**Catalog**: `Maturity.PREVIEW`, `Lifecycle.ACTIVE`, `ProductSupport.LIMITED`,
flags `(selectable=True, dispatchable=True, spendable=True)`, `native_audio=True`.
LIMITED rather than SUPPORTED **because duration/resolution/audio are
prompt-inferred** — no structured kwargs, unlike every sibling native video engine.

**Auth**: `GOOGLE_API_KEY` **or** `GEMINI_API_KEY` (`settings.google_api_key or
settings.gemini_api_key`). Neither present → `EnvironmentError` at construction,
the engine is runtime-unavailable, and every cascade silently starts at
`VEO_NATIVE` instead — a missing key changes the primary engine for the whole run
rather than failing loud.

**SDK**: `google.genai` → `genai.Client(api_key=...)`. **Gemini Developer API
only** — Omni Flash has no Vertex AI surface today, so this client never attempts
a Vertex client (contrast `veo_native.py`'s Vertex-first / Gemini-fallback cascade).

**Model**: `"gemini-omni-flash-preview"`

**Image-to-Video** — a distinct SDK surface from Veo's `Operation`:
```python
interaction = client.interactions.create(
    model="gemini-omni-flash-preview",
    input=[{"type": "image", "data": <base64>, "mime_type": "image/jpeg"}, ...,
           {"type": "text", "text": prompt}],
    generation_config={"video_config": {
        "task": "reference_to_video" if reference_images else "image_to_video"}},
    response_format={"type": "video", "aspect_ratio": "16:9", "delivery": "uri"},
)
```
- `aspect_ratio`: `"16:9"` or `"9:16"` (threaded from `cinema.aspect.fal_aspect_ratio()`)
- `reference_images`: extra image paths for subject/character preservation — their
  presence is what flips the task to `reference_to_video`
- **Duration and resolution have no kwargs** — encode that intent in the prompt text

**Polling**: `interaction.status`, a string — *not* Veo's `operation.done`. 10s
intervals, max 120 polls = 1200s = 20 min, then `TimeoutError`. Terminal statuses:
`completed`, `failed`, `cancelled`, `incomplete`, `budget_exceeded`.

**Two delivery paths** — handle both:
1. **Inline**: `video.data` is base64 **TEXT** (`Optional[str]`), never raw bytes —
   `base64.b64decode` before writing. Tested with `is not None`, not truthiness, so
   an empty-but-present payload (`b""`) still counts as inline.
2. **URI**: `client.files.get(name=video.uri)` → poll until `state == "ACTIVE"`
   (`FAILED` classified explicitly) → download the returned `download_uri`, **not**
   the original `video.uri`.

**Publication is atomic**: written to a sibling temp file and `os.replace`d into
position, so a mid-write failure never leaves a partial file (mirrors `sora_native.py`).

**Billing (`on_billed`)**: a zero-arg callback fired **exactly once**, the moment
the interaction reaches `completed` — and **before** video retrieval. A provider
that finished the interaction is billed regardless of what happens next, so spend
is recorded even when retrieval then fails and the method returns `None`
(money-gate class 2026-07-11, extended to the native adapters in slice M2).
Exceptions from the callback are logged and swallowed — a broken accounting hook
must never abort an otherwise-good generation.

**Quota**: its own cooldown pair, **not** Veo's —
`_GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL` / `_gemini_omni_quota_blocked()`, TTL
`_GEMINI_OMNI_QUOTA_TTL_S = 600s` (10 min, Gemini Developer API Tier-1 rolling
spend window). Its own `budget_exceeded` status is matched alongside the usual
`429`/`quota`/`exhausted` strings.

**Cost**: `API_COST_USD["GEMINI_OMNI"] = 0.56` ($0.112/s × ~5s) — **web-verified,
not repo-measured**. Because duration is prompt-inferred and variable, this flat
per-clip figure risks the SEEDANCE under-billing pattern; an `ffprobe`
duration-probe is recommended before it is load-bearing at scale.

**Wisdom**:
- Returns `None` (never raises) on failure so the cascade falls through cleanly —
  both pre-billing (non-`completed` terminal status) and post-billing (completed,
  but empty output or failed retrieval)
- Native audio, like Veo — relevant to dialogue routing
- The prompt does more work here than on any other engine: it is the *only* channel
  for duration, resolution, and audio intent

---

## Kling Native — LEGACY kling-v1-6 (`kling_native.py`)

**⚠️ Fallback-only since 2026-07-11**, and since WS2 no longer even the first
fallback — the portrait/medium chain is now `GEMINI_OMNI → VEO_NATIVE → KLING_3_0
→ KLING_NATIVE`. KLING_3_0 is the fal Kling v3 Pro route
(`fal-ai/kling-video/v3/pro/image-to-video`) — best-ranked Kling (#11 AA i2v
arena), identity via `elements` (frontal + ≤3 reference images, addressed as
`@Element1`). This native client still sends v1.6-era params (`face_consistency`,
`image_reference`) that no v3-era doc lists; its `kling-v3` bump is deferred
pending a live-key param check (native docs geo-blocked HTTP 446).

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
- (v1.6-era) subject binding + face_consistency was the strongest identity lock; on v3 the identity mechanism is `elements` on the fal route — see the header note
- Tasks typically complete in 30–90s after submission

---

## Sora 2 Native (`sora_native.py`)

**⚠️ Two different Sora entries — do not confuse them:**

| Key | What it is | State |
|-----|-----------|-------|
| `SORA_NATIVE` | OpenAI Videos API direct (`sora_native.py`) | **Deprecated but live** — date-gated fallback through the 2026-09-24 sunset, then non-dispatchable automatically. Still the 3rd fallback in the action cascade |
| `SORA_2` | The FAL-proxied route | **Fully RETIRED** — `Lifecycle.RETIRED` + `ProductSupport.UNSUPPORTED`, flags `(False, False, False)`: not selectable, not dispatchable, not spendable. **Do not route new work to it, in code or in prompts** |

OpenAI retires Sora 2 and the Videos API on **2026-09-24**. The action primary
moved to Seedance 2.0 (fal) on 2026-07-11 and then to `GEMINI_OMNI` in WS2;
`SORA_NATIVE` now sits third in the action fallback chain.

**Auth**: OpenAI API key via `OPENAI_API_KEY`

**SDK**: `openai.OpenAI` client

**Image-to-Video**:
- Model: `"sora-2"`
- Duration: **must be exactly** `4`, `8`, `12`, `16`, or `20` (integer seconds) — invalid values default to 4
- Resolution: `"480p"`, `"720p"`, or `"1080p"`
- Input images auto-resized to the resolved resolution (1280x720 landscape OR 720x1280 portrait, after sora-2 clamps to 720p) (LANCZOS, JPEG quality 90)
- Uses `client.videos.create_and_poll()` — SDK handles polling automatically
- Download: `client.videos.download_content(video.id)` with streaming iter_bytes

**Wisdom**:
- **Best motion physics** of all APIs — cloth simulation, body momentum, weight-aware movement
- No explicit character binding — relies on start frame quality + prompt engineering
- Duration lock is strict: validate before submission
- Natural film grain is a strength — don't fight it with prompts

---

## Veo 3.1 Native (`veo_native.py`)

**Shared first fallback for every shot type** since WS2 — when `GEMINI_OMNI` is
unavailable or fails, this is what actually runs. Also native-audio.

**Auth**: Google Generative AI SDK via `GOOGLE_API_KEY`

**SDK**: `google.genai` with `types.Image.from_file(location=path)`

**Image-to-Video**:
- Model: `"veo-3.1-generate-preview"` (Gemini API key backend) or `"veo-3.1-generate-001"` (Vertex AI backend — preferred, supports native audio)
- Duration: `"4s"`, `"6s"`, or `"8s"` (string with 's' suffix); `"5s"` is server-rejected (INVALID_ARGUMENT) and the code clamps to nearest valid value (5 → 6) via `_clamp_image_to_video_duration`
- Resolution: `"720p"` or `"1080p"`
- Aspect ratio: `"16:9"` (hardcoded)
- `person_generation`: `"allow_adult"`
- `reference_images`: Parameter accepted for interface compatibility, but NOT applied on the image-to-video path — server rejects them when a start image is provided ("Image and reference images cannot be both set.")
- `generate_audio`: Boolean — native synced audio generation

**First + Last Frame Control** (unique to Veo):
- Veo smoothly interpolates between start and end compositions via keyframe-controlled generation
- Deterministic endpoints — ideal for shot-to-shot transitions
- Note: a dedicated `generate_video_with_frames()` helper does not exist; keyframe control is achieved through the start image and prompt composition

**Polling**: Manual 10s intervals, logging every 60s. No explicit timeout cap.

**Wisdom**:
- **Cheapest video engine** at $0.30 per ~5s clip — cheaper than LTX, contrary to older docs
- First+last frame control is unmatched by other APIs — use for transitions
- Reference images (up to 3) lock character appearance without explicit face flag
- `"6s"` is the sweet spot for cinematic pacing
- Native audio is useful for dialogue/narration scenes
- Quota issues occur — pipeline tracks via TTL timestamp `_VEO_QUOTA_EXHAUSTED_UNTIL` (float, 0 = no cooldown), checked via `_veo_quota_blocked()`, auto-expires after `_VEO_QUOTA_TTL_S = 1800s` (30 min). **Distinct from Gemini Omni's cooldown** — never reuse one for the other

---

## LTX Video 2.3 (`ltx_native.py`)

**Auth**: Hybrid mode
- Primary: `LTX_API_KEY` → native API at `https://api.ltx.video/v1`
- Fallback: `FAL_KEY` → FAL proxy at `fal-ai/ltx-2.3/image-to-video` (`FAL_MODEL_ID`; bumped 2026-07-11 from `fal-ai/ltx-2`; fast tier `.../fast` unlocks 12-20s at 25fps/1080p; NO camera_motion param on fal — prompt-folded; generate_audio=False, audio carries ~$0.02/s surcharge)
- Auto-detects at init; tries native first

**Image-to-Video (native)**:
- Model: `"ltx-2-3-pro"`
- **Duration: exactly 6, 8, or 10 seconds** (`DURATION_SECONDS`; default 6). Anything else **raises before any network call** — both the native endpoint and the FAL proxy share this enum. Snap first with `LTXVideoAPI.nearest_supported_duration()` (snap-up bias). `phase_c_ffmpeg._LTX_DURATION_ENUM_S` mirrors it as a literal, drift-pinned by `tests/unit/test_ltx_native.py::test_phase_c_ffmpeg_duration_enum_matches_ltx_native`
- Resolution: `"480p"` (854x480), `"720p"`/`"1080p"` (1920x1080), `"4k"` (3840x2160). The fal resolution enum is `1080p`/`1440p`/`2160p`
- **Camera motion** parameter (native only): `dolly_in`, `dolly_out`, `jib_up`, `jib_down`, `pan_left`, `pan_right`, `tilt_up`, `tilt_down`, `zoom_in`, `zoom_out`, `crane_up`, `crane_down`, `truck_left`, `truck_right`, `static`
- **No polling** — returns MP4 bytes directly (fastest response of all APIs)

**Keyframe Transition** (like Veo):
- `generate_transition(start_frame, end_frame, prompt, duration)`
- Smooth interpolation between two compositions

**4K Support**:
- Pass `resolution="4k"` to `generate_video()` — no separate `generate_4k()` convenience wrapper exists

**Wisdom**:
- **4K support** is unique — no other API generates at 3840x2160
- Second-cheapest at $0.36 per clip, but that is a **6s floor estimate** while the dispatcher's default is 8s — it under-records ~33% on default shots unless the caller passes `record_api_call(duration_seconds=...)`
- Camera motion parameters add cinematic movement without prompt engineering — but only on the native route; on fal they must be folded into the prompt
- Direct byte stream = no polling overhead = fastest turnaround
- True 720p not natively supported — mapped to 1080p internally
- Best for: wide/landscape/environment shots (no face distortion at distance), where it remains the 2nd fallback behind Veo
- Keyframe transition shared with Veo — use for cut-to-cut scenes

---

## Runway Gen-4 (`phase_c_ffmpeg.py`)

**Auth**: RunwayML SDK via `RUNWAYML_API_SECRET`

**Image-to-Video**:
- Model: `"gen4_turbo"` (primary); a secondary path uses `"gen3a_turbo"`
- Duration: 10 seconds
- Ratio: `"16:9"`
- Image input: base64 data URI (`data:image/jpeg;base64,...`)
- Style lock: up to **3 reference images** for style consistency
- Poll: `client.tasks.retrieve(id=task.id)` (keyword arg); gen4_turbo block polls at 10s intervals

**Wisdom**:
- Strong style lock with reference images
- Good balance between face consistency and scene quality
- 10s fixed duration — no variable length
- Secondary fallback in most cascade chains

---

## Performance Capture (`performance/` package)

A **separate axis** from the base video generation above: talking-head /
driving-video retargeting, selected by `domain/performance.py`'s
`route_performance_engine()` and dispatched by `performance/_router.py`. Engine
names are `ACT_ONE`, `LIVE_PORTRAIT`, `VIGGLE`, `SKIP`; per-provider concurrency
caps live in `_router._SEMAPHORE_LIMITS` (Act-One 1, LivePortrait 2, Viggle 1).

### Runway Act-Two (`performance/act_two.py`) — migrated from Act-One

The routing engine name stays `ENGINE_ACT_ONE` and the catalog key stays
`RUNWAY_ACT_ONE` for backward-compat with existing routing/cost data, but the
adapter dispatches the live **`act_two`** model. The old `RUNWAY_ACT_ONE` catalog
entry is `Lifecycle.RETIRED` + `ProductSupport.KNOWN_BROKEN`, flags
`(False, False, False)` — deliberately *not* renamed, because the key must keep
mirroring `domain.scene_decomposer.API_REGISTRY`'s key set (pinned by
`test_catalog_exactly_covers_legacy_registry_plus_fal_svd_mutation_pin`).

Verified against the installed `runwayml` SDK v4.14.0 (2026-07-30, slice 5b):
- `model` is typed `Literal["act_two"]` — **"act_one" is no longer a constructible
  request** on `character_performance.create()`
- `reference` MUST be `{"type": "video", "uri": <url>}` — a 3–30s video of a person
  performing. **There is no audio-reference mode.** Act-One could synthesize a
  performance from dialogue audio alone; Act-Two cannot. Callers holding only TTS
  audio and no reference video get a clear logged failure rather than a malformed
  request
- **`.create()` takes no `duration`** — output length is inferred from the reference
  video. `duration_s` survives as a Python-side keyword used *only* for the $/s cost
  estimate; it is never forwarded to Runway
- `uri` is documented as "A HTTPS URL", so this adapter encodes local files as RFC
  2397 `data:<mime>;base64,...` URIs rather than passing filesystem paths through
- Offered but **not yet wired**: `body_control` (bool), `content_moderation`,
  `expression_intensity` (1–5 int), `seed`

**API surface**: `POST https://api.dev.runwayml.com/v1/character_performance`,
polled via `GET /v1/tasks/{id}`. Poll interval 3s. Auth reuses
`RUNWAYML_API_SECRET`. **Cost**: ~$0.05/s (`API_COST_USD["ACT_ONE"] = 0.25` per ~5s).

### LivePortrait (`performance/live_portrait.py`)

ComfyUI-pod based, the cheap opt-in path — `API_COST_USD["LIVE_PORTRAIT"] = 0.04`
(amortized GPU cost). Chosen over Act-Two only when the project explicitly sets
`performance_budget_mode` to `budget`/`cheap`, so the cheap path is opt-in rather
than a silent regression. **Requires a driving video**; dispatch returns `None` if
none is supplied.

### Viggle (`performance/viggle.py`) — ⚠️ KNOWN_BROKEN, CONTAINED

Catalog entry `VIGGLE` is `ProductSupport.KNOWN_BROKEN`, flags `(False, False, False)`.
Viggle *does* publish an official developer API (docs.viggle.ai, verified
2026-07-31) — the adapter provably mismatches it:

| Adapter sends | Real contract |
|---|---|
| `https://api.viggle.ai/v1/motion-transfer` | `https://apis.viggle.ai/v1/renders` |
| `GET https://api.viggle.ai/v1/jobs/{job_id}` | `GET /v1/renders/{id}` |
| `files={"character_image", "motion_video"}` | `{"image"/"image_url", "motion_video"/"motion_video_url"}` |
| `background_mode: white\|green\|transparent` | `background_mode: original\|solid\|transparent` (+ `bg_color`) |

Wrong subdomain, wrong path, wrong polling shape, and two of three field names
differ — a broken integration, not a credentials gap.

**Where the containment actually lives** — be precise about this:
- ✅ **Routing layer**: `route_performance_engine()` returns `ENGINE_SKIP` for the
  action-without-dialogue branch that used to return `ENGINE_VIGGLE`
  (`domain/performance.py`, Slice 6c 2026-07-31). Auto-routing can no longer select
  it, so in practice Viggle is never dispatched. Action motion comes from the video
  engines natively instead
- ❌ **Dispatch layer**: `performance/_router.py` is **not** catalog-gated — it
  imports nothing from `domain.provider_catalog`, so if `ENGINE_VIGGLE` reaches
  `dispatch()` by any other route it still calls
  `performance.viggle.generate_viggle_performance()` unconditionally

The KNOWN_BROKEN row therefore fails closed for anything that consults
`effective_policy` / `runtime_availability` (mirroring `RUNWAY_ACT_ONE`), but
wiring the Mode-A dispatcher itself to consult the catalog is a **dedicated repair
slice, not yet landed**. The routing branch returns `ENGINE_VIGGLE` again when it does.

---

## API Capabilities Matrix

| Feature | **Gemini Omni** | Kling 3.0 | Sora 2 | Veo 3.1 | LTX 2.3 | Runway Gen-4 Turbo |
|---------|-----------------|-----------|--------|---------|---------|-------------|
| Role (post-WS2) | **PRIMARY (all types)** | Fallback | Fallback (action, pre-sunset) | **1st fallback (all types)** | Fallback | Fallback |
| Character Binding | Reference images (`reference_to_video`) | `elements` (≤3 refs) | Prompt only | References (3, t2v path only) | Prompt only | Style lock (3) |
| Face Consistency Flag | No | No (v1.6 only) | No | No | No | No |
| Duration | **Prompt-inferred (no kwarg)** | 5s optimal | 4,8,12,16,20 | 4s,6s,8s | 6/8/10 (enforced) | 10s fixed |
| Max Resolution | Prompt-inferred | 1080p | 1080p | 1080p | **4K** | 1080p |
| Aspect Ratio | 16:9 / 9:16 | 16:9 / 9:16 | 16:9 / 9:16 | 16:9 (hardcoded) | 16:9 | 16:9 |
| Storyboard | No | 6 shots/15s | No | No | No | No |
| First+Last Frame | No | No | No | Yes | Yes | No |
| Native Audio | **Yes** | No | No | **Yes** | No (fal: off by contract) | No |
| Camera Motion Params | No | No | No | No | **15 types** (native only) | No |
| Polling Required | Yes (10s, 20min cap) | Yes (backoff) | Yes (SDK auto) | Yes (10s manual) | **No (direct)** | Yes (10s) |
| Est. USD / ~5s | 0.56 | 0.56 | 0.80 (`SORA_NATIVE`) | **0.30** | 0.36 (6s floor) | 0.50 |
| Best For | **Everything — arena #1** | Portraits/face | Action/motion | **Cheap + transitions** | Landscape/4K | Style lock |

---

## FAL Proxy Fallbacks

When native APIs fail, these FAL endpoints provide redundancy:

| API | FAL Model ID | Notes |
|-----|-------------|-------|
| Kling | `fal-ai/kling-video/v3/pro/image-to-video` | KLING_3_0 engine; `elements` identity, $0.112/s audio-off (parity with native pricing) |
| ~~Sora~~ | ~~`fal-ai/sora-2/image-to-video`~~ | **RETIRED — `SORA_2` is UNSUPPORTED, not dispatchable. Do not route here.** Use `SORA_NATIVE` until the 2026-09-24 sunset |
| Veo | `fal-ai/veo3.1/reference-to-video` | Reference images supported |
| LTX | `fal-ai/ltx-2.3/image-to-video` | `FAL_MODEL_ID`; duration enum {6,8,10}s; no camera_motion param (prompt-folded); audio off by contract |
| Seedance | `bytedance/seedance-2.0/image-to-video` | 4-15s, 480p-4k, 9:16 OK; `.../reference-to-video` takes ≤9 ref images ($0.3024/s @720p standard). Per-shot-type durations in `SEEDANCE_DURATIONS` |

All FAL proxies use `FAL_KEY` and `fal_client.subscribe()` with polling.

---

## Environment Variables

```bash
GOOGLE_API_KEY         # Gemini Omni (PRIMARY) + Veo 3.1
GEMINI_API_KEY         # Gemini Omni alternative — either this or GOOGLE_API_KEY
KLING_ACCESS_KEY       # Kling native JWT
KLING_SECRET_KEY       # Kling native JWT
OPENAI_API_KEY         # Sora 2 native (also used for scene decomposition)
LTX_API_KEY            # LTX native (optional if FAL_KEY set)
RUNWAYML_API_SECRET    # Runway Gen-4 + Act-Two performance capture
FAL_KEY                # FAL proxy fallbacks + FLUX image gen + lip sync + upscale
ELEVENLABS_API_KEY     # Voiceover (Phase B)
ANTHROPIC_API_KEY      # Chief Director QA (Claude)
```

Without `GOOGLE_API_KEY` **or** `GEMINI_API_KEY` the primary engine for every shot
type is unavailable and the pipeline silently runs on `VEO_NATIVE` — which needs
`GOOGLE_API_KEY` too. Verify key presence before blaming routing.

---

## Which claims here are machine-checked

**Today: none of them.** Every fact on this page is hand-maintained prose that can
rot silently — API shapes, polling intervals, parameter lists, cost figures, and
all rationale alike. Re-read the adapter before trusting a specific parameter.

`scripts/check_provider_catalog_claims.py` (Slice 14a, currently on
`unification/waves-3-8` — **not yet on every branch**) re-derives a hand-picked
fact set from `domain/provider_catalog.py`'s `CATALOG` and fails loud on drift:
GEMINI_OMNI routable, SORA_2 fully retired, RUNWAY_ACT_ONE retired, VIGGLE
KNOWN_BROKEN, and the LTX `{6, 8, 10}` duration enum. Its docstring currently
scopes itself to `config/prompts/pipeline_context.md` and the two `SKILL.md`
copies. **This file and `shot-routing.md` now assert the same five facts**, so
when 14a lands here that scope note should be widened to name them — otherwise
these two files carry checked-looking claims that nothing actually checks.
