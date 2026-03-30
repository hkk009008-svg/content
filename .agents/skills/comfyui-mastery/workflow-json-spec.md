# ComfyUI Workflow JSON Specification

## API Format

ComfyUI uses a flat dictionary of node definitions. This is the **API format** (used by `/prompt` endpoint), NOT the UI format (which includes position/size metadata).

```json
{
  "<node_id>": {
    "inputs": {
      "<param_name>": <value>,
      "<linked_param>": ["<source_node_id>", <output_slot_index>]
    },
    "class_type": "<ExactNodeClassName>",
    "_meta": { "title": "<Display Name>" }
  }
}
```

### Rules

1. **Node IDs** are strings (e.g., `"8"`, `"100"`, `"200"`). Any unique string works, but convention is numeric.
2. **Scalar inputs** are direct values: `"text": "a photo of a cat"`, `"steps": 20`, `"denoise": 0.75`
3. **Linked inputs** reference another node's output: `["source_node_id", output_slot_index]`
   - Slot index is 0-based integer — `0` means the first output of the source node
   - Example: `"model": ["112", 0]` means "take output slot 0 from node 112"
4. **`class_type`** must be the exact Python class name (case-sensitive): `"KSampler"` not `"ksampler"`
5. **`_meta`** is optional — only used for display in the UI

### Minimal Example: txt2img

```json
{
  "1": {
    "inputs": { "ckpt_name": "v1-5-pruned-emaonly.safetensors" },
    "class_type": "CheckpointLoaderSimple"
  },
  "2": {
    "inputs": { "text": "a beautiful sunset over mountains", "clip": ["1", 1] },
    "class_type": "CLIPTextEncode"
  },
  "3": {
    "inputs": { "text": "", "clip": ["1", 1] },
    "class_type": "CLIPTextEncode"
  },
  "4": {
    "inputs": { "width": 512, "height": 512, "batch_size": 1 },
    "class_type": "EmptyLatentImage"
  },
  "5": {
    "inputs": {
      "seed": 42, "steps": 20, "cfg": 7.0,
      "sampler_name": "euler", "scheduler": "normal",
      "denoise": 1.0,
      "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
      "latent_image": ["4", 0]
    },
    "class_type": "KSampler"
  },
  "6": {
    "inputs": { "samples": ["5", 0], "vae": ["1", 2] },
    "class_type": "VAEDecode"
  },
  "7": {
    "inputs": { "images": ["6", 0], "filename_prefix": "output" },
    "class_type": "SaveImage"
  }
}
```

**CheckpointLoaderSimple outputs**: slot 0 = MODEL, slot 1 = CLIP, slot 2 = VAE

## Output Slot Index Reference

Common nodes and their output slots:

| class_type | Slot 0 | Slot 1 | Slot 2 |
|---|---|---|---|
| CheckpointLoaderSimple | MODEL | CLIP | VAE |
| UNETLoader | MODEL | — | — |
| DualCLIPLoader | CLIP | — | — |
| CLIPLoader | CLIP | — | — |
| VAELoader | VAE | — | — |
| LoraLoader | MODEL | CLIP | — |
| CLIPTextEncode | CONDITIONING | — | — |
| FluxGuidance | CONDITIONING | — | — |
| BasicGuider | GUIDER | — | — |
| KSampler | LATENT | — | — |
| SamplerCustomAdvanced | LATENT | LATENT (denoised) | — |
| KSamplerSelect | SAMPLER | — | — |
| BasicScheduler | SIGMAS | — | — |
| RandomNoise | NOISE | — | — |
| EmptyLatentImage | LATENT | — | — |
| VAEDecode | IMAGE | — | — |
| VAEEncode | LATENT | — | — |
| LoadImage | IMAGE | MASK | — |
| ControlNetLoader | CONTROL_NET | — | — |
| ApplyPulid | MODEL | — | — |
| IPAdapterApply | MODEL | — | — |

## Type System

ComfyUI has typed connections. Linking incompatible types causes errors.

| Type | Color (UI) | Description |
|---|---|---|
| MODEL | purple | Diffusion model (UNet) |
| CLIP | yellow | Text encoder |
| VAE | red | Variational autoencoder |
| CONDITIONING | orange | Encoded text + metadata |
| LATENT | pink | Latent space tensor |
| IMAGE | blue | Pixel tensor [B,H,W,C] float32 0-1 |
| MASK | green | Single-channel tensor [B,H,W] |
| NOISE | dark purple | Noise tensor |
| GUIDER | teal | CFG guider object |
| SAMPLER | brown | Sampler algorithm |
| SIGMAS | gray | Noise schedule |
| CONTROL_NET | cyan | ControlNet model |
| INT / FLOAT / STRING / BOOLEAN | gray | Scalar values |

## Workflow Generation Algorithm

When building a workflow from a natural language request:

### Step 1: Select Base Template
Match the request to the closest pattern in `workflow-patterns.md`:
- Face identity preservation → `txt2img-flux-pulid` (#2)
- Image-to-image → `img2img` (#3)
- Pose/depth/edge guidance → `controlnet-pose` (#4)
- Remove/replace regions → `inpainting` (#5)
- Higher resolution → `upscale-hires` (#6)
- Style transfer → `ip-adapter-style` (#7)
- Generate video → `animatediff-txt2vid` (#8)
- Basic generation → `txt2img-basic` (#1)

### Step 2: Modify Parameters
Inject user-specified values into the template:
```python
workflow["<node_id>"]["inputs"]["<param>"] = new_value
```

Common modifications:
- **Prompt**: Set `text` on CLIPTextEncode node
- **Seed**: Set `noise_seed` on RandomNoise or `seed` on KSampler
- **Resolution**: Set `width`/`height` on EmptyLatentImage
- **Steps**: Set `steps` on BasicScheduler or KSampler
- **CFG/Guidance**: Set `cfg` on KSampler or `guidance` on FluxGuidance
- **Denoise**: Set `denoise` on BasicScheduler or KSampler (< 1.0 for img2img)

### Step 3: Add/Remove Nodes
For features not in the base template:
1. Add new nodes with unique IDs (use high numbers like 200+)
2. Wire inputs using link references: `["source_node_id", output_slot]`
3. Rewire existing links if inserting into the chain

**Example — Adding ControlNet to a workflow:**
```python
# Add ControlNet loader
workflow["200"] = {
    "inputs": {"control_net_name": "control_v11p_sd15_openpose.safetensors"},
    "class_type": "ControlNetLoader"
}
# Add ControlNet apply (insert between conditioning and sampler)
workflow["201"] = {
    "inputs": {
        "conditioning": ["2", 0],      # from CLIPTextEncode
        "control_net": ["200", 0],      # from ControlNetLoader
        "image": ["202", 0],            # from preprocessor
        "strength": 0.8,
        "start_percent": 0.0,
        "end_percent": 1.0
    },
    "class_type": "ControlNetApplyAdvanced"
}
# Rewire: sampler now takes conditioning from ControlNet, not directly from CLIP
workflow["5"]["inputs"]["positive"] = ["201", 0]
```

### Step 4: Validate

Run through this checklist:
- [ ] Every linked input `["id", slot]` references an existing node ID
- [ ] Output slot indices are within range for the source node's class_type
- [ ] Types match (MODEL → MODEL, not MODEL → IMAGE)
- [ ] No circular dependencies
- [ ] At least one SaveImage or PreviewImage node exists
- [ ] Model architecture matches (SD1.5 vs SDXL vs FLUX — don't mix)
- [ ] For FLUX: use UNETLoader + DualCLIPLoader (not CheckpointLoaderSimple)
- [ ] For FLUX: use SamplerCustomAdvanced (not KSampler)
- [ ] For SD1.5/SDXL: use CheckpointLoaderSimple + KSampler

## Debugging Common Errors

| Error | Cause | Fix |
|---|---|---|
| `"prompt_id" not in response` | Server not running or wrong URL | Check COMFYUI_SERVER_URL |
| `Required input 'X' missing` | Node input not connected | Add the missing link or scalar value |
| `Invalid output slot index` | Slot index out of range | Check output slot reference table above |
| `type mismatch` | Wrong type connection | Check type system table — ensure types match |
| `Node type not found: X` | Custom node not installed | Install via ComfyUI-Manager |
| `CUDA out of memory` | Model too large for GPU | Use fp8/fp16 quantized models, reduce resolution |
| `Prompt execution error` | Various runtime failures | Check ComfyUI console for Python traceback |
| Blank/black output | Denoise too low or wrong VAE | Increase denoise, verify VAE matches model |
| Garbled faces | Wrong model for face nodes | PuLID needs FLUX; IP-Adapter needs matching model |

## Dynamic Node Injection Pattern

This project's `phase_c_assembly.py` demonstrates runtime workflow modification:

```python
# 1. Load base template
with open("pulid.json") as f:
    workflow = json.load(f)

# 2. Apply shot-type parameters (modifies existing nodes)
workflow = apply_workflow_params(workflow, params)

# 3. Inject runtime values (prompt, seed, face reference)
workflow["122"]["inputs"]["text"] = prompt
workflow["25"]["inputs"]["noise_seed"] = seed
workflow["93"]["inputs"]["image"] = uploaded_face_filename

# 4. Conditionally add nodes (img2img mode)
if init_image:
    workflow["200"] = {"inputs": {"image": remote_init}, "class_type": "LoadImage"}
    workflow["201"] = {"inputs": {"pixels": ["200", 0], "vae": ["10", 0]}, "class_type": "VAEEncode"}
    workflow["13"]["inputs"]["latent_image"] = ["201", 0]  # rewire sampler input
    workflow["17"]["inputs"]["denoise"] = 0.4  # partial denoise

# 5. Queue modified workflow
prompt_id = comfy.queue_prompt(workflow)
```

This pattern is robust because:
- Base template is known-good (tested in ComfyUI UI)
- Modifications target specific node IDs
- New nodes use high IDs (200+) to avoid collisions
- Links are explicitly rewired when the graph structure changes
