# ComfyUI Video & Animation Nodes Reference

## AnimateDiff (ComfyUI-AnimateDiff-Evolved)

**Repository**: `Kosinkadink/ComfyUI-AnimateDiff-Evolved`

AnimateDiff injects temporal motion modules into SD1.5/SDXL U-Net models so that
a standard txt2img or img2img pipeline produces coherent multi-frame sequences
instead of single images.

### Core Loader Nodes

#### ADE_LoadAnimateDiffModel
Loads a motion model checkpoint into memory.

| Input | Type | Notes |
|-------|------|-------|
| model_name | COMBO | Dropdown of `.ckpt`/`.safetensors` in `models/animatediff_models/` |

Output: `MOTION_MODEL_ADE`

#### ADE_AnimateDiffLoaderGen1 (current recommended loader)
Applies the loaded motion model to a standard SD model with context options.

| Input | Type | Notes |
|-------|------|-------|
| model | MODEL | Base SD model from CheckpointLoaderSimple |
| model_name | COMBO | Motion model file |
| beta_schedule | COMBO | `sqrt_linear` (default), `linear`, `cosine` |
| context_options | CONTEXT_OPTIONS | Optional -- from ADE_AnimateDiffUniformContextOptions |
| motion_lora | MOTION_LORA | Optional -- from ADE_AnimateDiffMotionLoRA |
| ad_settings | AD_SETTINGS | Optional -- sampling settings |
| sample_settings | SAMPLE_SETTINGS | Optional |
| motion_scale | FLOAT | 1.0 default, scale motion intensity |
| ad_keyframes | AD_KEYFRAMES | Optional -- per-frame overrides |

Output: `MODEL` (patched with motion modules)

#### ADE_AnimateDiffLoaderWithContext (Legacy)
Older combined loader that merges model loading + context in one node.
Maintained for backward compatibility. Prefer Gen1 loader for new workflows.

### Context Options

#### ADE_AnimateDiffUniformContextOptions
Controls the sliding-window context that determines how many frames the model
sees at once during denoising.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| context_length | INT | 16 | Frames per context window (typically 16) |
| context_stride | INT | 1 | Step between window starts |
| context_overlap | INT | 4 | Overlapping frames between windows |
| context_schedule | COMBO | `uniform` | `uniform`, `windowed` |
| closed_loop | BOOL | false | Connect last frame back to first |

Output: `CONTEXT_OPTIONS`

For generating videos longer than 16 frames, the context window slides across
the total frame count. Overlap ensures smooth transitions between windows.

### Sampling & Scheduling

#### ADE_AnimateDiffSamplingSettings
Fine-grained control over how the motion modules interact with sampling.

| Parameter | Type | Notes |
|-----------|------|-------|
| batch_offset | INT | Offset for noise scheduling |
| noise_type | COMBO | `default`, `FreeNoise`, `constant` |
| seed_gen | COMBO | `comfy`, `auto1111` |
| seed_offset | INT | Per-batch seed offset |

#### ADE_AnimateDiffKeyframe
Defines per-frame or per-range overrides for strength/scale.

| Parameter | Type | Notes |
|-----------|------|-------|
| start_percent | FLOAT | When in the frame sequence this keyframe activates |
| guarantee_steps | INT | Minimum steps this keyframe stays active |
| inherit_missing | BOOL | Inherit values from previous keyframe |

#### ADE_MultivalDynamic
Applies dynamic per-frame values (float schedules) to motion parameters.
Accepts a list of floats, one per frame.

### Combination / Output

#### ADE_AnimateDiffCombine
Combines generated frame latents/images into a single output.

| Parameter | Type | Notes |
|-----------|------|-------|
| images | IMAGE | Batch of frames |
| frame_rate | INT | Output FPS (default 8) |
| loop_count | INT | Number of loops |
| format | COMBO | `gif`, `webp`, `mp4` (if ffmpeg available) |
| pingpong | BOOL | Play forward then reverse |

### Motion Models

| Model File | Base | Frames | Notes |
|------------|------|--------|-------|
| mm_sd_v14.ckpt | SD1.4 | 16 | Original, lower quality |
| mm_sd_v15.ckpt | SD1.5 | 16 | Standard quality |
| mm_sd_v15_v2.ckpt | SD1.5 | 16 | Improved temporal coherence |
| mm_sdxl_v10_beta.ckpt | SDXL | 16 | SDXL beta, higher VRAM |
| temporaldiff-v1-animatediff.ckpt | SD1.5 | 16 | Community fine-tune |

Place motion models in: `ComfyUI/models/animatediff_models/`

### Motion LoRAs

#### ADE_AnimateDiffMotionLoRA
Loads a motion LoRA to modify motion characteristics (e.g., zoom, pan, tilt).

| Parameter | Type | Notes |
|-----------|------|-------|
| lora_name | COMBO | LoRA file from `models/animatediff_motion_lora/` |
| strength | FLOAT | 0.0-1.0, effect intensity |

---

## Stable Video Diffusion (SVD)

Built-in ComfyUI nodes for Stability AI's SVD img2vid model.

### ImageOnlyCheckpointLoader
Loads SVD checkpoints (`svd.safetensors` or `svd_xt.safetensors`).

| Parameter | Type | Notes |
|-----------|------|-------|
| ckpt_name | COMBO | SVD checkpoint file |

Outputs: `MODEL`, `CLIP_VISION`, `VAE`

### SVD_img2vid_Conditioning
Creates conditioning from an input image for video generation. Replaces standard
CLIP text conditioning -- SVD does NOT use text prompts.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| clip_vision | CLIP_VISION | -- | From ImageOnlyCheckpointLoader |
| init_image | IMAGE | -- | Starting frame |
| vae | VAE | -- | For latent encoding |
| width | INT | 1024 | Output width |
| height | INT | 576 | Output height |
| video_frames | INT | 14 | Frame count (14 for svd, 25 for svd_xt) |
| motion_bucket_id | INT | 127 | 1-1023, controls motion amount |
| fps | INT | 6 | Target framerate metadata |
| augmentation_level | FLOAT | 0.0 | Noise added to init image (0.0-1.0) |

Outputs: `positive` CONDITIONING, `negative` CONDITIONING, `latent` LATENT

### VideoLinearCFGGuidance
Model patch that applies linearly decreasing CFG across frames for smoother
motion. Later frames get lower guidance, reducing flickering.

| Parameter | Type | Notes |
|-----------|------|-------|
| model | MODEL | SVD model |
| min_cfg | FLOAT | Minimum CFG at last frame (default 1.0) |

### SVD Workflow Pattern
```
ImageOnlyCheckpointLoader -> model, clip_vision, vae
LoadImage -> init_image
SVD_img2vid_Conditioning(clip_vision, init_image, vae, ...) -> positive, negative, latent
VideoLinearCFGGuidance(model) -> patched_model
KSampler(patched_model, positive, negative, latent) -> samples
VAEDecode(samples, vae) -> images
VHS_VideoCombine(images) -> video file
```

---

## Video Helper Suite (ComfyUI-VideoHelperSuite)

**Repository**: `Kosinkadink/ComfyUI-VideoHelperSuite`

Essential utility nodes for loading, splitting, combining, and exporting video.

### VHS_LoadVideo (Load Video - Upload)
Loads a video file and extracts frames as an IMAGE batch.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| video | FILE | -- | Upload or path to video |
| force_rate | INT | 0 | Override FPS (0 = use original) |
| force_size | COMBO | `Disabled` | Resize option |
| custom_width | INT | 512 | Width when force_size enabled |
| custom_height | INT | 512 | Height when force_size enabled |
| frame_load_cap | INT | 0 | Max frames (0 = all) |
| skip_first_frames | INT | 0 | Skip N leading frames |
| select_every_nth | INT | 1 | Take every Nth frame |

Outputs: `IMAGE` (batch), `frame_count` INT, `audio` VHS_AUDIO, `video_info` VHS_VIDEOINFO

### VHS_LoadVideoPath (Load Video - Path)
Same as VHS_LoadVideo but accepts a file path string instead of upload widget.

### VHS_VideoCombine (Video Combine)
Merges IMAGE batch into a video file.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| images | IMAGE | -- | Frame batch |
| frame_rate | FLOAT | 8.0 | Output FPS |
| loop_count | INT | 0 | 0 = no loop |
| filename_prefix | STRING | `AnimateDiff` | Output filename |
| format | COMBO | `video/h264-mp4` | Also: `image/gif`, `image/webp` |
| pingpong | BOOL | false | Forward-reverse playback |
| save_output | BOOL | true | Save to output dir |
| audio | VHS_AUDIO | -- | Optional audio track |

### VHS_SplitVideoFrames (Split Video)
Splits an IMAGE batch at a specified index.

| Parameter | Type | Notes |
|-----------|------|-------|
| images | IMAGE | Input batch |
| split_index | INT | Frame number to split at |

Outputs: `IMAGE` (first half), `IMAGE` (second half)

### VHS_MergeLatents
Concatenates two LATENT batches along the batch dimension.

### VHS_GetLatentCount
Returns the number of samples in a LATENT batch as an INT.

### VHS_SelectEveryNthLatent
Temporal subsampling: picks every Nth latent from a batch.

| Parameter | Type | Notes |
|-----------|------|-------|
| latents | LATENT | Input batch |
| select_every_nth | INT | Stride |
| skip_first | INT | Offset before starting selection |

---

## Frame Interpolation (ComfyUI-Frame-Interpolation)

**Repository**: `Fannovel16/ComfyUI-Frame-Interpolation`

Generates intermediate frames between existing frames for smoother video.
All VFI nodes require an IMAGE input with at least 2 frames.

### RIFE_VFI
Real-Time Intermediate Flow Estimation. Fast, good general-purpose interpolator.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| frames | IMAGE | -- | Input frame batch (min 2) |
| ckpt_name | COMBO | `rife47.pth` | Model version: rife40-rife49 |
| multiplier | INT | 2 | Frames to insert between each pair |
| clear_cache_after_n_frames | INT | 10 | VRAM management |
| fast_mode | BOOL | true | Trade quality for speed |
| ensemble | BOOL | true | Better quality, slower |
| scale_factor | FLOAT | 1.0 | Internal processing scale |
| optional_interpolation_states | INTERPOLATION_STATES | -- | Scene detection mask |

Recommended models: `rife47.pth` (balanced), `rife49.pth` (latest/best quality).

Output: `IMAGE` (interpolated frame batch)

**Multiplier math**: Input 24 frames with multiplier=2 produces 47 frames.
Input N frames with multiplier M produces (N-1)*M + 1 frames.

### FILM_VFI
Frame Interpolation for Large Motion. Better for large motion between frames
but slower than RIFE.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| frames | IMAGE | -- | Input frame batch (min 2) |
| ckpt_name | COMBO | `film_net_fp32.pt` | Model checkpoint |
| multiplier | INT | 2 | Interpolation multiplier |
| clear_cache_after_n_frames | INT | 10 | VRAM management |

### Scene Detection (INTERPOLATION_STATES)
Optional input for VFI nodes. When scene changes are detected, interpolation
is skipped between those frames to prevent ghosting artifacts.

Generate with `VFI_SceneDetect` or provide manually.

---

## Temporal & Batch Operations

### Core Latent Batch Nodes (Built-in)

#### LatentBatch
Concatenates two LATENT inputs along the batch dimension.
Use to build up frame sequences for video pipelines.

#### RepeatLatentBatch
Repeats a LATENT N times along batch dimension.

| Parameter | Type | Notes |
|-----------|------|-------|
| samples | LATENT | Input |
| amount | INT | Repeat count |

### Frame Scheduling Patterns

For AnimateDiff workflows, frame scheduling is achieved by:

1. **Prompt scheduling**: Use ComfyUI prompt weighting with frame indices
   via AnimateDiff keyframes to change prompts over time.

2. **ControlNet scheduling**: Apply different ControlNet guidance per frame
   using timestep keyframes from Advanced-ControlNet.

3. **IPAdapter scheduling**: Use IPAdapter keyframes to transition between
   reference images across the video timeline.

4. **Latent composition**: Build frame batches with LatentBatch, then apply
   different noise/conditioning per segment.

### Motion Control Tips

- **motion_bucket_id** (SVD): Higher values = more motion. 127 is default.
  Range 1-1023. Values above 200 risk instability.
- **motion_scale** (AnimateDiff): Multiplier on motion module outputs.
  1.0 = normal. 0.5 = subtle motion. 1.5 = exaggerated motion.
- **augmentation_level** (SVD): Adding noise to init image increases motion
  diversity. 0.0 = faithful to input. 0.1-0.3 = moderate variation.
- **context_overlap** (AnimateDiff): Higher overlap = smoother transitions
  between context windows but slower generation. 4 is a good default.
- **FreeNoise**: Noise type in AnimateDiff sampling settings that improves
  temporal coherence for longer generations (32+ frames).

### Common Video Workflow Chain
```
[Generate/Load Frames]
  -> RIFE_VFI (2x-4x interpolation for smooth motion)
  -> ImageScale / ImageUpscaleWithModel (optional upscale)
  -> VHS_VideoCombine (export as mp4/gif/webp)
```

### VRAM Considerations

| Operation | VRAM Impact | Mitigation |
|-----------|------------|------------|
| AnimateDiff 16 frames SD1.5 | ~6-8 GB | Use context windows |
| AnimateDiff 16 frames SDXL | ~12-16 GB | Reduce resolution |
| SVD 14 frames | ~8-10 GB | Use fp16 |
| SVD_xt 25 frames | ~12-14 GB | Reduce frame count |
| RIFE interpolation | ~2-4 GB | clear_cache_after_n_frames |
| FILM interpolation | ~4-6 GB | Lower multiplier |
