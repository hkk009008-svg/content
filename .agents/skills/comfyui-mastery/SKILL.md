---
name: comfyui-mastery
description: Use when building, modifying, debugging, or understanding ComfyUI workflows, nodes, or API-format JSON. Use when generating images via ComfyUI, configuring samplers, ControlNet, PuLID, IP-Adapter, AnimateDiff, or any custom node. Use when integrating ComfyUI with RunPod, Railway, or production pipelines.
---

# ComfyUI Mastery

ComfyUI is a node-based execution graph for Stable Diffusion and FLUX models. Workflows are directed acyclic graphs where each node has a `class_type`, typed `inputs` (scalars or links to other nodes), and typed outputs. The engine resolves execution order automatically from the graph topology.

## Workflow JSON Format (API)

```json
{
  "node_id": {
    "inputs": { "param": value, "linked_param": ["source_node_id", output_slot_index] },
    "class_type": "NodeClassName",
    "_meta": { "title": "Display Name" }
  }
}
```

- Node IDs are **strings** (e.g., `"8"`, `"100"`)
- Links are `["source_node_id", output_slot_index]` — slot 0 is the first output
- Execution flows from loaders → conditioning → sampler → decoder → save
- See `workflow-json-spec.md` for the complete format spec, validation rules, and generation algorithm

## Quick Reference: Core Node Types

| class_type | Purpose | Key Inputs |
|---|---|---|
| CheckpointLoaderSimple | Load SD checkpoint | ckpt_name |
| UNETLoader | Load FLUX/UNET model | unet_name, weight_dtype |
| DualCLIPLoader | Load T5+CLIP for FLUX | clip_name1, clip_name2, type |
| VAELoader | Load VAE model | vae_name |
| CLIPTextEncode | Text → conditioning | text, clip |
| FluxGuidance | FLUX CFG guidance | guidance, conditioning |
| EmptyLatentImage | Create blank latent | width, height, batch_size |
| KSampler | Standard sampler | model, positive, negative, seed, steps, cfg, sampler, scheduler |
| SamplerCustomAdvanced | Advanced sampler | noise, guider, sampler, sigmas, latent_image |
| BasicScheduler | Compute sigmas | model, scheduler, steps, denoise |
| KSamplerSelect | Choose sampler algo | sampler_name |
| BasicGuider | CFG guider | model, conditioning |
| RandomNoise | Seed-based noise | noise_seed |
| VAEDecode | Latent → image | samples, vae |
| VAEEncode | Image → latent | pixels, vae |
| SaveImage | Save to disk | images, filename_prefix |
| LoadImage | Load from disk | image (filename) |
| ApplyPulid | PuLID face-lock | weight, start_at, end_at, model, pulid, eva_clip, face_analysis, image |
| ControlNetApply | Apply ControlNet | conditioning, control_net, image, strength |
| LoraLoader | Load LoRA weights | model, clip, lora_name, strength_model, strength_clip |

## Common Workflow Patterns

| Pattern | Description | Template in workflow-patterns.md |
|---|---|---|
| txt2img-basic | Checkpoint → CLIP → KSampler → VAE → Save | #1 |
| txt2img-flux-pulid | FLUX + PuLID face-lock (this project's pipeline) | #2 |
| img2img | Load → VAEEncode → KSampler (denoise < 1.0) | #3 |
| controlnet-pose | OpenPose → ControlNet → KSampler | #4 |
| inpainting | Mask → SetLatentNoiseMask → InpaintModel | #5 |
| upscale-hires | Generate → LatentUpscale → KSampler (hires fix) | #6 |
| ip-adapter-style | Style reference → IP-Adapter → KSampler | #7 |
| animatediff-txt2vid | AnimateDiff → KSampler → VideoCombine | #8 |

## Reference File Routing

| You need to... | Read this file |
|---|---|
| Understand the JSON format, generate or validate workflows | `workflow-json-spec.md` |
| Get a complete workflow template to modify | `workflow-patterns.md` |
| Work with model loaders, samplers, VAE, conditioning | `nodes-core.md` |
| Add ControlNet, depth, pose, or edge guidance | `nodes-controlnet.md` |
| Add face identity (PuLID, IP-Adapter, InstantID, ReActor) | `nodes-face-identity.md` |
| Generate video (AnimateDiff, SVD) or interpolate frames | `nodes-video.md` |
| Upscale, segment, inpaint, or mask images | `nodes-image-processing.md` |
| Use math, logic, switches, reroutes, or conversions | `nodes-utility.md` |
| Use WAS, Impact Pack, or other ecosystem packs | `custom-node-packs.md` |
| Understand this project's ComfyUI + RunPod integration | `a24-integration.md` |

## This Project's Integration

The A24 Engine uses ComfyUI as the primary image generation backend:
- **Workflow**: `pulid.json` — 15-node FLUX + PuLID pipeline
- **Server**: RunPod GPU endpoint (RTX 4090) at `COMFYUI_SERVER_URL`
- **API class**: `RunPodComfyUI` in `phase_c_assembly.py`
- **Shot optimization**: `workflow_selector.py` — 5 shot-type templates
- **Cascade**: ComfyUI → FAL.ai Kontext → FAL.ai FLUX-Pro
- See `a24-integration.md` for full annotated architecture
