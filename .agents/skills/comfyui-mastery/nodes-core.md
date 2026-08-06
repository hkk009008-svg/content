# Core nodes used by the tracked workers

This is a project-specific reference. The authenticated live `/object_info`
schema at the pinned revisions is authoritative.

## FLUX.2 loaders and conditioning

| `class_type` | Key inputs | Output | Project use |
| --- | --- | --- | --- |
| `UNETLoader` | `unet_name`, `weight_dtype` | MODEL | Loads the pinned FLUX.2 Klein 4B fp8 file |
| `CLIPLoader` | `clip_name`, `type=flux2`, `device` | CLIP | Loads the derived pinned Qwen text encoder |
| `VAELoader` | `vae_name` | VAE | Loads the pinned FLUX.2 VAE |
| `CLIPTextEncode` | `clip`, `text` | CONDITIONING | Encodes the bounded prompt |
| `ConditioningZeroOut` | `conditioning` | CONDITIONING | Creates the negative branch required by the candidate |
| `ReferenceLatent` | `conditioning`, `latent` | CONDITIONING | Adds one approved image latent; chains for 1–4 references |

Model filenames and loader choices are fixed in
`deploy/windows-flux2-klein/workflow.py` and `models.json`. Do not substitute a
dropdown choice discovered from another worker.

## Reference/image nodes

| `class_type` | Key inputs | Output | Project use |
| --- | --- | --- | --- |
| `LoadImage` | `image` | IMAGE, MASK | Loads a previously uploaded safe remote filename |
| `ImageScaleToTotalPixels` | `image`, `upscale_method`, `megapixels`, `resolution_steps` | IMAGE | Normalizes each FLUX.2 reference to 1 MP/alignment |
| `VAEEncode` | `pixels`, `vae` | LATENT | Encodes a reference image for `ReferenceLatent` |
| `VAEDecode` | `samples`, `vae` | IMAGE | Decodes the generated latent |
| `SaveImage` | `images`, `filename_prefix` | saved output | Produces the image artifact later downloaded/validated by the Mac |

## FLUX.2 sampling nodes

| `class_type` | Key inputs | Output | Fixed use |
| --- | --- | --- | --- |
| `RandomNoise` | `noise_seed` | NOISE | Unsigned 64-bit stable seed |
| `KSamplerSelect` | `sampler_name` | SAMPLER | `euler` |
| `Flux2Scheduler` | `steps`, `width`, `height` | SIGMAS | Four steps and a supported fixed dimension pair |
| `EmptyFlux2LatentImage` | `width`, `height`, `batch_size` | LATENT | Batch one, same fixed dimensions |
| `CFGGuider` | `model`, `positive`, `negative`, `cfg` | GUIDER | CFG 1.0 |
| `SamplerCustomAdvanced` | `noise`, `guider`, `sampler`, `sigmas`, `latent_image` | LATENT | Executes the fixed distilled sample |

There is no caller tuning surface for node classes, steps, sampler, CFG,
scheduler, model names, or dimensions outside the builder's aspect table.

## Link checks

- Links are `[source_node_id, output_index]`, with string node IDs.
- The source output type must equal the destination input type.
- All referenced nodes must exist and every generation input must reach the
  `SaveImage` output.
- Live `/object_info` must accept every node class, field, model choice, and
  remote filename immediately before submission.
- Any builder-byte change invalidates previous candidate evidence.
