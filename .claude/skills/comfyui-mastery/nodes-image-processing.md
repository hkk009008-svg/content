# ComfyUI Image Processing Nodes Reference

## Upscaling

### Model-Based Upscaling

#### UpscaleModelLoader
Loads a super-resolution model from `ComfyUI/models/upscale_models/`.

| Parameter | Type | Notes |
|-----------|------|-------|
| model_name | COMBO | Dropdown of available upscale model files |

Output: `UPSCALE_MODEL`

#### ImageUpscaleWithModel
Applies a loaded upscale model to an image.

| Input | Type | Notes |
|-------|------|-------|
| upscale_model | UPSCALE_MODEL | From UpscaleModelLoader |
| image | IMAGE | Input image |

Output: `IMAGE` (upscaled -- dimensions multiplied by model factor)

#### Recommended Upscale Models

| Model | Factor | Best For | File Size |
|-------|--------|----------|-----------|
| RealESRGAN_x4plus | 4x | General photos, real content | ~64 MB |
| RealESRGAN_x4plus_anime_6B | 4x | Anime/illustration style | ~17 MB |
| RealESRGAN_x2plus | 2x | General, less aggressive | ~64 MB |
| 4x-UltraSharp | 4x | Sharp detail preservation | ~64 MB |
| 4x_NMKD-Siax_200k | 4x | Balanced sharpness | ~64 MB |
| SwinIR_4x | 4x | Natural textures, landscapes | ~48 MB |
| HAT_SRx4 | 4x | State-of-art quality, slow | ~85 MB |
| BSRGAN | 4x | Text, sharp edges, graphics | ~64 MB |

Place models in: `ComfyUI/models/upscale_models/`

### Pixel-Space Scaling (Built-in)

#### ImageScale
Resizes an image to exact pixel dimensions.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| image | IMAGE | -- | Input |
| upscale_method | COMBO | `nearest-exact` | `nearest-exact`, `bilinear`, `area`, `bicubic`, `lanczos` |
| width | INT | 512 | Target width |
| height | INT | 512 | Target height |
| crop | COMBO | `disabled` | `disabled`, `center` |

#### ImageScaleBy
Scales image by a multiplier factor.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| image | IMAGE | -- | Input |
| upscale_method | COMBO | `nearest-exact` | Same options as ImageScale |
| scale_by | FLOAT | 1.0 | Multiplier (2.0 = double size) |

#### ImageScaleToTotalPixels
Scales image so total pixel count reaches target, preserving aspect ratio.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| image | IMAGE | -- | Input |
| upscale_method | COMBO | `nearest-exact` | Interpolation method |
| megapixels | FLOAT | 1.0 | Target total megapixels |

### Latent-Space Scaling (Built-in)

#### LatentUpscale
Upscales latent tensors directly (before VAE decode).

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| samples | LATENT | -- | Input latent |
| upscale_method | COMBO | `nearest-exact` | Interpolation method |
| width | INT | 512 | Target width (in latent space = pixel/8) |
| height | INT | 512 | Target height |
| crop | COMBO | `disabled` | `disabled`, `center` |

#### LatentUpscaleBy
Upscales latent by a multiplier factor.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| samples | LATENT | -- | Input |
| upscale_method | COMBO | `nearest-exact` | Interpolation |
| scale_by | FLOAT | 1.5 | Multiplier |

### Hi-Res Fix Pattern (Upscale + Re-denoise)
```
KSampler (low-res) -> LatentUpscale (2x) -> KSampler (denoise 0.4-0.6) -> VAEDecode
```
This two-pass approach produces sharper, more detailed results than single-pass
generation at high resolution.

---

## Segmentation

### SAM (Segment Anything) -- comfyui_segment_anything

**Repository**: `storyicon/comfyui_segment_anything`

#### SAMModelLoader
Loads a Segment Anything model.

| Parameter | Type | Notes |
|-----------|------|-------|
| model_name | COMBO | See model options below |

Available models:
- `sam_vit_h` (2.56 GB) -- Highest quality
- `sam_vit_l` (1.25 GB) -- Good balance
- `sam_vit_b` (375 MB) -- Fastest
- `sam_hq_vit_h` (2.57 GB) -- High-quality variant
- `sam_hq_vit_l` (1.25 GB)
- `sam_hq_vit_b` (379 MB)
- `mobile_sam` (39 MB) -- Lightweight mobile version

Output: `SAM_MODEL`

#### GroundingDinoModelLoader
Loads a GroundingDINO model for text-guided object detection.

| Parameter | Type | Notes |
|-----------|------|-------|
| model_name | COMBO | `GroundingDINO_SwinT_OGC`, `GroundingDINO_SwinB` |

Output: `GROUNDING_DINO_MODEL`

#### GroundingDinoSAMSegment
Combines text-based detection (GroundingDINO) with SAM segmentation.

| Input | Type | Notes |
|-------|------|-------|
| sam_model | SAM_MODEL | From SAMModelLoader |
| grounding_dino_model | GROUNDING_DINO_MODEL | From GroundingDinoModelLoader |
| image | IMAGE | Input image |
| prompt | STRING | Text description of object to segment |
| threshold | FLOAT | Detection confidence (default 0.3) |

Outputs: `IMAGE` (segmented), `MASK`

### SAM2 (ComfyUI-SAM2)

**Repository**: `neverbiasu/ComfyUI-SAM2`

Updated SAM2 nodes with improved segmentation quality and video support.
Key nodes: `SAM2ModelLoader`, `SAM2Segmentation`, `SAM2VideoSegmentation`.

---

## Inpainting

### SetLatentNoiseMask (Built-in)
Applies a mask to a latent so KSampler only denoises the masked region.

| Input | Type | Notes |
|-------|------|-------|
| samples | LATENT | Encoded image latent |
| mask | MASK | White = inpaint region, black = keep |

Output: `LATENT` (with noise mask attached)

### VAEEncodeForInpaint (Built-in)
Encodes an image for inpainting, handling mask edge blending.

| Input | Type | Notes |
|-------|------|-------|
| pixels | IMAGE | Input image |
| vae | VAE | VAE model |
| mask | MASK | Inpaint mask |
| grow_mask_by | INT | Pixels to expand mask boundary (default 6) |

Output: `LATENT` (ready for inpaint sampling)

### InpaintModelConditioning (Built-in)
For dedicated inpainting models (e.g., sd-v1-5-inpainting). Creates
conditioning that includes the masked image information.

| Input | Type | Notes |
|-------|------|-------|
| positive | CONDITIONING | Text conditioning |
| negative | CONDITIONING | Negative conditioning |
| vae | VAE | VAE model |
| pixels | IMAGE | Original image |
| mask | MASK | Inpaint region |

Outputs: `positive` CONDITIONING, `negative` CONDITIONING, `latent` LATENT

### Inpainting Workflow Patterns

**Pattern 1: Standard Model Inpainting**
```
LoadImage -> VAEEncode -> SetLatentNoiseMask(mask) -> KSampler(denoise=0.8) -> VAEDecode
```

**Pattern 2: Dedicated Inpaint Model**
```
LoadImage + mask -> InpaintModelConditioning -> KSampler(denoise=1.0) -> VAEDecode
```

**Pattern 3: VAEEncodeForInpaint (with edge handling)**
```
LoadImage + mask -> VAEEncodeForInpaint(grow_mask_by=6) -> KSampler -> VAEDecode
```

---

## Masking (Built-in Nodes)

### Conversion

| Node | Function |
|------|----------|
| ImageToMask | Extracts a single channel (R/G/B/A) as a mask |
| MaskToImage | Converts a mask to a grayscale image |
| LoadImageMask | Loads an image file and extracts a channel as mask |

### Composition

#### MaskComposite
Combines two masks using a logical/arithmetic operation.

| Parameter | Type | Notes |
|-----------|------|-------|
| destination | MASK | Base mask |
| source | MASK | Mask to combine |
| x | INT | X offset of source |
| y | INT | Y offset of source |
| operation | COMBO | `multiply`, `add`, `subtract`, `and`, `or`, `xor` |

### Manipulation

| Node | Parameters | Function |
|------|-----------|----------|
| InvertMask | mask | Flips black/white regions |
| GrowMask | mask, expand (INT), tapered_corners (BOOL) | Expands mask boundary by N pixels |
| CropMask | mask, x, y, width, height | Crops mask to region |
| ThresholdMask | mask, value (FLOAT 0-1) | Binarizes: above threshold = white |
| FeatherMask | mask, left, top, right, bottom (INT) | Soft edges with feathering |
| MaskErode | mask, amount (INT) | Shrinks mask (morphological erosion) |
| MaskDilate | mask, amount (INT) | Grows mask (morphological dilation) |
| BlurMask | mask, amount (FLOAT) | Gaussian blur on mask edges |
| SolidMask | value (FLOAT), width, height | Creates uniform mask |

### Masquerade Nodes (masquerade-nodes-comfyui)

**Repository**: `BadCafeCode/masquerade-nodes-comfyui`

Extended mask operations: `MaskByText`, `MaskMorphology`, `CombineMasks`,
`MaskToRegion`, `CutByMask`, `PasteByMask`, `SegmentAnything` (built-in SAM).

---

## Image Operations (Built-in)

### Compositing

#### ImageComposite (ImageCompositeMasked)
Overlays one image onto another using a mask.

| Input | Type | Notes |
|-------|------|-------|
| destination | IMAGE | Background image |
| source | IMAGE | Foreground image |
| mask | MASK | Transparency mask for source |
| x | INT | X offset |
| y | INT | Y offset |
| resize_source | BOOL | Auto-resize source to fit |

#### ImageBlend
Blends two images together with adjustable opacity.

| Input | Type | Notes |
|-------|------|-------|
| image1 | IMAGE | First image |
| image2 | IMAGE | Second image |
| blend_factor | FLOAT | 0.0 = image1, 1.0 = image2 |
| blend_mode | COMBO | `normal`, `multiply`, `screen`, `overlay`, `soft_light` |

### Cropping & Padding

| Node | Key Parameters | Function |
|------|---------------|----------|
| ImageCrop | image, width, height, x, y | Crops image to specified region |
| ImagePadForOutpaint | image, left, top, right, bottom | Adds padding for outpainting with feathered edges |

### Batch Operations

| Node | Function |
|------|----------|
| ImageBatch | Concatenates two IMAGE tensors along batch dimension |
| ImageFromBatch | Extracts a range of images from a batch (batch_index, length) |
| RepeatImageBatch | Repeats an image N times as a batch |

### Filters & Adjustments

| Node | Key Parameters | Function |
|------|---------------|----------|
| ImageSharpen | sharpen_radius, sigma, alpha | Unsharp mask sharpening |
| ImageBlur | blur_radius, sigma | Gaussian blur |
| ImageInvert | image | Inverts all pixel values |
| ImageQuantize | image, colors (INT), dither | Reduces color palette |

### Color & Channel

| Node | Function |
|------|----------|
| ImageToMask | Extract R, G, B, or A channel |
| SplitImageWithAlpha | Separates RGB and alpha |
| JoinImageWithAlpha | Combines RGB image with alpha mask |

---

## Upscaling Workflow Recommendations

### For Photorealistic Content
```
ImageUpscaleWithModel (RealESRGAN_x4plus)
  -> ImageScale (to exact target dimensions)
```

### For Anime/Illustration
```
ImageUpscaleWithModel (RealESRGAN_x4plus_anime_6B)
  -> ImageSharpen (light, sigma=0.5)
```

### For Maximum Quality (Two-Pass)
```
KSampler (512x512) -> LatentUpscale (2x to 1024x1024)
  -> KSampler (denoise=0.45, steps=20)
  -> VAEDecode
  -> ImageUpscaleWithModel (4x-UltraSharp)
  -> ImageScale (to final resolution)
```

### For Video Frames
```
[Frame batch]
  -> ImageUpscaleWithModel (SwinIR -- preserves temporal consistency)
  -> ImageScale (normalize to exact dimensions)
  -> VHS_VideoCombine
```

### Interpolation Method Selection

| Method | Best For |
|--------|----------|
| nearest-exact | Pixel art, hard edges, no blending |
| bilinear | Fast, acceptable for most cases |
| bicubic | Good quality, slight softening |
| lanczos | Best quality for downscaling |
| area | Best for significant downscaling |
