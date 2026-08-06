---
name: "comfyui-mastery"
description: "Use when building, modifying, debugging, or reviewing this repository's hash-bound FLUX.2 Klein image graph, pinned LivePortrait performance graph, ComfyUI API JSON, worker readiness, or durable local-GPU dispatch."
---

# ComfyUI Mastery

ComfyUI executes a directed graph. API-format nodes use string IDs, a
`class_type`, and typed `inputs`; links are `[source_node_id, output_index]`.
Graph validity is necessary but is not worker readiness.

This repository has exactly two supported production graph contracts:

1. FLUX.2 Klein 4B distilled reference-conditioned image generation.
2. LivePortrait driving-performance transfer.

Do not substitute an interactive UI export, a historical graph, a cached node
list, or an unbound remote service for either tracked contract.

## API graph shape

```json
{
  "node_id": {
    "class_type": "NodeClassName",
    "inputs": {
      "scalar": "value",
      "linked_input": ["source_node_id", 0]
    }
  }
}
```

- Node IDs and link source IDs are strings.
- Every link output index is an integer. The tracked package validators prove
  link existence/types, graph reachability, bounds, and fixed dimensions.
- Immediately before submission, the generic live client validates class
  availability, required/unknown inputs, and installed enum/model choices
  against authenticated `/object_info`; do not overstate that live check as a
  full graph/type/range validator.
- A graph/UI export may contain metadata or widgets that are not valid API
  input. Use the tracked flat builders.

## Current node families

### FLUX.2 Klein

`UNETLoader`, `CLIPLoader`, `VAELoader`, `CLIPTextEncode`,
`ConditioningZeroOut`, `LoadImage`, `ImageScaleToTotalPixels`, `VAEEncode`,
`ReferenceLatent`, `RandomNoise`, `KSamplerSelect`, `Flux2Scheduler`,
`EmptyFlux2LatentImage`, `CFGGuider`, `SamplerCustomAdvanced`, `VAEDecode`, and
`SaveImage`.

### LivePortrait

`LoadImage`, `VHS_LoadVideo`, `DownloadAndLoadLivePortraitModels`,
`LivePortraitLoadMediaPipeCropper`, `LivePortraitCropper`,
`LivePortraitRetargeting`, `LivePortraitProcess`, `LivePortraitComposite`, and
`VHS_VideoCombine`.

Read `a24-integration.md` for the exact data flow and contract boundary.

## Immutable builders

- FLUX.2: `deploy/windows-flux2-klein/workflow.py`. The whole candidate package
  is bound by `candidate.json`; application code loads that builder through
  `performance/flux2_klein.py` only after validating all bindings.
- LivePortrait: `performance/live_portrait_workflow.py`. Its tracked worker
  probe graph must equal the builder output, and model/revision/workflow hashes
  form the performance capability digest.

Changing a builder or tracked probe invalidates its existing evidence. Update
the corresponding manifest/package bindings and rerun that role's required
execution/acceptance evidence; never relabel old evidence as current.

## Worker topology and readiness

- Raw ComfyUI and the gateway bind only to Windows loopback.
- The Mac application uses an SSH tunnel to a Mac loopback URL and a strong
  bearer token.
- A shared endpoint must expose exactly `image-flux2-klein` and
  `performance-liveportrait`, with the same credential configured for both
  roles.
- `/health/live`, `/system_stats`, an empty queue, or a successful
  `/object_info` response proves only a partial fact.
- Production admission requires the exact authenticated capability payload,
  expected hashes, fixed execution proof, and role-specific state.

FLUX.2 may run only in state `ready`; installation alone is
`not_installed`, and a passing fixed probe without the sequential
1/2/4-reference capacity run is `needs_benchmark`. LivePortrait requires its
pinned startup execution proof and role-bound readiness digest.

## Submission discipline

1. Validate local inputs and output destination before constructing a client.
2. Fetch and validate authenticated capability readiness.
3. Upload bounded source media only after readiness passes.
4. Build the graph from the tracked builder using returned remote filenames.
5. Reserve/recover a durable attempt and submit once.
6. Persist the prompt ID, poll history, validate the output record and media,
   then publish atomically.
7. Treat an ambiguous submit/status result as unknown; reconcile the accepted
   prompt instead of queuing a replacement.

The shared desktop GPU is single-queue production capacity. Serialize
LivePortrait, keep its 25 fps/512-pixel/8-second ingest envelope, and stop other
GPU workloads before canaries, benchmarks, or worker startup.

## Reference routing

| Need | Read |
| --- | --- |
| Project topology, readiness, and data flow | `a24-integration.md` |
| API JSON validation and safe mutation | `workflow-json-spec.md` |
| Current graph patterns | `workflow-patterns.md` |
| Current loader/sampler/latent nodes | `nodes-core.md` |
| Reference conditioning and identity evidence | `nodes-face-identity.md` |
| LivePortrait/video nodes | `nodes-video.md` |
| Image scaling/validation nodes | `nodes-image-processing.md` |
| Generic utility nodes | `nodes-utility.md` |
