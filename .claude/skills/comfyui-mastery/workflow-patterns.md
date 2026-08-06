# Current workflow patterns

Use the tracked builders directly. These diagrams are review aids, not copied
templates; the package-bound Python output is authoritative.

## Pattern 1: FLUX.2 Klein reference-conditioned image

**Builder:** `deploy/windows-flux2-klein/workflow.py`

```text
UNETLoader(flux-2-klein-4b-fp8)
CLIPLoader(qwen_3_4b, type=flux2)
VAELoader(flux2-klein-vae)
  -> CLIPTextEncode(prompt)
  -> ConditioningZeroOut(negative)

for each of 1..4 references:
  LoadImage -> ImageScaleToTotalPixels -> VAEEncode
    -> ReferenceLatent(positive)
    -> ReferenceLatent(negative)

RandomNoise(seed)
KSamplerSelect(euler)
Flux2Scheduler(steps=4, fixed width/height)
EmptyFlux2LatentImage(fixed width/height)
  -> CFGGuider(cfg=1.0)
  -> SamplerCustomAdvanced
  -> VAEDecode
  -> SaveImage
```

Caller-controlled inputs are limited to:

- non-empty prompt, at most 4096 characters;
- one to four safe, unique remote reference filenames;
- unsigned 64-bit seed;
- one aspect ratio from the builder's fixed dimension table; and
- a bounded safe output prefix.

The graph has no optional node injection. A requested change to node classes,
model names, steps, scheduler, dimensions, or conditioning changes the
candidate contract and requires new bound evidence.

## Pattern 2: LivePortrait driving-performance transfer

**Builder:** `performance/live_portrait_workflow.py`

```text
LoadImage(source keyframe)
VHS_LoadVideo(driving clip, 25 fps, width 512, <=200 frames)
DownloadAndLoadLivePortraitModels(fp16, human)
LivePortraitLoadMediaPipeCropper(CPU, keep loaded)
  -> LivePortraitCropper(source)
  -> LivePortraitCropper(driver)
  -> LivePortraitRetargeting(eyes + lips)
  -> LivePortraitProcess(relative motion, stitching)
  -> LivePortraitComposite
  -> VHS_VideoCombine(H.264 MP4, 25 fps)
```

Both remote input filenames must be non-empty. Duration must be finite,
positive, and no more than eight seconds. The builder converts duration into a
maximum frame count before the GPU receives the batch.

## Safe graph-review checklist

1. Confirm the caller imports the tracked builder rather than a copied graph.
2. Confirm the active package/workflow hash matches the capability digest.
3. Validate every node class, input, enum/model choice, link type, and output
   path against authenticated live `/object_info`.
4. Prove every required input reaches the output node.
5. Keep uploads after readiness and before the single durable submission.
6. Treat changed graph bytes as new evidence scope.
7. Validate the decoded output and expected dimensions/container before atomic
   publication.
