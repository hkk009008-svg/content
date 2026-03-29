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

### Portrait (Close-up face focus)
```
pulid_weight:              1.0    # Maximum face-lock
pulid_start_at:            0.20   # Earlier = stronger identity bake-in
pulid_end_at:              1.0
guidance:                  3.5    # FLUX sweet spot
steps:                     25     # Finer skin texture, pore detail, iris sharpness
sampler:                   dpmpp_2m
scheduler:                 sgm_uniform
pag_scale:                 3.0    # Sharpen face details without oversaturation
controlnet_depth_strength: 0.35
ip_adapter_weight:         0.25   # Minimal style transfer
denoise_default:           0.25   # Tighter temporal consistency
target_api:                KLING_NATIVE
video_fallbacks:           [RUNWAY_GEN4, SORA_NATIVE, KLING_FAL]
```

### Medium (Waist-up balanced)
```
pulid_weight:              0.9
pulid_start_at:            0.25
pulid_end_at:              1.0
guidance:                  3.5
steps:                     20
sampler:                   dpmpp_2m
scheduler:                 sgm_uniform
pag_scale:                 3.0    # Enhance mid-range detail (clothing, background)
controlnet_depth_strength: 0.40
ip_adapter_weight:         0.30
denoise_default:           0.35
target_api:                KLING_NATIVE
video_fallbacks:           [RUNWAY_GEN4, SORA_NATIVE, LTX]
```

### Wide (Establishing shot, environment-primary)
```
pulid_weight:              0.65   # Lower — environment matters more
pulid_start_at:            0.35   # Later start — let environment establish
pulid_end_at:              0.9    # 90% — final 10% for environment polish
guidance:                  3.0
steps:                     20
sampler:                   dpmpp_2m
scheduler:                 sgm_uniform
pag_scale:                 2.5    # Lower — avoid over-sharpening
controlnet_depth_strength: 0.50   # Strongest spatial lock
ip_adapter_weight:         0.35
denoise_default:           0.45
target_api:                LTX    # 4K, 3D camera, depth-aware, cheapest
video_fallbacks:           [VEO_NATIVE, KLING_NATIVE, RUNWAY_GEN4]
```

### Action (Dynamic movement)
```
pulid_weight:              0.8    # Slightly reduced — action poses stress face
pulid_start_at:            0.30
pulid_end_at:              1.0
guidance:                  3.5
steps:                     20
sampler:                   dpmpp_2m
scheduler:                 sgm_uniform
pag_scale:                 2.0    # Lower — motion needs softness not crispness
controlnet_depth_strength: 0.30   # Light spatial guidance
ip_adapter_weight:         0.25
denoise_default:           0.40
target_api:                SORA_NATIVE  # Best motion physics, body momentum, cloth
video_fallbacks:           [KLING_NATIVE, RUNWAY_GEN4, LTX]
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
target_api:                LTX    # 4K, no face, cheapest, best environments
video_fallbacks:           [VEO_NATIVE, KLING_NATIVE]
```

---

## Cascade Retry Logic

From `phase_c_ffmpeg.py:generate_ai_video()`:

1. Try primary API (from `target_api`)
2. On failure → try next in `video_fallbacks` list
3. If ALL APIs exhausted → wait **2 minutes** for quota refresh
4. Retry up to **2 full cascade cycles**
5. Track `attempted_apis` set to prevent retry loops
6. After 2 complete cycles → return None (hard failure)

**Error handling**: Each API wrapped in try/catch. On exception → `try_next_api()`. Detailed logging per attempt.

**Global quota flags**: Some APIs (Veo) set `_veo_quota_exhausted = True` to prevent ALL subsequent shots from wasting time on a known-dead endpoint.

---

## Adaptive PuLID Feedback Loop

From `workflow_selector.py:get_adaptive_pulid_weight()`:

```
base_weight = WORKFLOW_TEMPLATES[shot_type]["pulid_weight"]
rolling_stats = identity_validator.get_rolling_stats(character_id, window=10)

if rolling_stats.success_rate < 0.7:
    # Identity failing → boost PuLID
    delta = +0.10
elif rolling_stats.mean_similarity > 0.8:
    # Identity passing strongly → allow flexibility
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

**Cheapest to most expensive** (approximate relative cost per video):

1. **LTX** — $  (4K capable, no polling overhead)
2. **Kling** — $$  (subject binding premium)
3. **Veo** — $$$  (reference images add cost)
4. **Runway** — $$$  (10s fixed, moderate cost)
5. **Sora** — $$$$  (highest cost, best motion)

**Cost strategy**: Use LTX for all wide/landscape/environment shots. Reserve Sora for scenes where physics/motion quality is critical. Kling is the best value for character-driven shots.

---

## Optimal Duration by Scenario

| Scenario | API | Duration | Rationale |
|----------|-----|----------|-----------|
| Dialogue/reaction | Kling | 5s | Face consistency, natural pacing |
| Walking/medium action | Kling/Sora | 4–5s | Avoid temporal drift |
| Complex motion | Sora | 8s | More frames for smooth physics |
| Wide environment | LTX/Veo | 6–8s | Time to establish setting |
| Landscape/cinematic pan | LTX | 8s | Slowest pan reveals detail |
| Shot-to-shot transition | Veo | 5–6s | First+last frame interpolation |

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
