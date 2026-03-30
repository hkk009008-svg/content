# ComfyUI Custom Node Packs Reference

## ComfyUI-Manager

**Repository**: `Comfy-Org/ComfyUI-Manager`
**Install**: Bundled with ComfyUI as of late 2025. For older installs:
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Comfy-Org/ComfyUI-Manager.git
```

### Purpose
Central management hub for installing, updating, removing, and disabling
custom nodes. Eliminates manual git cloning and dependency management.

### Key Features

| Feature | Description |
|---------|-------------|
| Node Database Search | Search 1000+ custom nodes by name or function |
| One-Click Install | Install any registered node pack with automatic dependency resolution |
| Missing Node Detection | Detects red (missing) nodes when loading workflows, offers to install them |
| Model Download | Downloads models and places them in correct directories automatically |
| Conflict Detection | Flags dependency incompatibilities before installation |
| Update All | Batch-update all installed custom nodes |
| Disable/Enable | Toggle node packs without uninstalling |
| Snapshot/Restore | Save and restore node environment state |

### Usage
Access via the **Manager** button in the ComfyUI menu bar.
- **Install Custom Nodes**: Search and install from the registry
- **Install Missing Custom Nodes**: Auto-detect what a workflow needs
- **Install Models**: Browse and download models by category
- **Update All**: Check for and apply updates to all packs

### API Endpoints (for automation)
- `GET /manager/reboot` -- Restart ComfyUI
- `GET /manager/component/get_list` -- List installed nodes
- `POST /manager/component/install` -- Install a node pack

---

## WAS Node Suite

**Repository**: `WASasquatch/was-node-suite-comfyui`
**Install**: ComfyUI-Manager or `git clone` into `custom_nodes/`
**Node Count**: 218+ nodes

### Purpose
The largest general-purpose node suite. Fills gaps in ComfyUI's core with
text manipulation, image filters, number operations, and workflow utilities.

### Key Node Categories

#### Text Manipulation
| Node | Function |
|------|----------|
| Text Concatenate | Join 2-4 strings with optional delimiter |
| Text Multiline | Multi-line text input widget |
| Text Random Line | Pick random line from text block (seeded) |
| Text Find and Replace | Regex or literal string replacement |
| Text Parse Tokens | Replace custom tokens in prompts |
| Text Parse Noodle Soup Prompts | NSP wildcard expansion |
| Text Load Line From File | Sequential or indexed line loading |
| Text String Truncate | Truncate to character count |
| CLIP Text Encode (NSP) | CLIP encoding with Noodle Soup Prompt support |

#### Image Processing
| Node | Function |
|------|----------|
| Image Resize | Resize with multiple interpolation methods |
| Image Crop Face | Auto-detect and crop faces |
| Image Blend | Blend two images with opacity |
| Image Bloom Filter | Add bloom/glow effect |
| Image Gradient Map | Apply color gradient mapping |
| Image Dragan Photography Filter | Dramatic HDR-style effect |
| Image Chromatic Aberration | Simulated lens aberration |
| Image Film Grain | Add film grain noise |
| Image Style Filter | Preset artistic filters |

#### Number & Logic
| Node | Function |
|------|----------|
| Number Input | Typed number input (INT or FLOAT) |
| Number Multiple Of | Round to nearest multiple |
| Number Operation | Basic arithmetic between two numbers |
| Random Number | Seeded random number generation |
| Logic Boolean | Output 1 or 0 |
| Logic Boolean Primitive | True/False input widget |
| Logic Comparison AND/OR | Combine boolean conditions |

#### Conditioning Helpers
| Node | Function |
|------|----------|
| CLIP Text Encode (NSP) | Enhanced text encoding with wildcards |
| Conditioning Input Switch | Route between two conditioning inputs |
| Bus Node | Bundle multiple types into one connection |

---

## Impact Pack

**Repository**: `ltdrdata/ComfyUI-Impact-Pack`
**Install**: ComfyUI-Manager or git clone
**Node Count**: 100+ nodes

### Purpose
Automated detection, segmentation, and detail enhancement. The go-to pack
for face fixing, object-level inpainting, and regional processing.

### Core Concepts

**SEGS** (Segments): A data type representing detected regions in an image.
Each segment contains: bounding box, mask, crop, confidence score, label.

**DetailerPipe**: A bundled pipeline containing MODEL + CLIP + VAE + positive +
negative conditioning. Simplifies passing all needed data to Detailer nodes.

### Key Nodes

#### Detection & Segmentation
| Node | Function |
|------|----------|
| SAMLoader | Load Segment Anything model |
| UltralyticsDetectorProvider | Load YOLO/ultralytics detection model |
| BboxDetectorSEGS | Detect bounding boxes -> SEGS |
| SAMDetectorCombined | SAM-based segmentation from points/boxes |
| MaskToSEGS | Convert mask to SEGS format |
| SEGSToMask | Convert SEGS back to combined mask |
| SEGSToMaskList | Convert SEGS to individual masks |

#### Detail Enhancement
| Node | Function |
|------|----------|
| FaceDetailer | All-in-one face detection + enhancement |
| FaceDetailerPipe | FaceDetailer with pipe input for multi-pass |
| DetailerForEach | Apply enhancement to each detected segment |
| DetailerForEachPipe | Pipe version of DetailerForEach |

#### FaceDetailer Parameters
| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| image | IMAGE | -- | Input image |
| model | MODEL | -- | SD model for re-generation |
| clip | CLIP | -- | Text encoder |
| vae | VAE | -- | VAE for encode/decode |
| positive | CONDITIONING | -- | Prompt for face region |
| negative | CONDITIONING | -- | Negative prompt |
| bbox_detector | BBOX_DETECTOR | -- | Face detection model |
| sam_model | SAM_MODEL | -- | Optional SAM for precise masks |
| guide_size | INT | 384 | Target size for detected region |
| denoise | FLOAT | 0.5 | Re-generation strength |
| feather | INT | 5 | Mask edge feathering |
| steps | INT | 20 | Sampling steps for detail pass |

#### Pipe Management
| Node | Function |
|------|----------|
| BasicPipe | Bundle MODEL+CLIP+VAE+pos+neg into pipe |
| BasicPipeToDetailerPipe | Convert BasicPipe to DetailerPipe format |
| DetailerPipeToBasicPipe | Reverse conversion |
| EditBasicPipe | Modify individual elements of a pipe |
| EditDetailerPipe | Modify DetailerPipe elements |

#### Regional Processing
| Node | Function |
|------|----------|
| SEGSDetailer | Enhance each segment independently |
| SEGSPreview | Preview detected segments |
| SEGSOrderedFilter | Filter/sort segments by area, confidence |
| SEGSLabelFilter | Filter segments by detection label |

---

## Efficiency Nodes

**Repository**: `jags111/efficiency-nodes-comfyui`
(Originally `LucianoCirino/efficiency-nodes-comfyui`, now maintained fork)
**Install**: ComfyUI-Manager or git clone

### Purpose
Reduce node count and streamline workflows. Combines multiple operations
into single nodes with built-in caching and preview.

### Key Nodes

#### Efficient Loader
Loads Checkpoint + VAE + LoRA in one node with model caching.

| Parameter | Type | Notes |
|-----------|------|-------|
| ckpt_name | COMBO | Checkpoint selection |
| vae_name | COMBO | VAE selection (or "Baked VAE") |
| clip_skip | INT | CLIP skip layers (-1, -2, etc.) |
| lora_name | COMBO | Optional LoRA |
| lora_model_strength | FLOAT | LoRA model weight |
| lora_clip_strength | FLOAT | LoRA CLIP weight |
| positive | STRING | Positive prompt text |
| negative | STRING | Negative prompt text |
| lora_stack | LORA_STACK | Optional additional LoRAs |
| cnet_stack | CNET_STACK | Optional ControlNet stack |

Outputs: MODEL, CONDITIONING+, CONDITIONING-, LATENT, VAE, CLIP, dependencies

#### Eff. Loader SDXL (TSC_EfficientLoaderSDXL)
SDXL-specific loader with base/refiner architecture support.

| Additional Parameters | Notes |
|----------------------|-------|
| base_ckpt_name | SDXL base checkpoint |
| refiner_ckpt_name | SDXL refiner (optional) |
| positive_ascore | Aesthetic score for positive |
| negative_ascore | Aesthetic score for negative |

#### KSampler (Efficient)
Enhanced KSampler with live preview and seed management.

| Feature | Description |
|---------|-------------|
| Live Preview | Real-time denoising visualization |
| VAE Decode | Optional inline decode (skip separate node) |
| Seed Box | Dedicated seed input with increment/random |
| Script | XY Plot scripting support |

#### KSampler SDXL (Eff.)
Two-stage sampler for SDXL base + refiner in one node.

### Workflow Benefit
A typical 8-node workflow (loader + CLIP + sampler + VAE + save)
collapses to 2-3 Efficiency nodes with identical output.

---

## ComfyUI-KJNodes

**Repository**: `kijai/ComfyUI-KJNodes`
**Install**: ComfyUI-Manager or git clone
**Node Count**: 80+ nodes

### Purpose
Quality-of-life nodes for masking, list operations, conditioning
manipulation, and general workflow enhancement.

### Key Nodes

| Category | Nodes | Function |
|----------|-------|----------|
| Primitives | GetImagesFromBatchIndexed, CreateTextMask | Extended type utilities |
| Batch Ops | ImageBatchRepeatInterleaving, ConditioningMultiCombine | Batch manipulation |
| Masking | CreateShapeMask, CreateGradientMask, BatchCLIPSeg | Procedural mask generation |
| Conditioning | ConditioningSetMaskAndCombine, FlipSigmas | Advanced conditioning control |
| Scheduling | FloatSchedule, StringSchedule | Per-step value scheduling |
| Set/Get | SetNode, GetNode | Cross-graph value passing |

### Notable Utilities
- **CreateShapeMask**: Generate circle, rectangle, or polygon masks procedurally
- **CreateGradientMask**: Linear or radial gradient masks
- **GetImagesFromBatchIndexed**: Extract specific frames by index list
- **ConditioningSetMaskAndCombine**: Regional prompting helper
- **StableZero123_BatchSchedule**: Camera orbit scheduling for 3D

---

## ComfyUI-Inspire-Pack

**Repository**: `ltdrdata/ComfyUI-Inspire-Pack`
**Install**: ComfyUI-Manager or git clone

### Purpose
Extension nodes from the Impact Pack author. Focuses on regional conditioning,
prompt scheduling, wildcards, and backend optimization.

### Key Nodes

| Category | Nodes | Function |
|----------|-------|----------|
| Regional | RegionalPrompt, CombineRegionalPrompts | Region-specific prompting |
| Wildcards | WildcardEncode, WildcardProcessor | Dynamic prompt variation |
| Scheduling | PromptSchedule, ScheduleToCondition | Per-step prompt changes |
| Backend | BackendLoader, BackendCache | Model caching across runs |
| A1111 Compat | A1111PromptStyle, KSamplerAdvancedInspire | Familiar parameter names |
| Conditioning | ConditioningConcat, ConditioningCombine | Advanced conditioning ops |

### Regional Conditioning Pattern
```
RegionalPrompt("face, detailed", mask=face_mask)
  + RegionalPrompt("background, forest", mask=bg_mask)
  -> CombineRegionalPrompts
  -> KSampler
```

### Wildcard Syntax
```
{cat|dog|bird} -> randomly selects one
{2$$red|blue|green|yellow} -> selects 2 items
__animals__ -> loads from wildcard file
```

---

## ComfyUI-Advanced-ControlNet

**Repository**: `Kosinkadink/ComfyUI-Advanced-ControlNet`
**Install**: ComfyUI-Manager or git clone

### Purpose
Enhanced ControlNet with sliding window support, timestep keyframes,
per-step strength scheduling, and latent keyframe batching.

### Key Nodes
| Node | Function |
|------|----------|
| ControlNetLoaderAdvanced | Load ControlNet with advanced options |
| TimestepKeyframe | Define ControlNet strength at specific timesteps |
| LatentKeyframe | Apply different ControlNet guidance per latent batch index |
| SlidingWindowOptions | Context-window ControlNet for AnimateDiff videos |
| ControlNetApplyAdvanced | Apply with all advanced options |

### Use Case
Critical for AnimateDiff workflows where ControlNet guidance must vary
across frames (e.g., different poses per frame in a video).

---

## ComfyUI-LayerDiffuse

**Repository**: `layerdiffusion/ComfyUI-LayerDiffuse`
**Install**: ComfyUI-Manager or git clone

### Purpose
Generate images with transparent backgrounds directly from the diffusion
process. No post-processing alpha matting needed.

### Key Nodes
| Node | Function |
|------|----------|
| LayerDiffuseApply | Patch model for transparent generation |
| LayerDiffuseDecode | Decode latent to RGBA image |
| LayerDiffuseCondJoint | Joint foreground/background conditioning |

### Use Case
Product photography, compositing assets, sprite generation, sticker creation.
Works with SD1.5 and SDXL.

---

## ComfyUI-IC-Light

**Repository**: `huchenlei/ComfyUI-IC-Light-Native`
**Install**: ComfyUI-Manager or git clone

### Purpose
Relighting images using IC-Light models. Change lighting direction,
intensity, and color of existing images.

### Key Nodes
| Node | Function |
|------|----------|
| ICLightConditioning | Create conditioning with light direction |
| LoadICLightModel | Load IC-Light model weights |
| ICLightApply | Apply relighting to image |

### Use Case
Product relighting, portrait lighting adjustment, scene lighting changes.
Particularly powerful combined with LayerDiffuse for transparent+relit assets.

---

## ComfyUI_essentials

**Repository**: `cubiq/ComfyUI_essentials`
(Actively maintained fork: `comfyorg/comfyui-essentials`)
**Install**: ComfyUI-Manager or git clone

### Purpose
Essential nodes that fill gaps in ComfyUI core. Image batch operations,
math, conditional logic, masking, and debugging utilities.

### Key Nodes

| Category | Nodes | Function |
|----------|-------|----------|
| Image | ImageResize+, ImageCrop+, ImageFlip+, ImageDesaturate+ | Enhanced image ops |
| Batch | ImageListToBatch+, ImageBatchToList+, BatchCount+ | Batch conversion |
| Math | SimpleMath+, ConsoleDebug+ | Expression evaluation |
| Logic | Switch+, Compare+, DebugTensorShape+ | Flow control |
| Mask | MaskBlur+, MaskFlip+, MaskBatch+ | Mask manipulation |
| Sampling | KSamplerSelect+ (with model/sampler/scheduler selection helpers) | Sampling utilities |

### SimpleMath+ Expression Reference
Variables `a`, `b`, `c` map to the three float inputs.
```
a + b           # addition
a * 2.5         # multiplication
min(a, b)       # minimum
max(a, b, c)    # maximum
abs(a - b)      # absolute difference
a ** 0.5        # square root
round(a, 2)     # round to 2 decimal places
int(a)          # truncate to integer
a if a > b else b  # conditional (ternary)
```

---

## Quick Reference: Pack Selection Guide

| Need | Pack | Key Node |
|------|------|----------|
| Install/manage nodes | ComfyUI-Manager | Manager UI |
| Fix faces | Impact Pack | FaceDetailer |
| Text manipulation | WAS Node Suite | Text Concatenate, etc. |
| Reduce node count | Efficiency Nodes | Efficient Loader |
| Frame interpolation | Frame-Interpolation | RIFE_VFI |
| Video I/O | VideoHelperSuite | VHS_VideoCombine |
| Animate images | AnimateDiff-Evolved | ADE_AnimateDiffLoaderGen1 |
| Advanced ControlNet | Advanced-ControlNet | TimestepKeyframe |
| Transparent backgrounds | LayerDiffuse | LayerDiffuseApply |
| Relighting | IC-Light | ICLightConditioning |
| Regional prompts | Inspire-Pack | RegionalPrompt |
| Math/logic | essentials | SimpleMath+ |
| Mask generation | KJNodes | CreateShapeMask |
| Precise segmentation | segment_anything | GroundingDinoSAMSegment |

---

## Installation Best Practices

1. **Always use ComfyUI-Manager** for installation when possible
2. **Check compatibility** before installing -- some packs conflict
3. **Keep packs updated** -- Manager -> Update All periodically
4. **Disable unused packs** to reduce startup time and memory
5. **Use snapshots** before major updates for rollback capability
6. **Check VRAM requirements** -- some packs load additional models

### Common Dependency Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Red node in workflow | Missing custom node pack | Manager -> Install Missing |
| Import error on startup | Python dependency missing | Manager -> Fix (try) |
| Model not found | Model file not downloaded | Manager -> Install Models |
| CUDA out of memory | Too many model patches loaded | Disable unused packs |
| Slow startup | Too many packs installed | Disable unused packs |

### Directory Structure
```
ComfyUI/
  custom_nodes/
    ComfyUI-Manager/
    ComfyUI-AnimateDiff-Evolved/
    ComfyUI-VideoHelperSuite/
    ComfyUI-Impact-Pack/
    ComfyUI-Inspire-Pack/
    ComfyUI-Frame-Interpolation/
    ComfyUI-Advanced-ControlNet/
    ComfyUI-LayerDiffuse/
    ComfyUI-IC-Light-Native/
    ComfyUI-KJNodes/
    ComfyUI_essentials/
    was-node-suite-comfyui/
    efficiency-nodes-comfyui/
    comfyui_segment_anything/
  models/
    checkpoints/         # SD models
    vae/                 # VAE models
    loras/               # LoRA models
    controlnet/          # ControlNet models
    upscale_models/      # ESRGAN, SwinIR, etc.
    animatediff_models/  # Motion modules
    sams/                # SAM models
    grounding-dino/      # GroundingDINO models
```
