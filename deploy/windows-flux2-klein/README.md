# FLUX.2 Klein 4B distilled — offline Windows candidate

This directory is an isolated candidate for capability `image-flux2-klein`.
It includes guarded Windows install, probe, and benchmark commands, but none of
them run automatically. The checked-in state does **not** mean models were
installed, change the accepted LivePortrait worker, expose an API route, prove
a GPU execution, or claim production readiness.

Current truth:

- `candidate_state`: `not_installed`
- `readiness.state`: `not_installed`
- `startup_ready`: `false`
- `execution_proven`: `false`
- `benchmark_state`: `not_run`
- license/provenance review: official sources selected; Qwen shard derivation
  has not been executed

A green static preflight means only that the checked-in manifests, builder
outputs for 1, 2, and 10 staged reference images, and pinned `/object_info`
schema agree. It cannot promote this candidate.

## Pinned upstream basis

- [Black Forest Labs FLUX.2 Klein 4B model card](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) declares the 4B open weights under Apache-2.0 and describes distilled four-step, multi-reference use.
- [Official ComfyUI Klein guide](https://docs.comfy.org/tutorials/flux/flux-2-klein) identifies the FP8 diffusion model, Qwen 3 4B encoder, FLUX.2 VAE, and official core workflow.
- The VAE and Qwen source shards are pinned directly to the official BFL
  Apache repository at commit
  `5e67da950fce4a097bc150c22958a05716994cea`.
- The official ComfyUI workflow template is pinned to commit `6c038ced23eb9d4de675b14aa854b616a6a7cd16`.
- ComfyUI core is pinned to the repository's existing Windows-worker commit `b1693ecba9f5b65f8c80ab36b195ab963ec92413` (`0.30.0`).

The exact model revisions, byte sizes, SHA-256 values, destinations, and source
URLs are in `models.json`. No fetch-by-branch URL is accepted.

### License and derivation boundary

The BFL 4B repository and upstream Qwen3-4B project declare Apache-2.0. The VAE
is now the direct official BFL BF16 artifact; static tensor correspondence and
pinned ComfyUI loader compatibility are recorded in `PROVENANCE.md`.

The Qwen Comfy mirror is not an installation source. `models.json` pins the two
official BFL Apache shards, their index, and every hash. The offline
`merge_qwen_encoder.py` tool must derive the required single-file encoder and
match its complete known SHA-256 before license approval. Matching headers,
shapes, and expected output size alone are not payload proof. The candidate
therefore remains blocked on that unexecuted derivation as well as installation
and runtime evidence.

## Workflow contract

`workflow.py` returns a flat ComfyUI API graph—no UI subgraph UUIDs and no
custom nodes. The caller must provide:

- a non-empty prompt;
- a fixed unsigned 64-bit seed;
- one of the fixed aspect ratios in `ASPECT_DIMENSIONS`; and
- 1–10 already-uploaded, unique reference filenames.

Each reference is scaled to one-megapixel class, VAE encoded, then attached to
both positive and zeroed-negative conditioning with native `ReferenceLatent`
nodes. Sampling is fixed to Euler, CFG 1.0, batch 1, and the distilled four-step
`Flux2Scheduler` path. Ten is this candidate's bounded multi-reference safety
envelope, aligned with the broader FLUX.2 documentation; it is not a measured
local capacity claim.

## Guarded Windows installation

Run this on the Windows desktop, from the checked-out repository, while
ComfyUI is stopped and the target GPU is otherwise idle:

```powershell
.\deploy\windows-flux2-klein\Install-Candidate.ps1 `
  -ComfyRoot C:\ComfyUI
```

The default state/cache root is
`%LOCALAPPDATA%\ContentFlux2Klein`; it can be changed with `-StateRoot`. The
installer validates this package first, audits every final model destination
before its first network call, and refuses a mismatched existing file. It then
downloads only commit-pinned official BFL files, checks complete byte counts
and SHA-256 values, runs the deterministic Qwen merge, and publishes each model
with a no-overwrite atomic filesystem operation. If a later publish/evidence
step fails, it rolls back only exact files created by that invocation.

Verified cache/derivation bytes are retained for resumability and audit. The
peak disk requirement is therefore materially larger than the approximately
12.3 GB installed model set. Do not start the install until the selected
Windows state volume and the ComfyUI model volume both have sufficient free
space. Cache deletion is an explicit later operator action, never an automatic
installer side effect.

Successful installation writes immutable history plus `install.json` with
status `installed_needs_execution_probe`. It also atomically publishes
`status.json` in the state root, still projecting `state=not_installed` with
`artifacts_installed=true` and blocker `candidate_execution_probe_not_run`. It
does not mark the candidate ready.

### Standalone offline Qwen derivation

After the three pinned official BFL text-encoder files have been staged under a
single source directory using their `text_encoder/...` paths, run:

```powershell
python .\deploy\windows-flux2-klein\merge_qwen_encoder.py `
  --source-dir C:\staging\flux2-klein-official `
  --output C:\ComfyUI\models\text_encoders\qwen_3_4b.safetensors
```

This command performs no network access, verifies all source and output hashes,
uses bounded streaming, and refuses to overwrite a destination. The guarded
installer invokes the same function after downloading all three exact official
text-encoder source files. It has not been run against the multi-gigabyte
official shards in this checked-in candidate state.

## Fixed execution probe

Start the pinned ComfyUI checkout locally on Windows, keep its queue empty, and
run:

```powershell
.\deploy\windows-flux2-klein\Probe-Candidate.ps1 `
  -ComfyRoot C:\ComfyUI
```

Before uploading anything, `runtime.py` revalidates the bound package,
`install.json`, all three installed model hashes, live `/object_info`, an empty
queue, and GPU telemetry. It uploads the committed 173-byte decoded PNG
fixture, re-fetches `/object_info`, validates the complete live graph, and
submits exactly once. An ambiguous submit or execution timeout is durably
recorded as `submission_unknown` and is never automatically retried. A pass
requires one `SaveImage` output that downloads, fully decodes, and is exactly
1024 by 1024. The output and immutable evidence include the graph, model,
fixture, package, latency, and bounded GPU-memory bindings.

Uploaded fixed input files are removed only when their local bytes still match
the committed fixture. They are retained after an UNKNOWN submission because
the accepted job may still need them.

A passing probe atomically advances `status.json` to `needs_benchmark`. The
status record contains the state-root-relative immutable canary evidence path,
its exact SHA-256, run ID, workflow SHA-256, output SHA-256, and the complete
runtime-contract digest. A reader must rehash and validate that evidence before
trusting the state; browser projections must omit the local path.

## Sequential local capacity benchmark

After a passing fixed probe, pass its immutable evidence path explicitly:

```powershell
.\deploy\windows-flux2-klein\Benchmark-Candidate.ps1 `
  -ComfyRoot C:\ComfyUI `
  -ProbeEvidence C:\Users\you\AppData\Local\ContentFlux2Klein\evidence\probe\RUN_ID\evidence.json
```

The benchmark rejects stale or failed probe evidence, then runs reference
counts `1`, `2`, and `10` strictly sequentially. Each case repeats all live
schema/queue guards, makes exactly one submission, requires a decoded fixed-size
output, and records latency plus consistent RTX VRAM samples. `benchmark_passed`
means this exact three-case capacity contract completed without overlap, OOM,
or decode/schema failure. It intentionally invents no hidden latency SLA; the
measured latency remains visible in evidence for an operator decision.

Only a bound passing benchmark atomically advances `status.json` to `ready`.
Its immutable summary binds the exact canary hash and every 1/2/10 case
evidence, workflow, output, latency, and VRAM result. `runtime.py` exposes
`load_runtime_status(...)` as the fail-closed reader: it rejects path escapes,
hash drift, missing/wrong-state evidence, stale manifests/workflows, and a
transition whose readiness booleans contradict its state.

Running the commands on the Windows desktop against
`http://127.0.0.1:8188` is the preferred boundary. `runtime.py` refuses an
unauthenticated plaintext non-loopback endpoint. If a protected LAN gateway is
used, supply its bearer token through `CONTENT_COMFY_TOKEN`; endpoint URLs and
credentials are not written to evidence.

## Offline preflight

Run only the static package check:

```powershell
python .\deploy\windows-flux2-klein\preflight.py
```

Expected truth includes `readiness_state=not_installed` and
`execution_proven=false`. `preflight.py` rejects manifest hash drift, source
revision drift, missing or type-drifted core nodes, missing model choices,
unknown graph inputs/classes, link type mismatches, non-four-step sampling, and
unapproved output dimensions. It also requires the direct official VAE and
unexecuted, official-source Qwen derivation contract. It imports the bound
builder and validates flat
graphs at the minimum, ordinary multi-reference, and maximum candidate bounds
(1, 2, and 10 references). The committed `/object_info` fixture models ten
already-staged filenames. Runtime revalidates the worker's actual schema after
upload and requires each submitted name to be present there.

## Operator-visible UI readiness states

The shared UI exposes capability `image-flux2-klein` with these exact state
meanings:

| State | Required UI meaning |
| --- | --- |
| `not_installed` | Candidate exists, but pinned artifacts/runtime are absent. No run action. |
| `needs_benchmark` | Hashes, nodes, and fixed execution probe passed; required local benchmark has not. |
| `ready` | Hashes, schema, fixed execution probe, benchmark, and license review all passed. |
| `blocked` | A policy, license, manifest, model, or execution contract failed; show the blocker code. |
| `offline` | Previously configured worker cannot be reached through its authenticated bounded probe. |

The safe browser projection should include only:

- `capability`, `state`, `startup_ready`, and `execution_proven`;
- `benchmark_state` and a non-secret `blocker_code`;
- manifest/workflow contract digests after installation; and
- safe GPU/queue fields only after authenticated capability validation.

Do not expose endpoint URLs, bearer credentials, local paths, or raw provider
errors. Do not label static schema validation as `ready`.

## Application integration

Setup → GPU workers displays the authenticated image capability. Setup → Image
enables Local FLUX.2 only for the exact live `ready` record with startup,
execution, benchmark, hash, and license evidence intact. Production dispatch
accepts 1–10 approved references and binds the Comfy prompt ID to the durable
project attempt ledger through download and publication. Explicit local
selection fails closed; an ambiguous accepted job becomes `UNKNOWN` and blocks
automatic replacement work until reconciled.
