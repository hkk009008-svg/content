# LivePortrait and video nodes

The only supported ComfyUI video graph in this repository is the pinned
LivePortrait driving-performance workflow. Video generation providers and RIFE
post-processing live outside this graph.

## Ingest and output

### `VHS_LoadVideo`

Loads the operator-supplied driving clip. The tracked builder fixes:

- `force_rate=25`;
- `custom_width=512`, aspect-derived height;
- `frame_load_cap=round(duration * 25)`, bounded to 1–200;
- no initial skip and every frame selected.

This bound must remain before the GPU batch. Leaving source dimensions
unbounded can expand a short high-resolution upload into avoidable memory
pressure.

### `VHS_VideoCombine`

Combines the composited images into H.264 MP4 at 25 fps. The output is not
trusted merely because history contains a filename; the adapter downloads it,
validates the media container, and publishes atomically.

Video Helper Suite is pinned by commit in the Windows worker revisions
manifest. Validate its exact live input schema.

## LivePortrait nodes

### `DownloadAndLoadLivePortraitModels`

Loads the pinned human-mode pipeline at fp16. The tracked model manifest and
startup execution proof, not a successful import alone, establish readiness.

### `LivePortraitLoadMediaPipeCropper`

Uses CPU ONNX Runtime and keeps the cropper loaded. This intentionally avoids
the unsupported face-analysis dependency path.

### `LivePortraitCropper`

Two instances crop the source still and driving frames with the same fixed
512-size, scale, vertical offset, rotation, and largest-face-first policy.

### `LivePortraitRetargeting`

Builds eye and lip retargeting information from the driving crop at fixed
multipliers.

### `LivePortraitProcess`

Transfers relative motion with stitching, bounded smoothing, expression-
friendly behavior, and the retargeting input. The source still and driving
images must both reach this node.

### `LivePortraitComposite`

Composites the processed crop into the original source framing before video
combine.

## Fixed data flow

```text
LoadImage(source) -----------------------> source crop ----------+
VHS_LoadVideo(driver) -> driver crop -> retargeting              |
models + cropper -----------------------> process -> composite --+
                                                            -> VHS_VideoCombine
```

`required_live_portrait_node_classes()` derives the exact required class set
from the shipping builder. The worker probe graph must equal a builder result,
and authenticated readiness binds its workflow/model/revision hashes.

## Safety

- Require a source keyframe and existing driving video.
- Reject non-finite, zero/negative, or over-eight-second duration before I/O.
- Serialize work at concurrency one.
- Upload only after capability readiness passes.
- Production calls must persist/recover the durable prompt ID and never
  duplicate ambiguous work; compatibility calls without a ledger are not
  crash-resumable.
- Stop unrelated GPU workloads before worker startup, canary, or benchmark.
