# ComfyUI ControlNet & Preprocessor Nodes Reference

Complete reference for core ControlNet nodes, T2I-Adapter, and comfyui_controlnet_aux preprocessors.

---

## Core ControlNet Nodes (Built-in ComfyUI)

### ControlNetLoader
Loads a ControlNet or T2I-Adapter model from `ComfyUI/models/controlnet/`.

| Input | Type | Description |
|-------|------|-------------|
| control_net_name | COMBO | Model filename (.safetensors or .pth) |

| Output | Type |
|--------|------|
| CONTROL_NET | Loaded ControlNet/T2I-Adapter model |

**Note:** This single loader handles both ControlNet and T2I-Adapter models. Place all model files
in the same `models/controlnet/` directory.

### DiffControlNetLoader
Loads a diff-based ControlNet model that requires a base model reference.

| Input | Type | Description |
|-------|------|-------------|
| model | MODEL | Base diffusion model (needed for diff models) |
| control_net_name | COMBO | Diff ControlNet filename |

### ControlNetApply
Basic ControlNet conditioning application.

| Input | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| conditioning | CONDITIONING | - | - | Positive or negative conditioning |
| control_net | CONTROL_NET | - | - | Loaded ControlNet model |
| image | IMAGE | - | - | Preprocessed control image |
| strength | FLOAT | 1.0 | 0.0-10.0 | Conditioning intensity |

| Output | Type |
|--------|------|
| CONDITIONING | Modified conditioning with ControlNet applied |

### ControlNetApplyAdvanced
Adds timestep control for when the ControlNet activates during sampling.

| Input | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| positive | CONDITIONING | - | - | Positive conditioning |
| negative | CONDITIONING | - | - | Negative conditioning |
| control_net | CONTROL_NET | - | - | Loaded ControlNet model |
| image | IMAGE | - | - | Preprocessed control image |
| strength | FLOAT | 1.0 | 0.0-10.0 | Conditioning intensity |
| start_percent | FLOAT | 0.0 | 0.0-1.0 | Start of effect (% of sampling steps) |
| end_percent | FLOAT | 1.0 | 0.0-1.0 | End of effect (% of sampling steps) |
| vae | VAE | optional | - | VAE for image encoding (if needed) |

### ControlNetApplySD3
ControlNet application node for SD3 / Flux architectures. Conditions both positive and negative
prompts simultaneously.

| Input | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| positive | CONDITIONING | - | - | Positive conditioning |
| negative | CONDITIONING | - | - | Negative conditioning |
| control_net | CONTROL_NET | - | - | ControlNet model |
| vae | VAE | - | - | VAE model (required for SD3) |
| image | IMAGE | - | - | Control image |
| strength | FLOAT | 1.0 | 0.0-10.0 | Conditioning intensity |
| start_percent | FLOAT | 0.0 | 0.0-1.0 | Start timestep |
| end_percent | FLOAT | 1.0 | 0.0-1.0 | End timestep |

---

## T2I-Adapter

T2I-Adapter is a lightweight alternative to ControlNet (~77M params vs ~361M for ControlNet).
About 3x faster inference with smaller file sizes (~300MB). Loaded via the same ControlNetLoader.

### Usage Pattern
T2I-Adapter models are applied with the same ControlNetApply / ControlNetApplyAdvanced nodes
as regular ControlNet. No separate adapter-specific nodes needed in core ComfyUI.

### Key Differences from ControlNet
| Aspect | ControlNet | T2I-Adapter |
|--------|-----------|-------------|
| Parameters | ~361M | ~77M |
| File size | ~1.5 GB | ~300 MB |
| Speed | Baseline | ~3x faster |
| Quality | Higher ceiling | Slightly lower |
| Loader | ControlNetLoader | ControlNetLoader (same) |
| Apply node | ControlNetApply* | ControlNetApply* (same) |

---

## Preprocessors (comfyui_controlnet_aux by Fannovel16)

59 preprocessor nodes. All share a common `resolution` parameter (default: 512, range: 64-2048, step: 64).
Higher resolution = more detail but slower processing.

### AIO_Preprocessor (All-In-One)
Universal preprocessor that wraps all individual preprocessors behind a single dropdown.

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| image | IMAGE | - | Input image |
| preprocessor | COMBO | - | Select any preprocessor type |
| resolution | INT | 512 | Processing resolution |

### Edge Detection

| Node | ControlNet Model | Best For |
|------|-----------------|----------|
| CannyEdgePreprocessor | control_v11p_sd15_canny | Sharp edges, architectural, hard surfaces |
| HEDPreprocessor | control_v11p_sd15_softedge | Soft edges, organic shapes |
| PiDiNetPreprocessor | control_v11p_sd15_softedge | Lightweight soft edge alternative |
| ScribblePreprocessor | control_v11p_sd15_scribble | Hand-drawn sketch style |
| MLSDPreprocessor | control_v11p_sd15_mlsd | Straight lines only (architecture, rooms) |

**CannyEdgePreprocessor parameters:**

| Input | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| image | IMAGE | - | - | Input image |
| low_threshold | INT | 100 | 0-255 | Lower edge detection threshold |
| high_threshold | INT | 200 | 0-255 | Upper edge detection threshold |
| resolution | INT | 512 | 64-2048 | Processing resolution |

### Depth Estimation

| Node | ControlNet Model | Best For |
|------|-----------------|----------|
| DepthAnythingPreprocessor | control_v11f1p_sd15_depth | General depth, fast |
| DepthAnythingV2Preprocessor | control_v11f1p_sd15_depth | Improved depth accuracy |
| MiDaSDepthMapPreprocessor | control_v11f1p_sd15_depth | Classic depth estimation |
| ZoeDepthMapPreprocessor | control_v11f1p_sd15_depth | High-quality metric depth |

**DepthAnythingV2Preprocessor parameters:**

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| image | IMAGE | - | Input image |
| ckpt_name | COMBO | depth_anything_v2_vitl.pth | Model checkpoint |
| resolution | INT | 512 | Processing resolution |

### Pose Estimation

| Node | ControlNet Model | Best For |
|------|-----------------|----------|
| OpenPosePreprocessor | control_v11p_sd15_openpose | Human body + face + hands |
| DWPosePreprocessor | control_v11p_sd15_openpose | Improved accuracy, GPU-accelerated |
| AnimalPosePreprocessor | (animal-specific) | Animal body pose detection |

**DWPosePreprocessor parameters:**

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| image | IMAGE | - | Input image |
| detect_hand | COMBO | enable | Enable hand keypoint detection |
| detect_body | COMBO | enable | Enable body keypoint detection |
| detect_face | COMBO | enable | Enable face keypoint detection |
| resolution | INT | 512 | Processing resolution |
| bbox_detector | COMBO | yolox_l.onnx | Bounding box detection model |
| pose_estimator | COMBO | dw-ll_ucoco_384.onnx | Pose estimation model |

### Line Art

| Node | ControlNet Model | Best For |
|------|-----------------|----------|
| LineArtPreprocessor | control_v11p_sd15_lineart | Realistic line extraction |
| LineArtAnimePreprocessor | control_v11p_sd15_lineart_anime | Anime-style line art |
| MangaLinePreprocessor | control_v11p_sd15_lineart | Manga screentone + lines |

### Normal Maps

| Node | ControlNet Model | Best For |
|------|-----------------|----------|
| NormalBaePreprocessor | control_v11p_sd15_normalbae | Normal map from photo |
| BAE_NormalMapPreprocessor | control_v11p_sd15_normalbae | Alternative normal estimation |

### Semantic Segmentation

| Node | ControlNet Model | Best For |
|------|-----------------|----------|
| SegmentAnythingPreprocessor | control_v11p_sd15_seg | SAM-based universal segmentation |
| OneFormerADE20KPreprocessor | control_v11p_sd15_seg | Scene parsing (150 categories) |
| UniformerPreprocessor | control_v11p_sd15_seg | Efficient scene segmentation |

### Face & Body

| Node | ControlNet Model | Best For |
|------|-----------------|----------|
| MediaPipeFaceMeshPreprocessor | (face-specific CN) | 468-point facial mesh |

### Utility Preprocessors

| Node | ControlNet Model | Best For |
|------|-----------------|----------|
| TilePreprocessor | control_v11f1e_sd15_tile | Upscaling, detail enhancement |
| ColorPreprocessor | (t2i-adapter color) | Color palette transfer |
| ShufflePreprocessor | control_v11e_sd15_shuffle | Style/texture shuffle |
| InpaintPreprocessor | control_v2p_sd15_inpaint | Inpainting mask preparation |

**TilePreprocessor parameters:**

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| image | IMAGE | - | Input image |
| pyrUp_iters | INT | 3 | Pyramid upscaling iterations (blur level) |
| resolution | INT | 512 | Processing resolution |

---

## Strength & Timing Tuning Guide

### Strength Parameter

| Range | Effect | Use Case |
|-------|--------|----------|
| 0.0-0.3 | Subtle hint | Light guidance, creative freedom |
| 0.3-0.6 | Moderate | Balanced control and creativity |
| 0.6-0.8 | Strong | Tight adherence with some variation |
| 0.8-1.0 | Very strong | Near-exact reproduction of control image |
| 1.0-2.0 | Overpowered | Can cause artifacts, use with caution |

**General rule:** Start at 0.7-0.8, adjust based on results. Use lower values for multiple
stacked ControlNets to avoid conflicts.

### start_percent / end_percent Timing

| Pattern | start | end | Effect |
|---------|-------|-----|--------|
| Full duration | 0.0 | 1.0 | Active entire generation (default) |
| Early only | 0.0 | 0.4 | Sets composition, allows detail freedom |
| Late only | 0.5 | 1.0 | Refines details without affecting layout |
| Middle burst | 0.2 | 0.7 | Balanced structural + detail control |

**Key insight:** Early steps (0.0-0.3) determine overall composition and structure.
Mid steps (0.3-0.7) define features and shapes. Late steps (0.7-1.0) refine details and textures.

---

## Multi-ControlNet Stacking Patterns

### Chaining Method (Native ComfyUI)
Chain conditioning outputs: the CONDITIONING output of one ControlNetApplyAdvanced feeds
into the next ControlNetApplyAdvanced node as input conditioning.

```
CLIP Text Encode -> ControlNetApply (Depth) -> ControlNetApply (Canny) -> KSampler
```

### Common Effective Combinations

| Combination | Strengths | Recommended Settings |
|-------------|-----------|---------------------|
| Depth + Canny | 3D structure + sharp edges | Depth: 0.6, Canny: 0.5 |
| Pose + Depth | Character pose + scene depth | Pose: 0.8, Depth: 0.5 |
| Pose + Canny | Body position + edge detail | Pose: 0.7, Canny: 0.4 |
| Lineart + Color | Line structure + color palette | Lineart: 0.7, Color: 0.5 |
| Tile + Depth | Upscale detail + spatial coherence | Tile: 0.6, Depth: 0.4 |
| Depth + Normal | Full 3D surface information | Depth: 0.6, Normal: 0.4 |

### Multi-Layer Depth Stacking
Separate control images for foreground, mid-ground, and background with different strengths:

| Layer | Strength | start_percent | end_percent | Purpose |
|-------|----------|---------------|-------------|---------|
| Foreground | 0.9 | 0.0 | 1.0 | Tight subject control |
| Mid-ground | 0.6 | 0.0 | 0.8 | Moderate scene structure |
| Background | 0.3 | 0.0 | 0.5 | Loose environment hint |

This pattern reportedly achieves ~94% usable results with tight foreground control and
pleasant background variation.

### Stacking Rules of Thumb

1. **Total combined strength** should generally stay under 2.0 across all ControlNets.
   Higher combined values cause artifacts and over-constrained outputs.

2. **Use similar strengths** for ControlNets controlling different regions. If one is
   significantly stronger, it suppresses the other.

3. **Complementary types** work better than redundant types. Depth + Canny = good.
   Canny + HED = redundant (both are edges).

4. **Timing separation** can resolve conflicts. Apply structural controls (depth, pose) in
   early steps and detail controls (canny, lineart) in later steps.

5. **Start with single ControlNet**, verify it works, then add the second. Debug one at a time.

---

## ControlNet Models Quick Reference

### SD 1.5 Models
| Model | Preprocessor | Use Case |
|-------|-------------|----------|
| control_v11p_sd15_canny | Canny | Edge detection |
| control_v11p_sd15_depth / control_v11f1p_sd15_depth | Depth* | Depth maps |
| control_v11p_sd15_openpose | OpenPose/DWPose | Body/hand/face pose |
| control_v11p_sd15_softedge | HED/PiDiNet | Soft edges |
| control_v11p_sd15_scribble | Scribble | Sketch-based |
| control_v11p_sd15_lineart | LineArt | Line extraction |
| control_v11p_sd15_lineart_anime | LineArtAnime | Anime lines |
| control_v11p_sd15_mlsd | MLSD | Straight lines |
| control_v11p_sd15_normalbae | NormalBae | Surface normals |
| control_v11p_sd15_seg | Segment* | Segmentation |
| control_v11f1e_sd15_tile | Tile | Upscale/detail |
| control_v11e_sd15_shuffle | Shuffle | Style transfer |
| control_v2p_sd15_inpaint | Inpaint | Inpainting |

### SDXL Models
Most SD 1.5 ControlNet types have SDXL equivalents. Common sources:
diffusers/controlnet-canny-sdxl-1.0, diffusers/controlnet-depth-sdxl-1.0, etc.

### Flux Models
Flux ControlNet models are emerging. Check for Flux-specific models from
InstantX, Shakker-Labs, or the official Flux repositories.
