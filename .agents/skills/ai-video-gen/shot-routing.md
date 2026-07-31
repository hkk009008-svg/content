# Shot Routing & Workflow Parameters

## Shot Type Classification

Classification from `workflow_selector.py:classify_shot_type()`. Priority order:

1. **No characters in frame** → `landscape`
2. **Check `[SHOT]` section** of structured prompt for keywords
3. **Search full prompt + camera field** for keywords
4. **Default**: `medium` (safest fallback)

### Keywords by Type

| Type | Keywords |
|------|----------|
| **portrait** | close-up, closeup, portrait, ecu, extreme close, 85mm, macro, headshot, face shot, tight shot |
| **action** | tracking, crane, dolly, rapid, chase, running, action, dynamic, handheld, steadicam |
| **wide** | wide shot, wide angle, establishing, 24mm, 16mm, full shot, long shot, master shot, extreme wide |
| **landscape** | landscape, aerial, drone, skyline, panoramic, environment, scenery, no character |
| **medium** | medium, 50mm, mid-shot, waist, hip, american shot, cowboy shot, two-shot |

---

## Complete Workflow Templates

Parameters from `WORKFLOW_TEMPLATES` in `workflow_selector.py`:

**Two things changed pipeline-wide — read these before using any block below:**

1. **`target_api` is `GEMINI_OMNI` for every shot type** (Google-first migration,
   WS2 — Gemini Omni Flash is arena #1), with `VEO_NATIVE` as the shared first
   fallback everywhere. The engines that used to be primaries (KLING_3_0 for
   portrait/medium, LTX for wide/landscape, SEEDANCE for action) are now
   *fallbacks* and keep their old rationale in that role.
2. **`pulid_start_at` is `0.0` across the production tier.** The prior
   SDXL-era values (portrait 0.20 / medium 0.25 / wide 0.35 / action 0.30) were
   a structural no-op on FLUX; fixed 2026-06-13 (DECISIONS.md ADR-025,
   validated OFF 0.6205 → ON 0.8779).

### Portrait (Close-up face focus)
```
pulid_weight:              1.0    # Maximum face-lock
pulid_start_at:            0.0    # FLUX: bind from step 0 (coarse-identity window)
pulid_end_at:              1.0
guidance:                  3.5    # FLUX sweet spot
steps:                     25     # Finer skin texture, pore detail, iris sharpness
sampler:                   dpmpp_2m
scheduler:                 sgm_uniform
pag_scale:                 3.0    # Sharpen face details without oversaturation
controlnet_depth_strength: 0.35
ip_adapter_weight:         0.25   # Minimal style transfer
denoise_default:           0.25   # Tighter temporal consistency
target_api:                GEMINI_OMNI  # Google-first primary (WS2); native audio
video_fallbacks:           ['VEO_NATIVE', 'KLING_3_0', 'KLING_NATIVE', 'RUNWAY_GEN4', 'SEEDANCE']
                           # KLING_3_0 = fal Kling v3 Pro (#11 AA i2v arena), `elements` identity binding
                           # KLING_NATIVE = legacy kling-v1-6, proven identity fallback
```

### Medium (Waist-up balanced)
```
pulid_weight:              0.9
pulid_start_at:            0.0    # FLUX: bind from step 0
pulid_end_at:              1.0
guidance:                  3.5
steps:                     20
sampler:                   dpmpp_2m
scheduler:                 sgm_uniform
pag_scale:                 3.0    # Enhance mid-range detail (clothing, background)
controlnet_depth_strength: 0.40
ip_adapter_weight:         0.30
denoise_default:           0.35
target_api:                GEMINI_OMNI  # Google-first primary (WS2)
video_fallbacks:           ['VEO_NATIVE', 'KLING_3_0', 'KLING_NATIVE', 'RUNWAY_GEN4', 'SEEDANCE', 'LTX']
```

### Wide (Establishing shot, environment-primary)
```
pulid_weight:              0.65   # Lower — environment matters more
pulid_start_at:            0.0    # FLUX: bind from step 0
pulid_end_at:              0.9    # 90% — final 10% for environment polish
guidance:                  3.0
steps:                     20
sampler:                   dpmpp_2m
scheduler:                 sgm_uniform
pag_scale:                 2.5    # Lower — avoid over-sharpening
controlnet_depth_strength: 0.50   # Strongest spatial lock
ip_adapter_weight:         0.35
denoise_default:           0.45
target_api:                GEMINI_OMNI  # Google-first primary (WS2)
video_fallbacks:           ['VEO_NATIVE', 'LTX', 'KLING_3_0', 'RUNWAY_GEN4']
                           # LTX (4K, 3D camera, depth-aware, cheapest) demoted from primary to 2nd fallback
```

### Action (Dynamic movement)
```
pulid_weight:              0.8    # Slightly reduced — action poses stress face
pulid_start_at:            0.0    # FLUX: bind from step 0
pulid_end_at:              1.0
guidance:                  3.5
steps:                     20
sampler:                   dpmpp_2m
scheduler:                 sgm_uniform
pag_scale:                 2.0    # Lower — motion needs softness not crispness
controlnet_depth_strength: 0.30   # Light spatial guidance
ip_adapter_weight:         0.25
denoise_default:           0.40
target_api:                GEMINI_OMNI  # Google-first primary (WS2)
video_fallbacks:           ['VEO_NATIVE', 'SEEDANCE', 'SORA_NATIVE', 'KLING_3_0', 'RUNWAY_GEN4', 'LTX']
                           # SEEDANCE (#1 AA i2v arena 2026-07; multi-ref ≤9 images binds multi-character) demoted to 2nd fallback
                           # SORA_NATIVE stays 3rd until the 2026-09-24 sunset, then errors fast and cascades on
```

### Landscape (Pure environment, no characters)
```
pulid_weight:              0.0    # NO face-lock
pulid_start_at:            0.0
pulid_end_at:              0.0
guidance:                  4.0    # Higher — sharper architectural detail
steps:                     25     # Maximum — environment benefits most
sampler:                   dpmpp_2m
scheduler:                 sgm_uniform
pag_scale:                 3.5    # Maximum detail sharpening
controlnet_depth_strength: 0.55   # Strong spatial lock
ip_adapter_weight:         0.40   # Max style transfer
denoise_default:           0.55
target_api:                GEMINI_OMNI  # Google-first primary (WS2)
video_fallbacks:           ['VEO_NATIVE', 'LTX', 'KLING_3_0']
                           # LTX (4K, no face, cheapest, best environments) demoted from primary
```

**Dialogue shots** are not a ComfyUI template — they borrow portrait/medium for
image gen, then route to a video API with native lipsync. The video cascade is
`GEMINI_OMNI → VEO_NATIVE → Kling Lip Sync → Omnihuman`, data-driven via
`PURPOSE_API_RANKING` / `_resolve_dialogue_routing` in
`domain/scene_decomposer.py`.

**Runtime availability gate**: `GEMINI_OMNI` needs `GOOGLE_API_KEY` or
`GEMINI_API_KEY`. Without either it is runtime-unavailable and every cascade
above effectively starts at `VEO_NATIVE` — so a missing key silently changes
the primary engine for the whole run rather than failing loud
(`domain/video_engine_policy.py`, `domain/provider_catalog.py`).

---

## Cascade Retry Logic

From `phase_c_ffmpeg.py:generate_ai_video()`:

1. Try primary API (from `target_api`)
2. On failure → try next in `video_fallbacks` list
3. If ALL APIs exhausted → wait **30 seconds** (`time.sleep(30)`) for quota refresh
4. Retry up to **1 extra cascade cycle** by default (`MAX_CASCADE_RETRIES = 1`), raisable via the `cascade_retry_limit` UI knob
5. Track `attempted_apis` set to prevent retry loops
6. After max retries exceeded → return None (hard failure)

**Error handling**: Each API wrapped in try/catch. On exception → `try_next_api()`. Detailed logging per attempt.

**Global quota flags** (TTL timestamps, not boolean flags — each engine has its
own pair; do NOT reuse one engine's cooldown for another):

| Engine | Timestamp | Checked via | TTL |
|--------|-----------|-------------|-----|
| Veo | `_VEO_QUOTA_EXHAUSTED_UNTIL` | `_veo_quota_blocked()` | `_VEO_QUOTA_TTL_S` = 1800s (30 min) |
| Gemini Omni | `_GEMINI_OMNI_QUOTA_EXHAUSTED_UNTIL` | `_gemini_omni_quota_blocked()` | `_GEMINI_OMNI_QUOTA_TTL_S` = 600s (10 min, Gemini Developer API Tier-1 rolling spend window) |

Gemini Omni's quota-exhaustion vocabulary includes its own `budget_exceeded`
status alongside the usual `429`/`quota`/`exhausted` string matches
(`phase_c_ffmpeg.py:38-43`, `gemini_omni_native.py`).

---

## Adaptive PuLID Feedback Loop

From `workflow_selector.py:get_adaptive_pulid_weight()`:

```
base_weight = WORKFLOW_TEMPLATES[shot_type]["pulid_weight"]
rolling_stats = identity_validator.get_rolling_stats(character_id)  # window=10 is the default; not passed explicitly at call sites

if rolling_stats.success_rate < 0.5:
    # Identity failing hard → boost PuLID
    delta = +0.10
elif rolling_stats.success_rate < 0.8:
    # Identity below target → moderate boost
    delta = +0.05
elif rolling_stats.success_rate == 1.0 and rolling_stats.mean_similarity > 0.80:
    # Identity great → allow more creativity
    delta = -0.05
else:
    delta = 0.0

# SMART: Don't boost for failures caused by face angle or small face
if rolling_stats.common_failure in [FACE_ANGLE_EXTREME, SMALL_FACE_REGION]:
    delta = 0.0

adjusted = clamp(base_weight + delta, 0.0, 1.0)
```

This creates a feedback loop: poor identity scores automatically tighten PuLID on subsequent generations.

---

## Cost Optimization

**Cheapest to most expensive**, per ~5s clip. These are the committed estimates
in `cost_tracker.py`'s `API_COST_USD` — not a hand-maintained `$`-tier guess:

| Engine | Est. USD / ~5s | Note |
|--------|---------------|------|
| VEO_NATIVE | 0.30 | cheapest video engine — and the shared first fallback everywhere |
| LTX | 0.36 | **floor estimate**: fal ltx-2.3 $0.06/s audio-off @1080p × 6s *minimum*. The dispatcher's default is 8s, so this flat figure under-records ~33% on default shots |
| KLING_NATIVE | 0.50 | legacy v1.6; pre-v3 estimate |
| RUNWAY_GEN4 | 0.50 | 10s fixed |
| KLING_3_0 | 0.56 | fal kling-video/v3/pro $0.112/s audio-off |
| GEMINI_OMNI | 0.56 | $0.112/s × ~5s — **web-verified, not repo-measured** (see caveat below) |
| SORA_NATIVE | 0.80 | best motion; retires 2026-09-24 |
| SEEDANCE | 1.51 | $0.3024/s @720p standard; #1 arena quality, multi-reference |

Note this inverts a long-standing assumption in older docs: **Veo is cheaper
than LTX**, not more expensive.

⚠️ **The GEMINI_OMNI figure is the weakest number in this table.** Duration is
prompt-inferred on that API (no structured duration kwarg), so a flat per-clip
estimate risks the exact under-billing pattern SEEDANCE had to be fixed for on
2026-07-11. A duration-probe (`ffprobe` on the downloaded mp4) is recommended
before this figure is load-bearing at scale. Whenever a caller supplies the
actual dispatched duration, `record_api_call(duration_seconds=...)` computes the
true per-second cost from `API_COST_PER_SECOND_USD` instead of these flat
figures — prefer that path.

**Cost strategy**: cost is no longer what picks the primary — `GEMINI_OMNI` is
primary everywhere on quality grounds (arena #1), and the cascade order, not
price, decides what runs. Price matters when you deliberately override
`target_api` or when the Google engines are unavailable: LTX still earns its
slot on wide/landscape (4K, no face to distort at distance), and Seedance is
worth its 3× premium only where physics/motion or multi-character binding is
genuinely critical.

---

## Duration Constraints by Engine

Duration is an **engine contract**, not a free parameter — pick it from what the
engine actually accepts, then let the scenario refine within that set. Several
of these reject (rather than snap) an out-of-enum value, so validate before the
network call.

| Engine | Accepts | Enforcement |
|--------|---------|-------------|
| **GEMINI_OMNI** | *prompt-inferred* — **no structured duration kwarg** | Encode the intent in the prompt text. Nothing validates it, and the flat cost estimate assumes ~5s (see the cost caveat above) |
| VEO_NATIVE | 4s / 6s / 8s | Snaps to nearest valid; `"5s"` is server-rejected (INVALID_ARGUMENT) and clamped 5 → 6 (`veo_native._clamp_image_to_video_duration`) |
| LTX | 6 / 8 / 10 | **Raises before any network call** on anything else (`LTXVideoAPI.DURATION_SECONDS`; mirrored as `phase_c_ffmpeg._LTX_DURATION_ENUM_S`, drift-pinned by `tests/unit/test_ltx_native.py`). Use `nearest_supported_duration()` to snap-up first |
| SORA_NATIVE | 4 / 8 / 12 / 16 / 20 | Invalid values silently default to 4 — validate before submitting |
| SEEDANCE | 4–15s ints | Per shot type via `SEEDANCE_DURATIONS`: action/wide/landscape 8s, portrait/medium 4s |
| KLING_3_0 / KLING_NATIVE | 5s optimal | Longer durations increase temporal drift |
| RUNWAY_GEN4 | 10s fixed | No variable length |

**Scenario guidance** (within those constraints): 4–5s for dialogue/reaction and
walking (minimize temporal drift); 8s for complex motion and wide/landscape
establishing (full physics arcs, slow pans reveal detail); Veo 6s for
shot-to-shot transitions where first+last-frame interpolation is the point.

⚠️ `SEEDANCE_DURATIONS` is module-level *because* cost depends on it — an 8s
action clip costed against the per-~5s `API_COST_USD["SEEDANCE"]` figure
under-records by 38% (money-gate review 2026-07-11). Any new per-shot-type
duration map needs the same treatment.

---

## ComfyUI Node Mapping

`apply_workflow_params()` maps template values to ComfyUI nodes:

| Parameter | Node ID | Node Type | Input Field |
|-----------|---------|-----------|-------------|
| pulid_weight | 100 | ApplyPulid | weight |
| pulid_start_at | 100 | ApplyPulid | start_at |
| pulid_end_at | 100 | ApplyPulid | end_at |
| guidance | 60 | FluxGuidance | guidance |
| steps | 17 | BasicScheduler | steps |
| scheduler | 17 | BasicScheduler | scheduler |
| sampler | 16 | KSamplerSelect | sampler_name |
| pag_scale | 301 | PAG | scale |
