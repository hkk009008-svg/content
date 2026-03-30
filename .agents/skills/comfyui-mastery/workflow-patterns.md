# ComfyUI Workflow Patterns

8 complete workflow templates in API JSON format. Each includes an annotated node map and key parameters to modify.

## Pattern 1: txt2img-basic (SD 1.5 / SDXL)

**Use for**: Standard text-to-image with SD 1.5 or SDXL checkpoints.

```
[1] CheckpointLoaderSimple → MODEL(0), CLIP(1), VAE(2)
[2] CLIPTextEncode (positive) ← CLIP(1,1)
[3] CLIPTextEncode (negative) ← CLIP(1,1)
[4] EmptyLatentImage
[5] KSampler ← MODEL(1,0), positive(2,0), negative(3,0), latent(4,0)
[6] VAEDecode ← samples(5,0), VAE(1,2)
[7] SaveImage ← images(6,0)
```

```json
{
  "1": {"inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"}, "class_type": "CheckpointLoaderSimple"},
  "2": {"inputs": {"text": "a beautiful sunset over mountains, photorealistic, 8k", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
  "3": {"inputs": {"text": "blurry, low quality, deformed", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
  "4": {"inputs": {"width": 512, "height": 512, "batch_size": 1}, "class_type": "EmptyLatentImage"},
  "5": {"inputs": {"seed": 42, "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}, "class_type": "KSampler"},
  "6": {"inputs": {"samples": ["5", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
  "7": {"inputs": {"images": ["6", 0], "filename_prefix": "output"}, "class_type": "SaveImage"}
}
```

**Key parameters**: `ckpt_name`, `text` (prompts), `width`/`height`, `seed`, `steps`, `cfg`, `sampler_name`

---

## Pattern 2: txt2img-flux-pulid (This Project's Pipeline)

**Use for**: FLUX model with PuLID face identity preservation. This is the A24 Engine's production workflow.

See `a24-integration.md` for the full annotated `pulid.json` with 15 nodes.

**Key parameters to modify**:
- Node 122: `text` — generation prompt
- Node 25: `noise_seed` — deterministic seed
- Node 102: `width`/`height` — resolution (default 1344x768)
- Node 100: `weight` (0-1), `start_at`, `end_at` — PuLID face-lock strength
- Node 60: `guidance` — FLUX CFG (2.5-3.5)
- Node 17: `steps` (12-20), `denoise` (1.0 for txt2img, <1.0 for img2img)
- Node 93: `image` — face reference filename (must be uploaded first)

---

## Pattern 3: img2img

**Use for**: Generating from an existing image while preserving composition. Lower denoise = more similar to input.

```
[1] CheckpointLoaderSimple
[2] LoadImage (init image)
[3] VAEEncode ← pixels(2,0), vae(1,2)
[4] CLIPTextEncode (positive) ← clip(1,1)
[5] CLIPTextEncode (negative) ← clip(1,1)
[6] KSampler ← model(1,0), positive(4,0), negative(5,0), latent(3,0)
     denoise: 0.5 (lower = more preservation)
[7] VAEDecode ← samples(6,0), vae(1,2)
[8] SaveImage ← images(7,0)
```

```json
{
  "1": {"inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"}, "class_type": "CheckpointLoaderSimple"},
  "2": {"inputs": {"image": "init_image.png"}, "class_type": "LoadImage"},
  "3": {"inputs": {"pixels": ["2", 0], "vae": ["1", 2]}, "class_type": "VAEEncode"},
  "4": {"inputs": {"text": "cinematic portrait, golden hour lighting", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
  "5": {"inputs": {"text": "blurry, low quality", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
  "6": {"inputs": {"seed": 42, "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 0.5, "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["3", 0]}, "class_type": "KSampler"},
  "7": {"inputs": {"samples": ["6", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
  "8": {"inputs": {"images": ["7", 0], "filename_prefix": "img2img"}, "class_type": "SaveImage"}
}
```

**Key parameter**: `denoise` — 0.3 (subtle changes) to 0.8 (major rework). For temporal consistency between shots, use 0.3-0.5.

---

## Pattern 4: controlnet-pose

**Use for**: Generating images guided by OpenPose, depth maps, canny edges, etc.

```
[1] CheckpointLoaderSimple
[2] ControlNetLoader
[3] LoadImage (control image / reference pose)
[4] CLIPTextEncode (positive) ← clip(1,1)
[5] CLIPTextEncode (negative) ← clip(1,1)
[6] ControlNetApplyAdvanced ← positive(4,0), negative(5,0), control_net(2,0), image(3,0)
[7] EmptyLatentImage
[8] KSampler ← model(1,0), positive(6,0), negative(6,1), latent(7,0)
[9] VAEDecode ← samples(8,0), vae(1,2)
[10] SaveImage
```

```json
{
  "1": {"inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"}, "class_type": "CheckpointLoaderSimple"},
  "2": {"inputs": {"control_net_name": "control_v11p_sd15_openpose.safetensors"}, "class_type": "ControlNetLoader"},
  "3": {"inputs": {"image": "pose_reference.png"}, "class_type": "LoadImage"},
  "4": {"inputs": {"text": "a dancer in a red dress, studio lighting", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
  "5": {"inputs": {"text": "blurry, deformed", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
  "6": {"inputs": {"positive": ["4", 0], "negative": ["5", 0], "control_net": ["2", 0], "image": ["3", 0], "strength": 0.8, "start_percent": 0.0, "end_percent": 1.0}, "class_type": "ControlNetApplyAdvanced"},
  "7": {"inputs": {"width": 512, "height": 768, "batch_size": 1}, "class_type": "EmptyLatentImage"},
  "8": {"inputs": {"seed": 42, "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["6", 0], "negative": ["6", 1], "latent_image": ["7", 0]}, "class_type": "KSampler"},
  "9": {"inputs": {"samples": ["8", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
  "10": {"inputs": {"images": ["9", 0], "filename_prefix": "controlnet"}, "class_type": "SaveImage"}
}
```

**Tuning**: `strength` (0.5-1.0), `start_percent`/`end_percent` (for partial guidance). Stack multiple ControlNets by chaining ControlNetApplyAdvanced nodes.

---

## Pattern 5: inpainting

**Use for**: Replacing specific regions of an image while preserving the rest.

```
[1] CheckpointLoaderSimple (inpainting model preferred)
[2] LoadImage (original)
[3] LoadImageMask (mask — white = inpaint area)
[4] VAEEncodeForInpaint ← pixels(2,0), vae(1,2), mask(3,0)
[5] CLIPTextEncode (positive)
[6] CLIPTextEncode (negative)
[7] KSampler ← model(1,0), positive(5,0), negative(6,0), latent(4,0)
[8] VAEDecode
[9] SaveImage
```

```json
{
  "1": {"inputs": {"ckpt_name": "sd-v1-5-inpainting.safetensors"}, "class_type": "CheckpointLoaderSimple"},
  "2": {"inputs": {"image": "original.png"}, "class_type": "LoadImage"},
  "3": {"inputs": {"image": "mask.png", "channel": "red"}, "class_type": "LoadImageMask"},
  "4": {"inputs": {"pixels": ["2", 0], "vae": ["1", 2], "mask": ["3", 0], "grow_mask_by": 6}, "class_type": "VAEEncodeForInpaint"},
  "5": {"inputs": {"text": "a golden retriever sitting on grass", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
  "6": {"inputs": {"text": "blurry, deformed", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
  "7": {"inputs": {"seed": 42, "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["4", 0]}, "class_type": "KSampler"},
  "8": {"inputs": {"samples": ["7", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
  "9": {"inputs": {"images": ["8", 0], "filename_prefix": "inpaint"}, "class_type": "SaveImage"}
}
```

**Tips**: Use `grow_mask_by` (4-8 pixels) for smoother edges. Use inpainting-specific checkpoints for best results.

---

## Pattern 6: upscale-hires (Hires Fix)

**Use for**: Generating at low res then upscaling with a second pass for higher quality detail.

```
[1-7] Standard txt2img (Pattern 1) at low resolution
[8] LatentUpscale ← samples(5,0) — scale 2x
[9] KSampler ← model(1,0), positive(2,0), negative(3,0), latent(8,0), denoise=0.5
[10] VAEDecode ← samples(9,0)
[11] SaveImage
```

```json
{
  "1": {"inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"}, "class_type": "CheckpointLoaderSimple"},
  "2": {"inputs": {"text": "detailed portrait photo, 8k uhd", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
  "3": {"inputs": {"text": "blurry, low quality", "clip": ["1", 1]}, "class_type": "CLIPTextEncode"},
  "4": {"inputs": {"width": 512, "height": 512, "batch_size": 1}, "class_type": "EmptyLatentImage"},
  "5": {"inputs": {"seed": 42, "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}, "class_type": "KSampler"},
  "8": {"inputs": {"samples": ["5", 0], "upscale_method": "nearest-exact", "width": 1024, "height": 1024, "crop": "disabled"}, "class_type": "LatentUpscale"},
  "9": {"inputs": {"seed": 42, "steps": 15, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 0.5, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["8", 0]}, "class_type": "KSampler"},
  "10": {"inputs": {"samples": ["9", 0], "vae": ["1", 2]}, "class_type": "VAEDecode"},
  "11": {"inputs": {"images": ["10", 0], "filename_prefix": "hires"}, "class_type": "SaveImage"}
}
```

**Alternative**: Use `ImageUpscaleWithModel` (Real-ESRGAN) after VAEDecode for pixel-space upscaling instead of latent.

---

## Pattern 7: ip-adapter-style

**Use for**: Style transfer from a reference image using IP-Adapter.

```
[1] CheckpointLoaderSimple
[2] IPAdapterUnifiedLoader ← model(1,0)
[3] LoadImage (style reference)
[4] IPAdapterAdvanced ← model(2,0), image(3,0)
[5] CLIPTextEncode (positive)
[6] CLIPTextEncode (negative)
[7] EmptyLatentImage
[8] KSampler ← model(4,0), positive(5,0), negative(6,0), latent(7,0)
[9] VAEDecode
[10] SaveImage
```

**Key parameters**:
- `weight`: 0.5-1.0 (strength of style influence)
- `weight_type`: "standard", "linear", "ease in-out"
- `start_at`: 0.0, `end_at`: 1.0 (when IP-Adapter applies during denoising)
- `combine_embeds`: "concat", "add", "subtract" (for multiple references)

---

## Pattern 8: animatediff-txt2vid

**Use for**: Generating short video clips using AnimateDiff.

```
[1] CheckpointLoaderSimple
[2] ADE_AnimateDiffLoaderWithContext ← model(1,0)
[3] ADE_AnimateDiffUniformContextOptions (context_length=16, context_overlap=4)
[4] CLIPTextEncode (positive)
[5] CLIPTextEncode (negative)
[6] EmptyLatentImage (batch_size = frame_count, e.g., 16)
[7] KSampler ← model(2,0), positive(4,0), negative(5,0), latent(6,0)
[8] VAEDecode
[9] VHS_VideoCombine ← images(8,0), frame_rate=8
```

**Key parameters**:
- `batch_size` on EmptyLatentImage = number of frames (8, 16, 24)
- `frame_rate` on VHS_VideoCombine (8-24 fps)
- `context_length` and `context_overlap` on context options (16/4 is default)
- Motion model: `mm_sd_v15_v2.safetensors` for SD 1.5

**Gotchas**: AnimateDiff works with SD 1.5 models only (no SDXL/FLUX). Resolution must match the motion model's training (typically 512x512 or 512x768).

---

## Combining Patterns

Patterns can be combined by merging their node graphs:

| Want | Combine |
|---|---|
| Face-locked img2img | Pattern 2 + inject VAEEncode/LoadImage nodes (see a24-integration.md) |
| ControlNet + face identity | Pattern 4 + Pattern 2 (add ControlNet nodes to FLUX+PuLID workflow) |
| Inpainting + upscale | Pattern 5 → Pattern 6 (inpaint then hires fix) |
| Video + face identity | Not directly supported — generate frames with Pattern 2, use video tools to compile |
| Style + ControlNet | Pattern 7 + Pattern 4 (IP-Adapter + ControlNet on same model) |
