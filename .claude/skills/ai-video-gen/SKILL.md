---
name: "ai-video-gen"
description: "Use when working on the cinema pipeline, image or video provider routing, local FLUX.2 Klein keyframes, LivePortrait performance capture, character continuity, identity validation, prompt engineering, lip sync, post-processing, or final assembly."
---

# AI Video Generation Expert

Use repository code and current provider policy as the source of truth. Do not
revive a deleted workflow, invent readiness from reachability, or turn an
ambiguous paid/local submission into permission to start replacement work.

## Current pipeline

```text
Scene decomposition -> continuity/reference preparation -> keyframe generation
  -> policy-gated video provider route -> identity and media validation
  -> optional driving-performance transfer -> lip sync/post-processing
  -> FFmpeg assembly, packaging, and artifact indexing
```

Keyframes have two supported project selections:

- `gemini_multiref` is the default. Gemini Image runs when configured; a
  safely rejected result may continue through the guarded local/cloud
  cascade.
- `local_flux2_klein` is an explicit local route. It requires 1–10 approved
  regular-file references, durable job authority, and a fully ready local
  worker. If any requirement is missing, it fails closed; it does not silently
  spend on another provider.

The remaining guarded cloud image fallbacks are implemented in
`phase_c_assembly.py` and must preserve actual-engine provenance and billed
rejects. Never infer the winning provider from a project label.

## Local GPU topology

The application and project store stay on the Mac. The Windows 11 desktop owns
the ComfyUI/GPU runtime. Both services bind to Windows loopback; the Mac reaches
the bearer-authenticated gateway through its loopback SSH tunnel. Direct
plaintext LAN media transport is unsupported.

One authenticated gateway may expose exactly these two capabilities:

- `image-flux2-klein`: hash-bound FLUX.2 Klein 4B distilled image candidate.
- `performance-liveportrait`: pinned LivePortrait driving-performance worker.

When both application role URLs resolve to the shared tunnel they must use the
same strong token, and the gateway must prove both exact capability contracts.
URL equality or `/health/live` is not readiness.

### FLUX.2 Klein image contract

Source of truth: `deploy/windows-flux2-klein/` and
`performance/flux2_klein.py`.

- Fixed four-step distilled workflow, Euler sampler, CFG 1.0.
- One to ten unique approved references, each represented through the
  candidate's `ReferenceLatent` chain.
- Fixed supported aspect ratios/dimensions from the hash-bound workflow.
- Candidate package, workflow, models, revisions, install evidence, fixed
  execution probe, and sequential 1/2/10-reference benchmark must all match.
- State is one of `not_installed`, `needs_benchmark`, `ready`, `blocked`, or
  `offline`. Only `ready` may dispatch.
- Dispatch always uses the durable prompt ledger even though local provider
  cost is zero. Resume/reconcile an accepted prompt; never enqueue a duplicate.

### LivePortrait performance contract

Source of truth: `performance/live_portrait_workflow.py`,
`performance/live_portrait.py`, and `deploy/windows-liveportrait-worker/`.

- Requires both an approved keyframe and an operator-supplied driving video.
- Fixed at 25 fps, 512-pixel video ingest width, and at most 8 seconds/200
  driving frames per request.
- LivePortrait work is serialized at concurrency 1 on the 16 GiB desktop GPU.
- MediaPipe cropper runs through CPU ONNX Runtime; portrait inference uses the
  GPU.
- Readiness is role-, workflow-, model-, revision-, and execution-proof-bound.
- Production controller calls supply durable prompt authority here too, so an
  unknown submit/status outcome stops replacement work until reconciled. The
  adapter retains a non-durable compatibility path for callers without a
  shared ledger; do not claim crash-resume guarantees for that path.

The setup UI reads `/api/runtime/gpu-workers` and shows safe states, queue/GPU
facts, benchmark state, and blocker codes. Endpoint URLs, tokens, local paths,
and raw errors remain server-side.

## Video provider routing

`workflow_selector.WORKFLOW_TEMPLATES` is only the five-shot-class ordering
seed. `workflow_selector.get_resolved_workflow_routing()` delegates the
executable admission decision to `domain/video_engine_policy.py`, which
applies catalog lifecycle, product support, runtime availability, project
enablement, date-sensitive policy, and deduplication. For an `AUTO` request
with durable cost authority, `phase_c_ffmpeg.py` later filters only providers
whose recorded health is deterministically `unhealthy`; unknown/degraded
history remains eligible.

| Shot type | Ordered seed |
| --- | --- |
| portrait | GEMINI_OMNI -> VEO_NATIVE -> KLING_3_0 -> RUNWAY_GEN4 -> SEEDANCE |
| medium | GEMINI_OMNI -> VEO_NATIVE -> KLING_3_0 -> RUNWAY_GEN4 -> SEEDANCE -> LTX |
| wide | GEMINI_OMNI -> VEO_NATIVE -> LTX -> KLING_3_0 -> RUNWAY_GEN4 |
| action | GEMINI_OMNI -> VEO_NATIVE -> SEEDANCE -> KLING_3_0 -> RUNWAY_GEN4 -> LTX |
| landscape | GEMINI_OMNI -> VEO_NATIVE -> LTX -> KLING_3_0 |

Never treat this table as proof that an engine is configured or admitted. Ask
the runtime resolver and retain its rejection evidence. An explicit deprecated
pin is not authority for automatic routing.

## Performance-engine routing

`domain/performance.py` decides whether a shot needs performance transfer;
`performance/_router.py` dispatches it.

- Dialogue plus a face-readable shot defaults to Runway Act-Two (the persisted
  engine key remains `ACT_ONE` for compatibility).
- An explicit budget/cheap signal selects LivePortrait.
- Action without dialogue can select Viggle, whose catalog support remains
  `LIMITED` until a live contract run succeeds.
- Landscape, character-free, and wide-without-dialogue shots skip performance
  capture; wide dialogue falls through to Act-Two.
- Every real performance engine requires a driving video.

## Identity and continuity truth

Identity validation samples frames and records per-character similarity,
detection details, and a concrete `FailureReason`. It does not tune an image
graph. Missing/unusable evidence is `IDENTITY_UNVERIFIED` or manual review, not
a fabricated pass.

Current shot thresholds are defined only in `identity/types.py`:

| Shot | Strict | Standard | Lenient |
| --- | ---: | ---: | ---: |
| portrait | 0.75 | 0.70 | 0.60 |
| medium | 0.70 | 0.65 | 0.55 |
| wide | 0.60 | 0.55 | 0.45 |
| action | 0.65 | 0.60 | 0.50 |
| landscape | 0.0 | 0.0 | 0.0 |

Continuity uses approved character/location references, deterministic seeds,
style/camera constraints, artifact provenance, and post-generation validation.
Do not claim that previous output bytes are automatically fed into a mutable
image graph.

## Paid/local job safety

Before any network or GPU submission:

1. Validate project/run identity, input media, provider readiness, budget, and
   immutable request fingerprint.
2. Reserve or recover the durable attempt.
3. Submit once and persist the provider prompt/job ID immediately.
4. On timeout or ambiguous response, return recovery-required/unknown and
   reconcile that exact job before any retry.
5. Publish only validated media bytes and record actual provider/model, cost,
   latency, artifact hash, and version provenance.

## Reference routing

| Need | Read |
| --- | --- |
| Provider auth/contracts | `api-reference.md` |
| Shot classification and video candidate seed | `shot-routing.md` |
| Identity evidence and reference binding | `character-consistency.md` |
| Continuity/coherence | `continuity-and-style.md` |
| Prompt structure | `prompt-engineering.md` |
| Lip sync, upscaling, and assembly | `post-processing.md` |
| Local ComfyUI graphs/readiness | `../comfyui-mastery/SKILL.md` |

## Source map

| Concept | Source |
| --- | --- |
| Pipeline orchestrator | `cinema_pipeline.py` |
| Image generation and actual-engine provenance | `phase_c_assembly.py` |
| Local FLUX.2 dispatch | `performance/flux2_klein.py` |
| FLUX.2 candidate workflow | `deploy/windows-flux2-klein/workflow.py` |
| Video generation/cascade | `phase_c_ffmpeg.py` |
| Typed video policy | `domain/provider_catalog.py`, `domain/video_engine_policy.py` |
| Shot-class seed | `workflow_selector.py` |
| Continuity | `domain/continuity_engine.py` |
| Identity validation | `identity/validator.py`, `identity/types.py` |
| Performance routing | `domain/performance.py`, `performance/_router.py` |
| LivePortrait graph/adapter | `performance/live_portrait_workflow.py`, `performance/live_portrait.py` |
| Worker readiness and UI projection | `performance/worker_readiness.py`, `web_gpu_workers.py` |
| Artifact versions | `cinema/artifact_indexing.py` |
| Durable provider jobs | `paid_provider.py` |

## Common failure modes

- **Worker reachable but not ready:** inspect the capability state, blocker,
  package hashes, exact node schema, probe, and benchmark evidence. Do not
  weaken readiness to reachability.
- **GPU memory pressure:** keep the queue serialized, enforce the fixed
  LivePortrait ingest envelope, and stop unrelated GPU workloads before a
  canary/benchmark. Do not change the graph contract during an evidence run.
- **Identity drift:** verify approved references, framing, provider binding,
  and validator evidence. Generate a new version or request manual review; do
  not invent a hidden tuning parameter.
- **Temporal discontinuity:** check stable seeds, approved continuity/location
  references, camera/style constraints, scene boundaries, and post-processing.
- **Provider timeout/unknown:** recover the exact durable job. Never fall
  through to replacement paid or GPU work while acceptance is ambiguous.
