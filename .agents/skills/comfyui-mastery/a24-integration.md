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
1. ComfyUI + PuLID on the self-hosted GPU pod (primary — strongest face-lock;
   currently a Novita RTX 6000 Ada)
2. FAL.ai FLUX Kontext Max Multi (fallback — identity-preserving)
3. FAL.ai FLUX-Pro (last resort — no face-lock)

The former max tier (`pulid_max.json`, `quality_max.py`, and
`MAX_QUALITY_TEMPLATES`) was retired in WS1. The 22-node `pulid.json` graph is
the sole production image tier.

## Annotated pulid.json Node Map

The production workflow is a 22-node FLUX + PuLID pipeline (the diagram shows
the core graph; PAG and the hires-upscale chain are in the table below):

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
| 301 | PerturbedAttentionGuidance | PAG model patch — detail sharpening | `scale` (per shot class, 2.0–3.5) |
| 501 | UpscaleModelLoader | Load hires upscale model | `RealESRGAN_x4plus.pth` |
| 500 | ImageUpscaleWithModel | Apply 4× upscale | upscale_model, image |
| 502 | ImageScale | Downsample to delivery res | lanczos, 2688×1536 landscape / 1536×2688 portrait |

## ComfyUI API Class

`RunPodComfyUI` in `comfyui_client.py` communicates with the ComfyUI server and
is imported by `phase_c_assembly.py`:

```python
class RunPodComfyUI:
    def preflight(workflow) -> dict             # /object_info + /models + /queue
    def upload_image(image_path) -> str         # bounded POST /upload/image
    def queue_prompt(workflow) -> str           # one-shot POST /prompt; parse node_errors
    def wait_for_completion(prompt_id) -> dict  # /ws events + bounded /history fallback
    def cancel_prompt(prompt_id) -> bool        # atomic scoped cancel; legacy request is UNKNOWN
    def interrupt() -> None                     # explicit global /interrupt control
    def download_image(..., destination) -> str # validate + atomic /view publication
```

**Environment**: `COMFYUI_SERVER_URL` (pod gateway URL, port 8188 — currently
a Novita RTX 6000 Ada pod; the class name `RunPodComfyUI` is historical, the
integration is host-agnostic). `COMFYUI_API_KEY` optionally supplies a bearer
token for an authenticated reverse proxy.

**Job control**: connect/read timeouts bound every request. Idempotent reads use
pooled retries for transport failures, 429, and selected 5xx responses;
`POST /prompt` is never blindly retried. WebSocket terminal errors fail
immediately, and the 600-second job deadline requests ID-scoped cancellation
before falling through. Older pods can receive a pending `/queue` deletion
request, but its race with job start remains `UNKNOWN` and blocks fallback. An
unknown submission acknowledgement or any unconfirmed cancellation fails closed
instead of starting a duplicate FAL render. Global `/interrupt` remains
available as an explicit control but is never used automatically because it can
race into the next job. Output images are MIME/magic/dimension validated and
atomically published.

## Workflow Selector

`workflow_selector.py` classifies shots and applies optimized parameters:

| Shot Type | PuLID Weight | Start At | Guidance | Steps | PAG | Use Case |
|---|---|---|---|---|---|---|
| portrait | 1.0 | 0.0 | 3.5 | 25 | 3.0 | Close-ups, max face fidelity |
| medium | 0.9 | 0.0 | 3.5 | 20 | 3.0 | Balanced face + scene |
| wide | 0.65 | 0.0 | 3.0 | 20 | 2.5 | Establishing shots |
| action | 0.8 | 0.0 | 3.5 | 20 | 2.0 | Movement, tracking |
| landscape | 0.0 | 0.0 | 4.0 | 25 | 3.5 | No characters, pure environment |

All classes run `dpmpp_2m` + `sgm_uniform`. Templates still carry historical
`controlnet_depth_strength` and `ip_adapter_weight` fields, but the production
graph has no ControlNet/IP-Adapter consumer. `denoise_default` drives the
supported nodes 200-201 img2img path; provider routing comes from the per-class
`target_api`/`video_fallbacks` cascade in `WORKFLOW_TEMPLATES`.

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
