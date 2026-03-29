# ComfyUI Utility & Flow Control Nodes Reference

## Primitives (Built-in)

### PrimitiveNode
A universal widget node that outputs a single typed value. Right-click
to set the output type. Useful for sharing one value across multiple inputs.

Supported types: INT, FLOAT, STRING, COMBO (dropdown selection).

### Constant Value Nodes

| Node | Output Type | Notes |
|------|------------|-------|
| INT (from various packs) | INT | Integer constant with min/max/step |
| FLOAT (from various packs) | FLOAT | Decimal constant |
| STRING (from various packs) | STRING | Text constant, multiline option |
| BOOLEAN (from various packs) | BOOLEAN | True/false toggle |

### Note
A text-only node for adding comments/documentation to workflows.
Has no inputs or outputs. Purely visual annotation.

---

## Logic & Math

### SimpleMath+ (ComfyUI_essentials)
Evaluates mathematical expressions using Python AST.

| Input | Type | Notes |
|-------|------|-------|
| value | FLOAT | Input `a` |
| value | FLOAT | Input `b` (optional) |
| value | FLOAT | Input `c` (optional) |
| expression | STRING | Math expression using a, b, c |

Example expressions: `a * 2 + b`, `min(a, b)`, `a ** 0.5`, `round(a / b, 2)`

Supports: `+`, `-`, `*`, `/`, `//`, `%`, `**`, `abs()`, `min()`, `max()`,
`round()`, `int()`, `float()`, `sqrt()` (via `** 0.5`).

Output: `FLOAT`

### FloatMath / IntMath (various packs)
Simpler operation-based math nodes.

| Parameter | Options |
|-----------|---------|
| operation | `add`, `subtract`, `multiply`, `divide`, `power`, `min`, `max`, `modulo` |
| a | FLOAT/INT |
| b | FLOAT/INT |

### Compare / Switch / Conditional (ComfyUI_essentials)

#### ConditioningSwitch+ / ImageSwitch+ / LatentSwitch+
Routes one of two inputs to output based on a boolean condition.

| Input | Type | Notes |
|-------|------|-------|
| input_a | varies | First option |
| input_b | varies | Second option |
| boolean | BOOL | true = input_a, false = input_b |

Available switch variants for most ComfyUI types: IMAGE, LATENT,
CONDITIONING, MODEL, VAE, CLIP, STRING, INT, FLOAT.

### MathExpression (WAS Node Suite)
Similar to SimpleMath but with additional functions and string formatting.

---

## Flow Control (Built-in)

### Reroute
A pass-through node that re-routes connections for cleaner graph layout.
Accepts any type, outputs the same value unchanged.
Essential for organizing complex workflows -- route long connections through
reroute nodes to avoid visual clutter.

### RerouteTextForEncoding
Specialized reroute for text/string connections. Passes STRING type through.

### PreviewImage
Displays an image inline in the workflow graph. Does not save to disk.
Essential debugging tool to verify intermediate results.

| Input | Type | Notes |
|-------|------|-------|
| images | IMAGE | Any image tensor |

### SaveImage
Saves an image to the output directory with a filename prefix.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| images | IMAGE | -- | Input |
| filename_prefix | STRING | `ComfyUI` | Prefix for saved files |

### Execution Control

#### Mute / Bypass
Right-click any node -> Mute: Node is skipped entirely.
Right-click any node -> Bypass: Node passes inputs through unchanged.
These are UI features, not separate nodes.

#### Group Nodes
Select multiple nodes -> Right-click -> Group: Creates a visual grouping.
Groups can be collapsed, colored, and labeled for organization.

---

## Conversion (Built-in)

### Type Conversion Nodes

| Node | From | To | Notes |
|------|------|----|-------|
| ImageToMask | IMAGE | MASK | Extracts R, G, B, or A channel |
| MaskToImage | MASK | IMAGE | Converts mask to grayscale image |
| LatentToImage | -- | -- | Not built-in; use VAEDecode instead |
| SplitImageWithAlpha | IMAGE (RGBA) | IMAGE + MASK | Separates alpha channel |
| JoinImageWithAlpha | IMAGE + MASK | IMAGE (RGBA) | Combines image with alpha |

### String Operations (from custom packs)

| Node (WAS Suite) | Function |
|------------------|----------|
| Text Concatenate | Joins multiple strings |
| Text Multiline | Multi-line text input |
| Text Random Line | Selects random line from text |
| Text Find and Replace | String substitution |
| Text String Truncate | Truncates to character limit |
| Text to Number | Parses string to INT or FLOAT |
| Number to Text | Formats number as string |

### Type Casting (ComfyUI_essentials)

| Node | Function |
|------|----------|
| IntToFloat+ | INT -> FLOAT |
| FloatToInt+ | FLOAT -> INT (truncate/round) |
| StringToInt+ | STRING -> INT |
| BoolToInt+ | BOOL -> INT (0 or 1) |

---

## Model Operations (Built-in)

### Model Merging

#### ModelMergeSimple
Blends two models using a single ratio.

| Input | Type | Notes |
|-------|------|-------|
| model1 | MODEL | Base model |
| model2 | MODEL | Model to merge in |
| ratio | FLOAT | 0.0 = model1, 1.0 = model2 |

Output: `MODEL` (merged)

#### ModelMergeBlocks
Per-block merge ratios for fine-grained control.

| Input | Type | Notes |
|-------|------|-------|
| model1 | MODEL | Base model |
| model2 | MODEL | Secondary model |
| input_blocks.N | FLOAT | Ratio for each input (encoder) block |
| middle_block.N | FLOAT | Ratio for middle block |
| output_blocks.N | FLOAT | Ratio for each output (decoder) block |

#### ModelMergeSD1 / ModelMergeSDXL
Architecture-aware merging with named blocks (e.g., `time_embed`,
`label_emb`, `input_blocks.0-11`, `middle_block`, `output_blocks.0-11`).

#### CLIPMergeSimple
Merges two CLIP text encoders.

| Input | Type | Notes |
|-------|------|-------|
| clip1 | CLIP | Base CLIP |
| clip2 | CLIP | Secondary CLIP |
| ratio | FLOAT | Blend ratio |

#### CLIPMergeSubtract
Subtracts one CLIP's weights from another (for concept removal).

| Input | Type | Notes |
|-------|------|-------|
| clip1 | CLIP | Base |
| clip2 | CLIP | To subtract |
| multiplier | FLOAT | Subtraction strength |

### Model Patching (Performance)

#### FreeU / FreeU_V2
Applies Fourier-domain filtering to UNet features. Enhances backbone
high-frequency details while suppressing skip connection noise.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| model | MODEL | -- | Input model |
| b1 | FLOAT | 1.3 | Backbone scale factor (block 1) |
| b2 | FLOAT | 1.4 | Backbone scale factor (block 2) |
| s1 | FLOAT | 0.9 | Skip connection scale (block 1) |
| s2 | FLOAT | 0.2 | Skip connection scale (block 2) |

**FreeU_V2** refines the filtering with improved Fourier masking.
Recommended starting values differ from V1.

| Version | b1 | b2 | s1 | s2 |
|---------|-----|-----|-----|-----|
| FreeU V1 (SD1.5) | 1.3 | 1.4 | 0.9 | 0.2 |
| FreeU V2 (SD1.5) | 1.1 | 1.2 | 0.9 | 0.2 |
| FreeU V1 (SDXL) | 1.1 | 1.2 | 0.6 | 0.4 |

#### HyperTile
Splits attention computation into tiles for generating at resolutions
beyond normal VRAM capacity. Reduces memory from O(n^2) to O(n).

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| model | MODEL | -- | Input model |
| tile_size | INT | 256 | Tile size in pixels |
| swap_size | INT | 2 | Swap factor |
| max_depth | INT | 0 | How deep in UNet to apply (0 = all) |
| scale_depth | BOOL | false | Scale tile size with UNet depth |

Best for SDXL at 1024x1024+. Less effective for SD1.5.

#### PatchModelAddDownscale (Kohya Deep Shrink)
Downscales internal UNet activations during early sampling steps,
then upscales back. Dramatically reduces VRAM and speeds up generation.

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| model | MODEL | -- | Input |
| block_number | INT | 3 | UNet block to patch |
| downscale_factor | FLOAT | 2.0 | Internal downscale ratio |
| start_percent | FLOAT | 0.0 | When to start (0-1 of steps) |
| end_percent | FLOAT | 0.35 | When to stop |
| downscale_after_skip | BOOL | true | Apply after skip connection |
| downscale_method | COMBO | `bicubic` | Interpolation method |
| upscale_method | COMBO | `bicubic` | Interpolation method |

Typical usage: downscale_factor=2.0, end_percent=0.35 for ~2x speed gain.

#### PerturbedAttentionGuidance (PAG)
Perturbs self-attention during sampling to improve generation quality
without requiring negative prompts. Works as a model patch.

| Parameter | Type | Notes |
|-----------|------|-------|
| model | MODEL | Input model |
| scale | FLOAT | PAG guidance scale (default 3.0) |

### VRAM Impact of Model Patches

| Patch | VRAM Effect | Speed Effect |
|-------|------------|--------------|
| FreeU/V2 | Negligible | Negligible |
| HyperTile | Reduces significantly | Faster at high res |
| PatchModelAddDownscale | Reduces significantly | 1.5-2x faster |
| PerturbedAttention | Slight increase | Slightly slower |

### Combining Multiple Patches
Patches can be chained:
```
CheckpointLoaderSimple -> FreeU_V2 -> HyperTile -> PatchModelAddDownscale -> KSampler
```
Order generally does not matter as patches modify different aspects of the model.

---

## Debugging Tips

1. **PreviewImage** after every major step to catch issues early
2. **Mute** nodes to isolate problems (right-click -> Mute)
3. Use **Reroute** nodes to keep graphs readable
4. **Note** nodes to document why specific values were chosen
5. **SaveImage** with descriptive filename_prefix for A/B comparisons
6. Console (browser F12) shows node execution order and timing
