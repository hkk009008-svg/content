# A24 Engine — ComfyUI Integration

This project uses ComfyUI as the primary image generation backend for the cinema production pipeline.

## Architecture

```
generate_ai_broll() in phase_c_assembly.py
    ├─ Load pulid.json template
    ├─ workflow_selector.py → classify shot → apply params
    ├─ Inject: prompt, seed, aspect ratio, face reference, init_image
    ├─ RunPodComfyUI.upload_image() → face ref + init image
    ├─ RunPodComfyUI.queue_prompt(workflow) → prompt_id
    ├─ Poll: get_history(prompt_id) up to 600s
    └─ Download: get_image(filename, subfolder, type)
```

**API Cascade** (if ComfyUI unavailable):
1. ComfyUI + PuLID on RunPod (primary — strongest face-lock)
2. FAL.ai FLUX Kontext Max Multi (fallback — identity-preserving)
3. FAL.ai FLUX-Pro (last resort — no face-lock)

## Annotated pulid.json Node Map

The production workflow is a 15-node FLUX + PuLID pipeline:

```
[112] UNETLoader ──────────────────────┐
  └─ FLUX1/flux1-dev-fp8.safetensors   │
                                        ▼
[11] DualCLIPLoader                 [100] ApplyPulid ──→ [22] BasicGuider ──→ [13] SamplerCustomAdvanced
  └─ t5xxl_fp8 + clip_l                ▲ ▲ ▲ ▲                  ▲                    │ ▲ ▲ ▲
       │                                │ │ │ │                  │                    │ │ │ │
       ▼                           [99] PulidModel    [60] FluxGuidance          [25]│[16][17]
[122] CLIPTextEncode ──→ [60]      [101] EvaClip           ▲                  Noise Sampler Sched
  └─ text prompt                   [97] InsightFace        │                         │
                                   [93] LoadImage ─────────┘                         ▼
                                     └─ face_reference.jpg                    [102] EmptyLatentImage
                                                                                └─ 1344×768
                                                                                     │
[13] SamplerCustomAdvanced ──→ [8] VAEDecode ──→ [9] SaveImage                       │
                                    ▲                                                │
                               [10] VAELoader                                        │
                                 └─ ae.safetensors                                   │
```

### Node Details

| Node ID | class_type | Role | Key Parameters |
|---|---|---|---|
| 112 | UNETLoader | Load FLUX diffusion model | `FLUX1/flux1-dev-fp8.safetensors` |
| 11 | DualCLIPLoader | Load T5-XXL + CLIP-L text encoders | `t5xxl_fp8`, `clip_l`, type=`flux` |
| 122 | CLIPTextEncode | Encode text prompt → conditioning | `text` (injected at runtime) |
| 60 | FluxGuidance | Apply FLUX-specific CFG | `guidance` (2.5-3.5 by shot type) |
| 93 | LoadImage | Load character face reference | `image` (uploaded filename) |
| 97 | PulidInsightFaceLoader | Load InsightFace model | `provider`: CUDA |
| 99 | PulidModelLoader | Load PuLID v0.9.1 model | `pulid_flux_v0.9.1.safetensors` |
| 101 | PulidEvaClipLoader | Load Eva CLIP for PuLID | (no params) |
| 100 | ApplyPulid | Apply face identity lock | `weight`, `start_at`, `end_at` |
| 22 | BasicGuider | Create CFG guider | model + conditioning |
| 25 | RandomNoise | Generate seeded noise | `noise_seed` (injected) |
| 16 | KSamplerSelect | Choose sampler algorithm | `euler` |
| 17 | BasicScheduler | Compute sigma schedule | `steps`, `denoise`, scheduler=`simple` |
| 102 | EmptyLatentImage | Create blank latent canvas | 1344×768, batch=1 |
| 13 | SamplerCustomAdvanced | Run denoising loop | noise, guider, sampler, sigmas, latent |
| 8 | VAEDecode | Decode latent → pixels | samples, vae |
| 10 | VAELoader | Load VAE model | `ae.safetensors` |
| 9 | SaveImage | Save output to disk | `FLUX_PuLID` prefix |

## RunPod API Class

`RunPodComfyUI` in `phase_c_assembly.py` communicates with the ComfyUI server:

```python
class RunPodComfyUI:
    def upload_image(image_path) -> str       # POST /upload/image → returns remote filename
    def queue_prompt(workflow) -> str          # POST /prompt → returns prompt_id
    def get_history(prompt_id) -> dict         # GET /history/{prompt_id} → poll for completion
    def get_image(filename, subfolder, type)   # GET /view?filename=...&subfolder=...&type=...
```

**Environment**: `COMFYUI_SERVER_URL` (RunPod proxy URL, port 8188)

**Polling**: 300 retries × 2s = 600s max timeout. Check `outputs` dict for `images` key.

## Workflow Selector

`workflow_selector.py` classifies shots and applies optimized parameters:

| Shot Type | PuLID Weight | Start At | Guidance | Steps | Use Case |
|---|---|---|---|---|---|
| portrait | 1.0 | 0.3 | 3.5 | 20 | Close-ups, max face fidelity |
| medium | 0.9 | 0.4 | 3.0 | 15 | Balanced face + scene |
| wide | 0.7 | 0.5 | 2.5 | 12 | Establishing shots |
| action | 0.85 | 0.4 | 3.0 | 15 | Movement, tracking |
| landscape | 0.0 | 0.0 | 2.5 | 12 | No characters, pure environment |

**Classification**: Keyword matching on prompt + camera fields (85+ keywords).
**Landscape bypass**: If no characters → skip ComfyUI entirely, use Kontext.

## Dynamic img2img Injection

When `init_image` is provided, `generate_ai_broll()` dynamically injects two nodes:

```python
# Node 200: Load the previous shot's image
workflow["200"] = {"inputs": {"image": remote_init}, "class_type": "LoadImage"}

# Node 201: Encode to latent space
workflow["201"] = {"inputs": {"pixels": ["200", 0], "vae": ["10", 0]}, "class_type": "VAEEncode"}

# Rewire: sampler takes latent from VAEEncode instead of EmptyLatentImage
workflow["13"]["inputs"]["latent_image"] = ["201", 0]

# Set denoise < 1.0 for temporal consistency
workflow["17"]["inputs"]["denoise"] = denoise_strength  # e.g., 0.3-0.5
```

This preserves composition from the previous shot while allowing style/content changes.

## Adaptive PuLID Weight

`get_adaptive_pulid_weight()` in `workflow_selector.py` creates a feedback loop:

1. Identity validator tracks rolling pass/fail rate per character
2. If faces keep failing → `suggested_pulid_delta` increases (+0.10)
3. If faces consistently pass → delta decreases (-0.05)
4. Smart exceptions: doesn't boost for `FACE_ANGLE_EXTREME` or `SMALL_FACE_REGION`
5. Final weight clamped to [0.0, 1.0]

The adapted weight is passed as `pulid_weight_override` to `generate_ai_broll()`.
