# Content local ComfyUI integration

## Boundary

The Mac owns the application, project store, durable job ledger, and final
artifacts. A Windows 11 desktop with an RTX 5070 Ti owns the GPU runtime. Raw
ComfyUI and its bearer-authenticated gateway listen on Windows loopback only;
the Mac uses a pinned-host-key SSH tunnel whose local endpoint is normally
`http://127.0.0.1:18189`.

The application configures both role URLs to that loopback endpoint and both
role credentials to the same strong token when the worker is shared. Direct
plaintext LAN uploads are rejected.

```text
Mac application and durable ledger
  -> authenticated Mac-loopback SSH tunnel
    -> Windows loopback gateway
      -> raw ComfyUI queue (single desktop GPU)
```

## Authenticated capability contract

The shared gateway must expose exactly two capabilities:

```text
image-flux2-klein
performance-liveportrait
```

`performance/worker_readiness.py` computes the expected capability digests
from the tracked packages. `performance/comfyui_endpoint.py` enforces the
endpoint/credential topology. `web_gpu_workers.py` returns only a safe,
read-only UI projection.

Reachability is not admission. The application checks the exact capability
set, expected workflow/model/revision/package hashes, execution proof, and
role-specific readiness immediately before any source-media upload.

## FLUX.2 Klein image flow

```text
phase_c_assembly.generate_ai_broll()
  -> explicit/default image-backend policy
  -> require_flux2_worker_ready()
  -> ComfyUIClient authenticated capability request
  -> upload 1..10 approved unique references
  -> performance.flux2_klein builds through the hash-bound candidate
  -> durable prompt reservation/recovery and single submission
  -> history/output validation
  -> bounded image download and atomic publication
```

The tracked flat graph in `deploy/windows-flux2-klein/workflow.py` uses:

```text
FLUX.2 UNet + Qwen text encoder + VAE
  -> prompt conditioning and zeroed negative conditioning
  -> for each reference: LoadImage -> scale -> VAEEncode -> ReferenceLatent
  -> fixed seed + four-step Flux2Scheduler + Euler sampler
  -> CFGGuider (1.0) -> SamplerCustomAdvanced -> VAEDecode -> SaveImage
```

The candidate accepts 1–10 references and only the fixed aspect dimensions in
the builder. Its package, source revisions, model hashes, install record,
fixed execution proof, and sequential 1/2/10-reference benchmark are all part
of readiness. Only state `ready` dispatches.

## LivePortrait performance flow

```text
performance._router (LIVE_PORTRAIT, concurrency 1)
  -> require_liveportrait_worker_ready()
  -> authenticated capability proof
  -> upload approved keyframe and driving video
  -> build_live_portrait_workflow()
  -> production durable prompt reservation/recovery and single submission
  -> validate/download MP4 and publish atomically
```

The tracked graph uses a still source plus a bounded driving clip:

```text
LoadImage(source)
VHS_LoadVideo(25 fps, width 512, <=200 frames)
  -> pinned LivePortrait models
  -> CPU MediaPipe cropper for source and driver
  -> retarget/process/composite
  -> VHS_VideoCombine(H.264 MP4, 25 fps)
```

Requests must be greater than zero and no longer than eight seconds. The
worker runs one GPU job at a time to avoid overlapping model memory on the
16 GiB desktop. `performance/live_portrait.py` retains a non-durable
compatibility path when no shared cost/job tracker is supplied; only the
production ledger-backed path is crash-resumable.

## Readiness and recovery rules

- `/health/live` says only that a gateway process answered.
- `/health/ready` retains the dedicated performance compatibility contract.
- Authenticated `/api/capabilities/ready` is the shared-worker admission
  record.
- FLUX.2 states: `not_installed`, `needs_benchmark`, `ready`, `blocked`,
  `offline`.
- A stale hash, changed workflow, missing node class, wrong capability set,
  non-empty/overlapping benchmark queue, or failed evidence check blocks
  admission.
- Submit/status ambiguity is durable `UNKNOWN`, never permission to submit a
  second job or start a fallback provider.

## Operator/UI contract

The setup UI calls `/api/runtime/gpu-workers` and can display role, safe state,
GPU/VRAM, queue counts, benchmark state, blocker code, and missing node classes.
It must not receive endpoint URLs, bearer tokens, Windows paths, evidence
paths, or raw exceptions.

Before a canary, benchmark, installation validation, or worker restart, stop
other GPU workloads. Ordinary code/doc/test work does not require exclusive
GPU ownership.
