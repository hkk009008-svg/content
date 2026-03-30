# ComfyUI Core Nodes Reference

Comprehensive reference for all built-in ComfyUI nodes. class_type values match NODE_CLASS_MAPPINGS keys exactly.

---

## Model Loaders

| class_type | Inputs | Outputs | Description | Gotchas |
|---|---|---|---|---|
| `CheckpointLoaderSimple` | `ckpt_name`: COMBO | `MODEL`, `CLIP`, `VAE` | Loads a .safetensors/.ckpt checkpoint with model, CLIP, and VAE | Most common loader; VAE output may be suboptimal for some models -- use separate VAELoader |
| `CheckpointLoader` | `config_name`: COMBO, `ckpt_name`: COMBO | `MODEL`, `CLIP`, `VAE` | Loads checkpoint with explicit config file selection | Legacy node; prefer CheckpointLoaderSimple unless you need a custom config |
| `UNETLoader` | `unet_name`: COMBO, `weight_dtype`: COMBO | `MODEL` | Loads only the U-Net/diffusion model (no CLIP or VAE) | Used with Flux and other architectures where CLIP is loaded separately; weight_dtype controls fp16/fp32/etc |
| `DualCLIPLoader` | `clip_name1`: COMBO, `clip_name2`: COMBO, `type`: COMBO | `CLIP` | Loads two CLIP models and merges them into one CLIP object | Required for SDXL (clip_l + clip_g) and Flux (clip_l + t5xxl); type selects sdxl/sd3/flux |
| `CLIPLoader` | `clip_name`: COMBO, `type`: COMBO | `CLIP` | Loads a single CLIP text encoder model | type selects stable_diffusion, stable_cascade, sd3, stable_audio, mochi, ltxv, cosmos |
| `VAELoader` | `vae_name`: COMBO | `VAE` | Loads a standalone VAE model | Use when checkpoint's built-in VAE produces artifacts |
| `LoraLoader` | `model`: MODEL, `clip`: CLIP, `lora_name`: COMBO, `strength_model`: FLOAT, `strength_clip`: FLOAT | `MODEL`, `CLIP` | Applies a LoRA to both model and CLIP | strength values default 1.0; negative values invert the LoRA effect; chain multiple for stacking |
| `LoraLoaderModelOnly` | `model`: MODEL, `lora_name`: COMBO, `strength_model`: FLOAT | `MODEL` | Applies a LoRA to the model only (no CLIP modification) | Useful when LoRA should not alter text encoding |
| `unCLIPCheckpointLoader` | `ckpt_name`: COMBO | `MODEL`, `CLIP`, `VAE`, `CLIP_VISION` | Loads an unCLIP checkpoint with CLIP vision encoder | For image-variation models (e.g. SD2.1-unclip); outputs extra CLIP_VISION |
| `StyleModelLoader` | `style_model_name`: COMBO | `STYLE_MODEL` | Loads a style model (e.g. for T2I-Adapter style) | Reads from models/style_models directory |
| `GLIGENLoader` | `gligen_name`: COMBO | `GLIGEN` | Loads a GLIGEN grounded-language model | Used with GLIGENTextBoxApply for spatial text-box conditioning |
| `HypernetworkLoader` | `model`: MODEL, `hypernetwork_name`: COMBO, `strength`: FLOAT | `MODEL` | Loads and applies a hypernetwork to the model | Largely superseded by LoRA; strength default 1.0 |
| `UpscaleModelLoader` | `model_name`: COMBO | `UPSCALE_MODEL` | Loads an image upscale model (ESRGAN, RealESRGAN, etc.) | Reads from models/upscale_models; output feeds into ImageUpscaleWithModel |
| `CLIPVisionLoader` | `clip_name`: COMBO | `CLIP_VISION` | Loads a CLIP Vision model for image encoding | Reads from models/clip_vision; used with IPAdapter, unCLIP, and style transfer |

---

## Samplers and Scheduling

### High-Level Samplers

| class_type | Inputs | Outputs | Description | Gotchas |
|---|---|---|---|---|
| `KSampler` | `model`: MODEL, `seed`: INT, `steps`: INT, `cfg`: FLOAT, `sampler_name`: COMBO, `scheduler`: COMBO, `positive`: CONDITIONING, `negative`: CONDITIONING, `latent_image`: LATENT, `denoise`: FLOAT | `LATENT` | Standard all-in-one sampler; adds noise then denoises | denoise=1.0 for txt2img, 0.3-0.8 for img2img; most common sampler node |
| `KSamplerAdvanced` | `model`: MODEL, `add_noise`: COMBO (enable/disable), `noise_seed`: INT, `steps`: INT, `cfg`: FLOAT, `sampler_name`: COMBO, `scheduler`: COMBO, `positive`: CONDITIONING, `negative`: CONDITIONING, `latent_image`: LATENT, `start_at_step`: INT, `end_at_step`: INT, `return_with_leftover_noise`: COMBO (enable/disable) | `LATENT` | Advanced sampler with noise control and step range | No denoise param -- use start_at_step/end_at_step instead; can chain for multi-pass |
| `SamplerCustom` | `model`: MODEL, `add_noise`: BOOLEAN, `noise_seed`: INT, `cfg`: FLOAT, `positive`: CONDITIONING, `negative`: CONDITIONING, `sampler`: SAMPLER, `sigmas`: SIGMAS, `latent_image`: LATENT | `LATENT` (output), `LATENT` (denoised_output) | Custom sampler using separate SAMPLER and SIGMAS inputs | Dual outputs: output has leftover noise, denoised_output is clean; deprecated in favor of SamplerCustomAdvanced |
| `SamplerCustomAdvanced` | `noise`: NOISE, `guider`: GUIDER, `sampler`: SAMPLER, `sigmas`: SIGMAS, `latent_image`: LATENT | `LATENT` (output), `LATENT` (denoised_output) | Fully modular sampler with pluggable noise, guider, sampler, and sigmas | Most flexible sampler; requires wiring RandomNoise + Guider + KSamplerSelect + Scheduler |

### Sampler Selection

| class_type | Inputs | Outputs | Description | Gotchas |
|---|---|---|---|---|
| `KSamplerSelect` | `sampler_name`: COMBO | `SAMPLER` | Selects a sampler algorithm by name for SamplerCustom(Advanced) | Options: euler, euler_ancestral, heun, dpm_2, dpm_2_ancestral, lms, dpm_fast, dpm_adaptive, dpmpp_2s_ancestral, dpmpp_sde, dpmpp_2m, dpmpp_2m_sde, dpmpp_3m_sde, ddpm, lcm, uni_pc, uni_pc_bh2, ipndm, ipndm_v, deis |

### Schedulers (Sigma Generators)

| class_type | Inputs | Outputs | Description | Gotchas |
|---|---|---|---|---|
| `BasicScheduler` | `model`: MODEL, `scheduler`: COMBO, `steps`: INT, `denoise`: FLOAT | `SIGMAS` | Generates sigmas using model's built-in scheduler options | scheduler options: normal, karras, exponential, sgm_uniform, simple, ddim_uniform, beta; denoise < 1.0 truncates steps |
| `KarrasScheduler` | `steps`: INT, `sigma_max`: FLOAT, `sigma_min`: FLOAT, `rho`: FLOAT | `SIGMAS` | Generates Karras noise schedule sigmas | Model-independent; defaults sigma_max=14.614642, sigma_min=0.0291675, rho=7.0 |
| `NormalScheduler` | `steps`: INT, `sigma_max`: FLOAT, `sigma_min`: FLOAT | `SIGMAS` | Generates normally-distributed noise schedule sigmas | Model-independent; simpler than Karras |
| `ExponentialScheduler` | `steps`: INT, `sigma_max`: FLOAT, `sigma_min`: FLOAT | `SIGMAS` | Generates exponentially-distributed noise schedule sigmas | Good default for many models |
| `PolyexponentialScheduler` | `steps`: INT, `sigma_max`: FLOAT, `sigma_min`: FLOAT, `rho`: FLOAT | `SIGMAS` | Generates polyexponential noise schedule sigmas | Extension of exponential schedule with rho shape parameter |
| `SDTurboScheduler` | `model`: MODEL, `steps`: INT, `denoise`: FLOAT | `SIGMAS` | Generates sigmas optimized for SD-Turbo/SDXL-Turbo models | Designed for very low step counts (1-4 steps) |
| `VPScheduler` | `steps`: INT, `beta_d`: FLOAT, `beta_min`: FLOAT, `eps_s`: FLOAT | `SIGMAS` | Generates Variance Preserving (VP) noise schedule sigmas | Used for VP-type diffusion models |
| `SGMUniformScheduler` | `steps`: INT, `sigma_max`: FLOAT, `sigma_min`: FLOAT | `SIGMAS` | Generates SGM uniform noise schedule sigmas | Model-independent |

### Sigma Operations

| class_type | Inputs | Outputs | Description | Gotchas |
|---|---|---|---|---|
| `SplitSigmas` | `sigmas`: SIGMAS, `step`: INT | `SIGMAS` (high), `SIGMAS` (low) | Splits a sigma sequence at the given step into two parts | Dual output: high_sigmas (before step), low_sigmas (after step); for multi-stage sampling |
| `FlipSigmas` | `sigmas`: SIGMAS | `SIGMAS` | Reverses the order of sigma values | Used for RF-Inversion and other reverse-diffusion techniques; ensures first value is non-zero |

---

## Conditioning

| class_type | Inputs | Outputs | Description | Gotchas |
|---|---|---|---|---|
| `CLIPTextEncode` | `text`: STRING, `clip`: CLIP | `CONDITIONING` | Encodes text prompt into conditioning using CLIP | The workhorse prompt node; supports ComfyUI weight syntax (word:1.2) |
| `CLIPTextEncodeSDXL` | `clip`: CLIP, `width`: INT, `height`: INT, `crop_w`: INT, `crop_h`: INT, `target_width`: INT, `target_height`: INT, `text_g`: STRING, `text_l`: STRING | `CONDITIONING` | SDXL-specific dual text encoder with resolution conditioning | text_g = OpenCLIP-bigG (global), text_l = CLIP-L (local); width/height should match output resolution |
| `CLIPSetLastLayer` | `clip`: CLIP, `stop_at_clip_layer`: INT | `CLIP` | Sets which CLIP layer to use for encoding | Negative values count from end; -1 is last, -2 is second-to-last; some models work better with -2 |
| `ConditioningCombine` | `conditioning_1`: CONDITIONING, `conditioning_2`: CONDITIONING | `CONDITIONING` | Combines two conditionings by concatenating their lists | Creates an OR-like effect -- model attends to both; different from ConditioningConcat |
| `ConditioningConcat` | `conditioning_to`: CONDITIONING, `conditioning_from`: CONDITIONING | `CONDITIONING` | Concatenates conditioning tensors along sequence dimension | Creates AND-like effect -- extends the token sequence; different from ConditioningCombine |
| `ConditioningSetArea` | `conditioning`: CONDITIONING, `width`: INT, `height`: INT, `x`: INT, `y`: INT, `strength`: FLOAT | `CONDITIONING` | Sets a spatial area for the conditioning (in pixels, 8px increments) | Coordinates and dimensions in pixel space (auto-divided by 8 internally); for regional prompting |
| `ConditioningSetAreaPercentage` | `conditioning`: CONDITIONING, `width`: FLOAT, `height`: FLOAT, `x`: FLOAT, `y`: FLOAT, `strength`: FLOAT | `CONDITIONING` | Sets a spatial area for the conditioning using 0.0-1.0 percentages | More intuitive than pixel-based; 0.5 width = half the image |
| `ConditioningSetMask` | `conditioning`: CONDITIONING, `mask`: MASK, `strength`: FLOAT, `set_cond_area`: COMBO | `CONDITIONING` | Applies a mask to the conditioning region | set_cond_area: default or mask bounds; essential for inpainting workflows |
| `ConditioningSetTimestepRange` | `conditioning`: CONDITIONING, `start`: FLOAT, `end`: FLOAT | `CONDITIONING` | Limits conditioning to a percentage range of timesteps | start/end are 0.0-1.0 representing % of total timesteps; for prompt scheduling across steps |
| `ConditioningZeroOut` | `conditioning`: CONDITIONING | `CONDITIONING` | Zeros out the conditioning tensors (including pooled_output) | Produces empty/null conditioning; useful as true unconditional input for CFG |
| `FluxGuidance` | `conditioning`: CONDITIONING, `guidance`: FLOAT | `CONDITIONING` | Applies guidance scale to conditioning for Flux models | Default 3.5; range 0.0-100.0; Flux uses guidance embedding instead of CFG |

### Guiders (for SamplerCustomAdvanced)

| class_type | Inputs | Outputs | Description | Gotchas |
|---|---|---|---|---|
| `BasicGuider` | `model`: MODEL, `conditioning`: CONDITIONING | `GUIDER` | Simple guider with single conditioning (no CFG) | For Flux and other models that use internal guidance; no negative prompt |
| `CFGGuider` | `model`: MODEL, `positive`: CONDITIONING, `negative`: CONDITIONING, `cfg`: FLOAT | `GUIDER` | Standard Classifier-Free Guidance with positive/negative conditioning | cfg default 8.0; the standard guider for SD1.5/SDXL workflows |
| `DualCFGGuider` | `model`: MODEL, `cond1`: CONDITIONING, `cond2`: CONDITIONING, `negative`: CONDITIONING, `cfg_conds`: FLOAT, `cfg_cond2_negative`: FLOAT | `GUIDER` | Dual CFG with two positive conditionings and one negative | For advanced dual-conditioning setups; two separate cfg scale controls |

---

## Latent Operations

| class_type | Inputs | Outputs | Description | Gotchas |
|---|---|---|---|---|
| `EmptyLatentImage` | `width`: INT, `height`: INT, `batch_size`: INT | `LATENT` | Creates a blank latent image filled with zeros | Dimensions must be multiples of 8; SD1.5 typical 512x512, SDXL typical 1024x1024 |
| `EmptySD3LatentImage` | `width`: INT, `height`: INT, `batch_size`: INT | `LATENT` | Creates a blank latent image for SD3/Flux models | Dimensions in 16px increments; 16-channel latent space vs 4-channel for SD1.5/SDXL |
| `LatentUpscale` | `samples`: LATENT, `upscale_method`: COMBO, `width`: INT, `height`: INT, `crop`: COMBO | `LATENT` | Resizes latent to exact width/height | Methods: nearest-exact, bilinear, area, bicubic, bislerp; crop: disabled or center |
| `LatentUpscaleBy` | `samples`: LATENT, `upscale_method`: COMBO, `scale_by`: FLOAT | `LATENT` | Resizes latent by a scale factor | scale_by 2.0 = double resolution; same methods as LatentUpscale |
| `LatentComposite` | `samples_to`: LATENT, `samples_from`: LATENT, `x`: INT, `y`: INT, `feather`: INT | `LATENT` | Composites one latent onto another at x,y position | Coordinates in latent space (pixels / 8); feather blends edges |
| `LatentBlend` | `samples1`: LATENT, `samples2`: LATENT, `blend_factor`: FLOAT | `LATENT` | Blends two latents by factor (0.0 = samples1, 1.0 = samples2) | Simple linear interpolation; factor 0.5 is equal mix |
| `LatentCrop` | `samples`: LATENT, `width`: INT, `height`: INT, `x`: INT, `y`: INT | `LATENT` | Crops a region from the latent | All values in pixel space (internally divided by 8); must be multiples of 8 |
| `LatentFlip` | `samples`: LATENT, `flip_method`: COMBO | `LATENT` | Flips latent horizontally or vertically | flip_method: x-axis (vertical flip) or y-axis (horizontal flip) |
| `LatentRotate` | `samples`: LATENT, `rotation`: COMBO | `LATENT` | Rotates latent by fixed angles | rotation: none, 90 degrees, 180 degrees, 270 degrees |
| `LatentBatch` | `samples1`: LATENT, `samples2`: LATENT | `LATENT` | Concatenates two latents into a batch | Both must have same width/height; increases batch dimension |
| `LatentFromBatch` | `samples`: LATENT, `batch_index`: INT, `length`: INT | `LATENT` | Extracts a slice from a latent batch | batch_index is 0-based; length is number of frames to extract |
| `RepeatLatentBatch` | `samples`: LATENT, `amount`: INT | `LATENT` | Repeats a latent N times along batch dimension | Useful for generating multiple images from same latent dimensions |
| `LatentAdd` | `samples1`: LATENT, `samples2`: LATENT | `LATENT` | Element-wise addition of two latent tensors | Both must match in spatial dimensions |
| `LatentSubtract` | `samples1`: LATENT, `samples2`: LATENT | `LATENT` | Element-wise subtraction (samples1 - samples2) | Useful for extracting latent differences |
| `LatentMultiply` | `samples`: LATENT, `multiplier`: FLOAT | `LATENT` | Scales all latent values by a multiplier | Can amplify or attenuate latent signal |
| `LatentInterpolate` | `samples1`: LATENT, `samples2`: LATENT, `ratio`: FLOAT | `LATENT` | Interpolates between two latents by ratio | ratio 0.0 = samples1, 1.0 = samples2; smooth blending |

---

## VAE

| class_type | Inputs | Outputs | Description | Gotchas |
|---|---|---|---|---|
| `VAEDecode` | `samples`: LATENT, `vae`: VAE | `IMAGE` | Decodes latent tensor to pixel-space image | Standard path from latent to viewable image; output is 0-1 float tensor |
| `VAEDecodeTiled` | `samples`: LATENT, `vae`: VAE, `tile_size`: INT | `IMAGE` | Decodes latent in tiles to reduce VRAM usage | tile_size default 512; use when VAEDecode OOMs on large images |
| `VAEEncode` | `pixels`: IMAGE, `vae`: VAE | `LATENT` | Encodes pixel-space image to latent tensor | Input must be 0-1 float IMAGE; standard img2img encode path |
| `VAEEncodeForInpaint` | `pixels`: IMAGE, `vae`: VAE, `mask`: MASK, `grow_mask_by`: INT | `LATENT` | Encodes image for inpainting with mask handling | grow_mask_by expands mask edges (default 6); sets masked latent pixels to zero |
| `VAELoader` | `vae_name`: COMBO | `VAE` | Loads a standalone VAE model | See Model Loaders section above |

---

## Noise

| class_type | Inputs | Outputs | Description | Gotchas |
|---|---|---|---|---|
| `RandomNoise` | `noise_seed`: INT | `NOISE` | Generates random noise from a seed for SamplerCustomAdvanced | Deterministic given same seed; feeds into SamplerCustomAdvanced noise input |
| `DisableNoise` | (none) | `NOISE` | Produces a no-op noise object (no noise added) | Use when you want to denoise without adding fresh noise; for second-pass sampling |

---

## Image I/O

| class_type | Inputs | Outputs | Description | Gotchas |
|---|---|---|---|---|
| `LoadImage` | `image`: COMBO (file picker) | `IMAGE`, `MASK` | Loads an image from the input directory | Also outputs alpha channel as MASK (white if no alpha); auto-converts to RGB float |
| `LoadImageMask` | `image`: COMBO (file picker), `channel`: COMBO | `MASK` | Loads a specific channel of an image as a mask | channel: alpha, red, green, blue; useful for extracting masks from specific channels |
| `SaveImage` | `images`: IMAGE, `filename_prefix`: STRING | (none -- saves to disk) | Saves image(s) to the output directory | Appends incrementing counter to filename_prefix; saves as PNG; shows in UI |
| `PreviewImage` | `images`: IMAGE | (none -- displays in UI) | Displays image in the UI without saving permanently | Saves to temp directory; images cleared on restart; use for debugging |

---

## Quick-Reference: Wiring Patterns

**Standard SD1.5/SDXL txt2img:**
```
CheckpointLoaderSimple -> MODEL, CLIP, VAE
CLIPTextEncode (positive) + CLIPTextEncode (negative) -> CONDITIONING
EmptyLatentImage -> LATENT
KSampler (all wired) -> LATENT
VAEDecode -> IMAGE -> SaveImage
```

**Flux txt2img (modular):**
```
UNETLoader -> MODEL
DualCLIPLoader (clip_l + t5xxl, type=flux) -> CLIP
VAELoader -> VAE
CLIPTextEncode -> CONDITIONING
FluxGuidance -> CONDITIONING
EmptySD3LatentImage -> LATENT
RandomNoise + BasicGuider + KSamplerSelect + BasicScheduler -> SamplerCustomAdvanced -> LATENT
VAEDecode -> IMAGE -> SaveImage
```
