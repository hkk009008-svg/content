# ComfyUI Face & Identity Preservation Nodes Reference

Complete reference for face identity nodes: PuLID, IP-Adapter, InstantID, ReActor, and InsightFace.

---

## PuLID (comfyui-pulid by cubiq)

Pure and Lightning ID customization. Injects identity embeddings at generation time via
cross-attention, producing identity-consistent images without post-processing.

### PulidModelLoader
Loads a pre-trained PuLID model from `ComfyUI/models/pulid/`.

| Input | Type | Description |
|-------|------|-------------|
| pulid_file | COMBO | Model filename. Primary: `pulid_flux_v0.9.1.safetensors` |

| Output | Type |
|--------|------|
| PULID | PULID model tuple (projection layers + adapter weights) |

### PulidInsightFaceLoader
Loads the InsightFace analysis model used by PuLID for face detection and embedding.

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| provider | COMBO | CPU | Execution provider: `CUDA`, `CPU`, `CoreML` |

| Output | Type |
|--------|------|
| INSIGHTFACE | InsightFace analysis model |

### PulidEvaClipLoader
Loads the EVA-CLIP model used for visual feature extraction.

| Output | Type |
|--------|------|
| EVA_CLIP | EVA-CLIP model for visual encoding |

### ApplyPulid
Standard node for applying PuLID identity conditioning with preset methods.

| Input | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| model | MODEL | - | - | Base diffusion model |
| pulid | PULID | - | - | Loaded PuLID model |
| eva_clip | EVA_CLIP | - | - | EVA-CLIP encoder |
| face_analysis | INSIGHTFACE | - | - | InsightFace model |
| image | IMAGE | - | - | Reference face image |
| weight | FLOAT | 1.0 | -1.0 to 5.0 | Identity conditioning strength |
| start_at | FLOAT | 0.0 | 0.0-1.0 | Start timestep (% of sampling) |
| end_at | FLOAT | 1.0 | 0.0-1.0 | End timestep (% of sampling) |
| method | COMBO | fidelity | fidelity, style | fidelity = closer likeness; style = more creative freedom |

### ApplyPulidAdvanced
Fine-grained control over projection and fidelity settings.

| Input | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| weight | FLOAT | 1.0 | -1.0 to 5.0 | Identity conditioning strength |
| projection | COMBO | ortho_v2 | ortho_v2, ortho, none | Embedding projection method |
| fidelity | INT | 8 | 0-32 | Num zero tensors added; lower = higher resemblance |
| noise | FLOAT | 0.0 | -1.0 to 1.0 | Noise injection into embeddings |
| start_at | FLOAT | 0.0 | 0.0-1.0 | Start timestep |
| end_at | FLOAT | 1.0 | 0.0-1.0 | End timestep |
| attn_mask | MASK | optional | - | Region mask for selective application |

**Note:** `ortho_v2` with `fidelity: 8` is equivalent to the standard node's `fidelity` method.

### PuLID Models
| Model | Architecture | Notes |
|-------|-------------|-------|
| pulid_flux_v0.9.1.safetensors | Flux-based | Primary recommended model |
| pulid_v1.1.safetensors | SD1.5/SDXL | Legacy support |

---

## IP-Adapter (ComfyUI_IPAdapter_plus by cubiq)

Image Prompt Adapter. Conditions generation on reference images via decoupled cross-attention.
Supports style transfer, composition transfer, and face identity (FaceID variants).

### IPAdapterModelLoader
Loads IP-Adapter model weights from `ComfyUI/models/ipadapter/`.

| Input | Type | Description |
|-------|------|-------------|
| ipadapter_file | COMBO | Model file (e.g., `ip-adapter-plus_sdxl_vit-h.safetensors`) |

### IPAdapterUnifiedLoader
All-in-one loader that auto-selects the correct IP-Adapter model, CLIP vision, and LoRA.

| Input | Type | Description |
|-------|------|-------------|
| model | MODEL | Base diffusion model |
| preset | COMBO | Model preset: LIGHT, STANDARD, VIT-G, PLUS, PLUS FACE, FULL FACE, FACEID, FACEID PLUS, FACEID PORTRAIT |

| Output | Type |
|--------|------|
| MODEL | Patched model |
| IPADAPTER | Loaded adapter |

### IPAdapterApply (IPAdapter)
Basic IP-Adapter application node.

| Input | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| weight | FLOAT | 1.0 | -1.0 to 3.0 | Adapter influence strength |
| start_at | FLOAT | 0.0 | 0.0-1.0 | Start timestep |
| end_at | FLOAT | 1.0 | 0.0-1.0 | End timestep |
| image | IMAGE | - | - | Reference image |

### IPAdapterAdvanced
Full-featured node with weight type scheduling and embeds manipulation.

| Input | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| weight | FLOAT | 1.0 | -1.0 to 5.0 | Adapter strength |
| weight_type | COMBO | linear | see table | How weight distributes across layers |
| start_at | FLOAT | 0.0 | 0.0-1.0 | Start timestep |
| end_at | FLOAT | 1.0 | 0.0-1.0 | End timestep |
| image | IMAGE | - | - | Reference image |
| image_negative | IMAGE | optional | - | Negative reference (steer away from) |
| attn_mask | MASK | optional | - | Region mask |
| clip_vision | CLIP_VISION | optional | - | Override CLIP vision model |

**Weight Types:**

| Weight Type | Behavior |
|-------------|----------|
| linear | Even influence across all layers |
| ease in | Gradual increase from start |
| ease out | Strong start, tapers off |
| ease in-out | Mild start/end, peak in middle |
| reverse in-out | Strong start/end, weak middle |
| weak input | Reduced influence on early layers |
| weak output | Reduced influence on late layers |
| weak middle | Reduced influence on middle layers |
| strong middle | Boosted influence on middle layers |
| style transfer | Optimized for style-only transfer |
| composition | Transfers layout/composition only |
| strong style transfer | Aggressive style transfer |
| style and composition | Combined style + layout |
| style transfer precise | Fine-tuned style (SDXL) |
| composition precise | Fine-tuned composition (SDXL) |

### IPAdapterBatch
Processes multiple images in batch mode for animation or multi-reference workflows.

### IPAdapterFaceID
Integrates InsightFace embeddings for identity-focused conditioning.

| Input | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| weight | FLOAT | 1.0 | -1.0 to 3.0 | Adapter strength |
| weight_faceidv2 | FLOAT | 1.0 | -1.0 to 5.0 | FaceID v2 specific weight |
| weight_type | COMBO | linear | all types | Weight scheduling |
| image | IMAGE | - | - | Reference face image |
| insightface | INSIGHTFACE | - | - | InsightFace model |

### IPAdapterFaceIDPlus
Enhanced FaceID with combined CLIP vision + InsightFace embeddings for better likeness.

Adds `image_negative` and `clip_vision` inputs on top of FaceID parameters.

### IPAdapterStyleComposition
Dedicated node for separating and controlling style vs composition transfer independently.

| Input | Type | Description |
|-------|------|-------------|
| weight_style | FLOAT | Style transfer strength |
| weight_composition | FLOAT | Composition transfer strength |
| image_style | IMAGE | Style reference |
| image_composition | IMAGE | Composition/layout reference |

### IPAdapterEncoder
Encodes reference images into IP-Adapter embedding space.

| Input | Type | Description |
|-------|------|-------------|
| image | IMAGE | Image to encode |
| ipadapter | IPADAPTER | Loaded adapter model |
| clip_vision | CLIP_VISION | CLIP vision model |

| Output | Type |
|--------|------|
| EMBEDS | Encoded image embeddings |

### IPAdapterCombineEmbeds
Merges multiple encoded embeddings into a single unified embedding.

| Input | Type | Description |
|-------|------|-------------|
| embed1 | EMBEDS | First embedding |
| embed2 | EMBEDS | Second embedding |
| method | COMBO | Combination method: concat, add, average |

---

## InstantID (ComfyUI_InstantID by cubiq)

Combines InsightFace identity embeddings with ControlNet facial keypoint conditioning
for strong identity preservation with structural control. Status: maintenance-only as of 2025.

### InstantIDModelLoader
Loads the InstantID cross-attention model.

| Input | Type | Description |
|-------|------|-------------|
| instantid_file | COMBO | Model file from `ComfyUI/models/instantid/` |

### InstantIDFaceAnalysis
Loads and configures InsightFace for face detection and embedding extraction.

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| provider | COMBO | CPU | CUDA, CPU, or CoreML |

### ApplyInstantID
Standard application node. Automatically injects 35% noise for natural variation.

| Input | Type | Default | Range | Description |
|-------|------|---------|-------|-------------|
| model | MODEL | - | - | Base model |
| instantid | INSTANTID | - | - | Loaded InstantID model |
| insightface | INSIGHTFACE | - | - | Face analysis model |
| control_net | CONTROL_NET | - | - | ControlNet model (required) |
| image | IMAGE | - | - | Reference face image |
| ip_weight | FLOAT | 1.0 | 0.0-3.0 | Identity embedding strength |
| cn_strength | FLOAT | 1.0 | 0.0-10.0 | ControlNet conditioning strength |
| start_at | FLOAT | 0.0 | 0.0-1.0 | Start timestep |
| end_at | FLOAT | 1.0 | 0.0-1.0 | End timestep |

**Important:** InstantID requires a ControlNet model for facial keypoint conditioning.
Use the dedicated InstantID ControlNet model (not a generic one).

### ApplyInstantIDAdvanced
Exposes noise injection control and additional fine-tuning parameters.

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| noise | FLOAT | 0.35 | Noise injection amount (0 = no noise) |
| All standard ApplyInstantID inputs | | | |

### ApplyInstantIDControlNet
Standalone ControlNet integration node for InstantID facial keypoints.

### FaceKeypointsPreprocessor
Extracts facial keypoints for ControlNet conditioning from reference images.

---

## ReActor (ComfyUI-ReActor by Gourieff)

Post-process face swapping using InsightFace detection + inswapper models.
Operates on generated/existing images (not during generation).

### ReActorFaceSwap
Core face swap node.

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| input_image | IMAGE | - | Target image (faces to replace) |
| source_image | IMAGE | - | Source image (face to use) |
| input_faces_index | STRING | "0" | Comma-separated target face indices |
| source_faces_index | STRING | "0" | Comma-separated source face indices |
| console_log_level | COMBO | 1 | Logging verbosity (0-2) |
| face_restore_model | COMBO | none | Restoration model to apply |
| face_restore_visibility | FLOAT | 1.0 | Restoration blend (0-1) |
| codeformer_weight | FLOAT | 0.5 | CodeFormer fidelity (0=quality, 1=fidelity) |
| detect_gender_input | COMBO | no | Filter input faces by gender |
| detect_gender_source | COMBO | no | Filter source faces by gender |
| input_faces_order | COMBO | left-right | Face processing order |
| source_faces_order | COMBO | left-right | Source face selection order |

### ReActorFaceSwapOpt (OPTIONS variant)
Enhanced node with additional optional inputs for masks, face models, and advanced settings.

### ReActorRestoreFace
Standalone face restoration node (usable independently of face swap).

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| image | IMAGE | - | Image to restore |
| face_restore_model | COMBO | - | Model: GFPGANv1.4, CodeFormer, GPEN-BFR-512 |
| visibility | FLOAT | 1.0 | Restoration intensity (0-1) |
| codeformer_weight | FLOAT | 0.5 | CodeFormer fidelity parameter |

**Face Restoration Models:**

| Model | File | Strengths |
|-------|------|-----------|
| GFPGAN v1.4 | GFPGANv1.4.pth | Fast, good general restoration |
| CodeFormer | codeformer-v0.1.0.pth | Superior quality, adjustable fidelity |
| GPEN-BFR-512 | GPEN-BFR-512.onnx | ONNX-based, balanced quality |

### ReActorBuildFaceModel
Creates a reusable face model from a reference image saved as `.safetensors`.

| Input | Type | Description |
|-------|------|-------------|
| image | IMAGE | Face reference image |
| face_index | INT | Which face to capture (if multiple) |

| Output | Type |
|--------|------|
| FACE_MODEL | Serialized face embedding |

Saved to `ComfyUI/models/reactor/faces/` as safetensors files.

### ReActorLoadFaceModel
Loads a previously saved face model file.

| Input | Type | Description |
|-------|------|-------------|
| face_model | COMBO | Safetensors file from reactor/faces/ |

### ReActorOptions
Configuration node for advanced face swap parameters. Feeds into ReActorFaceSwapOpt.

---

## InsightFace Nodes

Used by PuLID, InstantID, IP-Adapter FaceID, and ReActor for face detection and embedding.

### InsightFaceLoader
Loads the InsightFace analysis pipeline.

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| provider | COMBO | CPU | CUDA (GPU), CPU, CoreML (Apple) |

**Performance:** CUDA provider is significantly faster but requires GPU memory.
CPU works universally but is slower. CoreML is Apple Silicon optimized.

| Output | Type |
|--------|------|
| INSIGHTFACE | Loaded analysis model |

### InsightFaceAnalysis
Performs face detection, alignment, and embedding extraction on input images.
Used internally by the identity nodes above; rarely connected directly.

---

## Comparison Table

| Feature | PuLID | IP-Adapter FaceID | InstantID | ReActor |
|---------|-------|-------------------|-----------|---------|
| **Method** | Generation-time cross-attention | Generation-time decoupled cross-attention | Generation-time cross-attention + ControlNet | Post-process face swap |
| **When Applied** | During denoising | During denoising | During denoising | After image generation |
| **Identity Accuracy** | Highest (~91%) | Good (~79%) | High (~84%) | Very high (direct swap) |
| **VRAM Usage** | ~10.2 GB | ~7.8 GB | ~8.5 GB | ~4-6 GB |
| **Speed** | Slowest (~35s) | Fastest (~25s) | Moderate (~28s) | Fast (post-process) |
| **Expression Freedom** | Most restricted | Most flexible | Balanced | Source expression |
| **Pose Variation** | Good | Excellent | Good (ControlNet constrained) | Limited (face region only) |
| **Style Adaptability** | Via method param | Via weight_type | Moderate | None (pixel-level swap) |
| **ControlNet Required** | No | No | Yes (mandatory) | No |
| **Multi-face** | Single | Single/Batch | Single | Multi-face indexing |
| **Architecture** | Flux/SD | SD1.5/SDXL/Flux | SD1.5/SDXL | Model-agnostic |
| **Best For** | Max identity fidelity, portraits | Style + identity, creative work | Structured identity + pose | Quick swaps, video frames |
| **Face Restoration** | N/A (generation quality) | N/A | N/A | Built-in (CodeFormer/GFPGAN) |

### When to Use Each

- **PuLID**: Professional portraits requiring maximum likeness. Accept slower speed and higher VRAM for best identity accuracy.
- **IP-Adapter FaceID**: Creative workflows combining identity with style transfer. Fastest option with most artistic flexibility.
- **InstantID**: When you need identity preservation with structural/pose control via ControlNet. Good balance of quality and control.
- **ReActor**: Post-generation face replacement. Best for batch processing, video frames, or when generation-time methods are insufficient. Combine with CodeFormer for quality restoration.
- **Combined approach**: Use generation-time method (PuLID/InstantID) for base identity, then ReActor + FaceDetailer for refinement on problem areas.

---

## Common Workflow Patterns

### Single Identity (PuLID)
```
PulidModelLoader -> ApplyPulid
PulidInsightFaceLoader -> ApplyPulid
PulidEvaClipLoader -> ApplyPulid
LoadImage (ref face) -> ApplyPulid
KSampler -> ...
```

### Style + Identity (IP-Adapter)
```
IPAdapterUnifiedLoader (FACEID PLUS) -> IPAdapterAdvanced
LoadImage (ref face) -> IPAdapterAdvanced
weight_type: "style transfer" for style, "linear" for identity
```

### Structured Identity (InstantID)
```
InstantIDModelLoader -> ApplyInstantID
InstantIDFaceAnalysis -> ApplyInstantID
ControlNetLoader (instantid CN) -> ApplyInstantID
LoadImage (ref face) -> ApplyInstantID
```

### Post-Process Swap (ReActor)
```
Generated Image -> ReActorFaceSwap
LoadImage (source face) -> ReActorFaceSwap
ReActorFaceSwap -> ReActorRestoreFace (CodeFormer)
```
