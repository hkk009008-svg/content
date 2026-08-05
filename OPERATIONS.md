# Operations Guide

How to install, run, configure, and troubleshoot the Content cinema pipeline.

> For *what the code does*, read [ARCHITECTURE.md](ARCHITECTURE.md). This
> file is *how to operate it*.

---

## Quick navigation

- §1 [Prerequisites](#1-prerequisites)
- §2 [First-time setup](#2-first-time-setup)
- §3 [Environment variables](#3-environment-variables)
- §4 [Running the system](#4-running-the-system)
- §5 [Pod setup — RunPod ComfyUI](#5-pod-setup--runpod-comfyui)
- §6 [ComfyUI workflows & models](#6-comfyui-workflows--models)
- §7 [Verification — smoke + tests](#7-verification--smoke--tests)
- §8 [Common operational tasks](#8-common-operational-tasks)
- §9 [Troubleshooting](#9-troubleshooting)
- §10 [Costs at a glance](#10-costs-at-a-glance)
- §11 [Durable production controls](#11-durable-production-controls)

---

## 1. Prerequisites

| Requirement | Why |
|---|---|
| **Python 3.13** | PEP 604 union syntax + recent `concurrent.futures` semantics. 3.11+ is the floor but 3.13 is the tested target. |
| **Node 20+ / npm** | Vite 6 dev server + TypeScript 5.7 |
| **macOS or Linux** | `audio/effects.py` uses macOS AU plugins where available; Linux falls back to FFmpeg. Pedalboard works on both. |
| **ffmpeg** in PATH | Stitching, color grade, two-pass loudnorm, frame extraction. `brew install ffmpeg`. |
| **RunPod ComfyUI pod** | Optional image-generation fallback — Gemini 3.1 Flash Image is primary; the immutable RunPod image certifies the `pulid.json` PuLID graph. It does not currently certify LivePortrait/SadTalker. See §5. |
| **Cloud API keys** (~17 providers) | See §3 |
| **Disk space** | ~50GB for cache + projects + exports. DeepFace auto-downloads the identity model's weights on first run — currently **GhostFaceNet** (~16MB measured locally; everything in the codebase that says "ArcFace" — including the historical estimate this line used to carry — actually runs GhostFaceNet, see ARCHITECTURE.md §11.1). |

---

## 2. First-time setup

```bash
# Clone (assuming you're here, this is just for reference)
cd /your/workspace
git clone <repo> Content && cd Content

# Python venv
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Frontend deps
cd web
npm install
cd ..

# Env vars
cp .env.example .env
# Edit .env and fill in keys (see §3)

# Smoke
.venv/bin/python -c "
import cinema_pipeline
from cinema.context import PipelineContext, get_project_setting
from phase_c_vision import _get_shared_validator
from identity import get_shared_validator
from face_validator_gate import _get_validator as fvg
from performance.identity_gate import _get_validator as pig
assert _get_shared_validator() is get_shared_validator() is fvg() is pig()
print('OK')
"
```

If the smoke step fails, see §9.

### Claude Code hooks (two-seat sessions)

- `update-state.sh` must be registered under BOTH `PostToolUse` (matcher
  `Bash|Write|Edit`) AND `SessionStart` in `.claude/settings.local.json`
  (gitignored, per-machine). The SessionStart fire closes the v5.9
  skip-worktree coverage gap: pollution landing after a session's LAST
  PostToolUse fire (strike #2, 2026-06-12, 866 paths) is swept at the next
  session's start instead of surviving into its `git status`.

---

## 3. Environment variables

All env vars are read by [config/settings.py](config/settings.py) into a
frozen `Settings` dataclass. **Never read env vars elsewhere** — go through
`from config.settings import settings`.

Authoritative list (every variable consumed by the pipeline):

### LLM providers

| Var | Required? | Used by |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes (primary creative LLM) | LLMEnsemble, ChiefDirector, scene decomposition |
| `OPENAI_API_KEY` | Yes (primary judge / GPT-4o-only paths) | LLMEnsemble, style director, dialogue writer, scene decomposer fallback |
| `GEMINI_API_KEY` | Optional | Opt-in Gemini dispatch via `models=["gemini-3.1-pro-preview", ...]`; also `gemini_omni_native.GeminiOmniAPI` (video, WS2 `GEMINI_OMNI` — the `target_api` PRIMARY for all shot types) and `gemini_image_native.GeminiImageAPI` (image, WS3 Nano Banana 2 — the image PRIMARY by default policy, gated per-shot on a character reference being present; a project sets `identity_backend="pod"` to opt out). Both accept either this or `GOOGLE_API_KEY` (`settings.google_api_key or settings.gemini_api_key`). |
| `GOOGLE_API_KEY` | Optional | Veo Gemini Developer API path when no ADC-ready explicit Vertex project is available. An explicit `GOOGLE_CLOUD_PROJECT` selects Vertex only when Application Default Credentials resolve; otherwise this key is the safe fallback. Also used by `gemini_omni_native.GeminiOmniAPI` (video) and `gemini_image_native.GeminiImageAPI` (image). |

### Video generation

| Var | Required? | Used by |
|---|---|---|
| `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` | Optional (legacy compatibility) | KLING_NATIVE — deprecated kling-v1-6 JWT route, explicit-only for base video generation (storyboard compatibility remains separate); automatic Kling is fal KLING_3_0 via FAL_KEY |
| `FAL_KEY` | Recommended (used by many cascades) | FAL routes: Seedance (action primary since 2026-07-11), Veo (fal proxy), Kling 3.0, LTX (proxy), all lipsync engines, music, FLUX image fallback. The FAL-hosted `SORA_2` route is RETIRED/unreachable; native Sora is explicit-only pre-sunset compatibility billed through `OPENAI_API_KEY`. |
| `LTX_API_KEY` | Optional | LTX native direct (signed input upload + persisted async-v2 job polling; preferred over FAL proxy) |
| `RUNWAYML_API_SECRET` | Optional | RUNWAY_GEN4 automatic fallback and Act-Two performance; the Gen-3 dispatch branch is retired |

### Audio + performance capture

| Var | Required? | Used by |
|---|---|---|
| `ELEVENLABS_API_KEY` | Yes (TTS) | Dialogue voiceover, voice direction profiles, foley (when reactivated) |
| `CARTESIA_API_KEY` | Optional | Cartesia TTS path (Sonic 3.5 since 2026-08-01; routing key stays `CARTESIA_SONIC_2`) |
| `STABILITY_API_KEY` | Optional | Stable Audio 2 foley generator (currently dormant in audio/ — see DECISIONS.md) |
| `SUNO_API_KEY` (+ `SUNO_API_BASE`) | Optional | Suno V5 BGM (defaults to FAL Stable Audio) |
| `VIGGLE_API_KEY` | Optional | Viggle performance capture (Mode A only). **Uncontained 2026-08-01 (ADR-082):** the adapter was rewritten to the official `apis.viggle.ai/v1/renders` contract and `domain.performance.route_performance_engine` auto-selects it again for action-without-dialogue shots. Catalog state is `LIMITED`, not `SUPPORTED` — contract-correct and unit-tested, but never exercised against the live API, so your first render is also the first live verification. Those shots now need a driving video (Mode-B synthesis or an operator upload). |

### Google Cloud / Vertex AI

| Var | Required? | Used by |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | Required if using VEO_NATIVE via Vertex | Veo native adapter |
| `GOOGLE_CLOUD_LOCATION` | Optional (defaults to `us-central1`) | Veo native adapter |

### Research enrichment

| Var | Required? | Used by |
|---|---|---|
| `FIRECRAWL_API_KEY` | Optional | Style director + scene decomposer cinematography research |
| `TAVILY_API_KEY` | Optional | Same as above; preferred |

### Infrastructure

| Var | Default | Purpose |
|---|---|---|
| `COMFYUI_SERVER_URL` | unset | Authenticated gateway address. Production RunPod uses private `http://<pod-id>.runpod.internal:8189` or public `https://<pod-id>-8189.proxy.runpod.net`; raw `:8188` is loopback-only. |
| `COMFYUI_API_KEY` | unset | Bearer token for remote ComfyUI. Mandatory for the production image and injected with RunPod Secrets; empty is allowed only for an explicitly local development endpoint. |
| `EXPERIMENTS_DB_PATH` | `data/experiments.db` | SQLite cost tracker DB |
| `PIPELINE_JOB_DB_PATH` | `data/pipeline_jobs.db` | Filesystem-backed SQLite/WAL queue for full-project jobs. Relative paths are repository-rooted; `:memory:` and SQLite URI forms are rejected. |
| `PIPELINE_QUEUE_CONCURRENCY` | `1` | Global fixed worker-pool size, validated from 1 through 8. Raise only after provider quotas, local capacity, and aggregate budget have been reviewed. |
| `CINEMA_TRACE_DB_PATH` | `data/telemetry.db` | Local searchable structured trace index used by the Run UI. JSON stdout remains the deployment log stream. |
| `CINEMA_TRACE_RETENTION_DAYS` | `30` | Age retention for indexed traces, validated from 1 through 365 days. |
| `CINEMA_TRACE_MAX_EVENTS` | `50000` | Global row cap for the trace index, validated from 1,000 through 1,000,000 events. |
| `PERFORMANCE_CACHE_DIR` | `data/cache/driving` | Content-hash cache for Mode-B driving videos |
| `MOTION_GATE_SAMPLES` | `8` | Number of frame pairs sampled by `motion_gate.score_motion_fidelity` |
| `IDENTITY_EMBED_MODEL` | `GhostFaceNet` | DeepFace embedding backbone for identity QC (single chokepoint: `identity.validator.EMBED_MODEL`). ⚠️ All calibrated identity thresholds assume GhostFaceNet scores — non-default values (e.g. `Buffalo_L`, non-commercial license) fire a structural warning and need a pod re-calibration pass before the gates are meaningful. `AdaFace` selects the vendored adapter (`identity/adaface.py`, ADR-078) — UNCALIBRATED until P5 item 2. |
| `IDENTITY_ADAFACE_CKPT` | `models/adaface/adaface_ir101_ms1mv2.ckpt` | AdaFace checkpoint path (only consulted when `IDENTITY_EMBED_MODEL=AdaFace`). Download via `scripts/download_adaface_ckpt.py`; a missing file fails LOUD at startup by design. |
| `IDENTITY_ADAFACE_ARCH` | `ir_101` | Vendored AdaFace net arch (`identity/adaface_net.py` `build_model`); must match the checkpoint. |
| `WEB_BIND_HOST` | `127.0.0.1` | Loopback-only Flask bind. Non-loopback values are rejected until authenticated remote serving exists. |
| `WEB_CORS_ORIGINS` | `localhost-only dev origins` | Comma-separated explicit origin allowlist; `*` is rejected. |

### Minimal viable config

For a working "happy path" run you need:
- `ANTHROPIC_API_KEY` + `OPENAI_API_KEY` (LLM)
- `GEMINI_API_KEY` OR `GOOGLE_API_KEY` (video — Gemini Omni is the default primary for every shot type; also image-gen primary for character shots) — OR `KLING_ACCESS_KEY`+`KLING_SECRET_KEY`/`FAL_KEY` (video fallback cascade)
- `ELEVENLABS_API_KEY` (TTS — audio path)
- `FAL_KEY` (image-gen fallback chain: FLUX Kontext/Pro/Schnell, no pod needed) OR `COMFYUI_SERVER_URL` pointing at a working pod (reference-conditioned image-gen fallback)

A ComfyUI pod is no longer strictly required for a happy-path run — Gemini
image is the default primary for character shots and `phase_c_assembly.py`
falls through to the FAL FLUX chain (and, worst case, the free Pollinations
last resort) on any pod error or absent `COMFYUI_SERVER_URL`/`pulid.json`; the
pod remains the strongest identity-lock fallback. The certified production
image does not currently include LivePortrait/SadTalker; those paths need a
separately locked deployment. Everything else expands capability or adds
fallback paths.

---

## 4. Running the system

### Production-ish

```bash
.venv/bin/python web_server.py
```

Flask binds `127.0.0.1:8080`. Serves `web/dist/` (run `cd web && npm run build`
first to populate). Visit `http://localhost:8080`.

### Development (hot-reload frontend)

```bash
# Terminal 1: backend
.venv/bin/python web_server.py

# Terminal 2: frontend dev server
cd web && npm run dev
```

Visit `http://localhost:3000`. Vite proxies `/api/*` to `:8080`.

### Stopping

`Ctrl+C` the Flask process. The dispatcher stops claiming new work and asks
its local pipelines to cancel, but intentionally leaves any still-running
queue row under its current lease instead of manufacturing success. After the
process fence is released and that lease expires, the next server process
requeues the row with `resume_required=1` and enters the ordinary checkpoint
resume path (`pipeline_jobs.py:769`, `web_server.py:3270`).

That durable full-run queue is only one half of paid-work safety. Paid-media
adapters that own the versioned `CostTracker` attempt ledger resume an exact
FAL request, ComfyUI prompt, or native Kling task when a durable job ID was
recorded. Native Sora and other synchronous no-ID providers become
`accepted_unknown` if submission may have succeeded; automatic replay and
fallback are blocked. Planning LLM calls now reserve their own deterministic
no-replay paid attempts before the SDK boundary and reconcile successful token
usage once. They still cannot poll/resume a provider job after a crash because
those synchronous APIs expose no durable job ID.

To cancel a single project's run without killing the server:
```bash
curl -X POST http://localhost:8080/api/projects/<pid>/cancel
```

---

## 5. Pod setup — RunPod ComfyUI

A ComfyUI pod is the reference-conditioned fallback for image generation
(`pulid.json`; Gemini 3.1 Flash Image remains primary). A Gemini+FAL-only
configuration can run without it.

### Production path

Production uses the digest-pinned image under
[`deploy/runpod-comfyui/`](deploy/runpod-comfyui/README.md). That deployment
pins the CUDA/PyTorch base, ComfyUI, both required PuLID repositories and every
Python package; verifies every large model against byte-count and SHA-256
metadata; and refuses readiness until dependency, GPU, node, model-choice and
execution-canary checks pass.

Use an 80 GB or larger network volume mounted at `/workspace`. Raw ComfyUI is
loopback-only on `127.0.0.1:8188`. The only service eligible for exposure is the
authenticated gateway on `:8189`; `COMFYUI_API_KEY` is mandatory and must be
injected from a RunPod Secret. Prefer RunPod global networking with no public
ports. If public access is unavoidable, expose only `8189/http`, never `8188`.

The production image currently certifies the active `pulid.json` image graph
only. It does not contain or advertise LivePortrait/SadTalker. Those performance
paths require a separately locked image and model manifest before production
use; provider preflight will fail instead of silently claiming the node exists.

### Development/E2E bootstrap

[`scripts/setup_runpod.sh`](scripts/setup_runpod.sh) remains available for a
disposable development or E2E pod. It uses mutable downloads and dynamically
selects/reinstalls torch, so it is explicitly **not a production deployment**.
It now exits nonzero for missing required PuLID nodes or model files and never
prints a success summary after a required check fails.

The retired max tier (`--max`/`--max-fp16`) is not accepted by the bootstrap.
[`docs/RUNBOOK-max-tier-test.md`](docs/RUNBOOK-max-tier-test.md) is historical.

### Cost control

ComfyUI pods bill while running. Stop idle pods or use RunPod autoscaling, and
monitor readiness at `GET /health/ready` rather than treating a running
container as usable. For development, the Gemini/FAL-only paths bypass the pod.

---

## 6. ComfyUI workflows & models

ComfyUI workflow JSONs live at the **repo root**, not under `workflows/`:

| File | Used by |
|---|---|
| `pulid.json` | Production keyframe gen — `phase_c_assembly.generate_ai_broll` |

**Retired (WS1 Task 4):** `pulid_max.json` and its driver
(`quality_max.generate_ai_broll_max`) were deleted along with the max tier;
`pulid.json` is the sole ComfyUI/pod image graph now.

`pulid.json` is loaded once per process (module-level cache, lock-guarded)
and deep-copied per shot. Operator-side edits to the workflow JSON take
effect on next process restart.

### Model files required on the pod

For production (`pulid.json`), fetched and verified from
`deploy/runpod-comfyui/models.json`:
- FLUX.1-dev fp8 checkpoint (`flux1-dev-fp8.safetensors`, ~12GB)
- T5-XXL fp8 + CLIP-L text encoders (`t5xxl_fp8_e4m3fn.safetensors`, `clip_l.safetensors`)
- FLUX VAE (`ae.safetensors`)
- PuLID-FLUX face encoder weights (`pulid_flux_v0.9.1.safetensors`)
- EVA02-CLIP-L-336 weights used by `PulidFluxEvaClipLoader`
- antelopev2 InsightFace landmark model
- Real-ESRGAN 4x upscaler (`RealESRGAN_x4plus.pth`)

**Retired (WS1):** the max tier's SUPIR V2 (~35GB), AlignYourSteps scheduler
weights, LAION Aesthetic Predictor v2, CLIP ViT-L/14, FLUX Redux, the gated
fp16 FLUX/T5 base weights, and ReActor's `inswapper_128.onnx` are no longer
downloaded or needed.

---

## 7. Verification — smoke + tests

### §15 smoke (run at every session start)

```bash
.venv/bin/python scripts/ci_smoke.py
```

Single source of truth: [scripts/ci_smoke.py](scripts/ci_smoke.py).
Spec: [ARCHITECTURE.md §15](ARCHITECTURE.md#15-invariants--smoke-test).
Exit 0 = invariants hold.

### Unit tests

```bash
.venv/bin/python -m pytest tests/unit/ -q
```

Expected: **all pass, 0 failed** (the suite has grown well past the
2026-06-01 snapshot of 1275; run the command above for the current
collected count). The `@unittest.skip` entries formerly in
`test_project_persistence.py` were removed when the `domain.*` namespace
fix un-skipped them (ARCHITECTURE.md §16, 2026-06-09).

**Prerequisites — a venv alone is not enough.** The unit suite needs the
frontend dev-dependencies installed as well:

```bash
cd web && npm install
```

Without them the `test_product_surface_inventory.py` tests fail with
`TypeScript compiler unavailable: Cannot find module 'typescript'` — the
inventory walks `web/src` with the real TypeScript compiler. CI installs them
for the same reason (`dcc7b048`).

The suite does **not** need API credentials. `tests/conftest.py` supplies
placeholder values for every provider key, so a checkout with no `.env` runs
identically to one with real keys — every affected test mocks its client, and
nothing is sent anywhere. A real environment or `.env` still wins. (Contrast
the integration tests below, which do need real credentials.)

### TypeScript

```bash
cd web && npx tsc --noEmit
```

Should exit silently (no output = no errors).

### Integration tests

```bash
.venv/bin/python -m pytest tests/integration/ -m e2e
```

Requires real API credentials. Run sparingly.

For the protected paid release checks, dispatch the manual
[`Live contract canary`](docs/LIVE_CONTRACT_CANARY.md). Select exactly one
fixed target and obtain protected-environment approval. The RunPod targets are
deliberately split:

- `runpod-pulid-production` proves the shipping `pulid.json` graph on the
  pinned production image using `COMFYUI_SERVER_URL` / `COMFYUI_API_KEY`.
- `runpod-liveportrait-performance` proves LivePortrait only on a separately
  configured performance image using `PERFORMANCE_COMFYUI_SERVER_URL` /
  `PERFORMANCE_COMFYUI_API_KEY`.

Do not use PuLID readiness as evidence that the performance node contract is
installed. The workflow validates that separation before spending
([scripts/live_contract_canary.py:59](scripts/live_contract_canary.py:59),
[scripts/live_contract_canary.py:71](scripts/live_contract_canary.py:71)).

---

## 8. Common operational tasks

### Create a new project

UI: click "+ New Project" on the project selector. Or via API:
```bash
curl -X POST http://localhost:8080/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"name": "My Short"}'
```

Returns the project's 12-hex ID.

### Start a generation run

UI: click "Print this Reel" on the project page. Or:
```bash
curl -X POST http://localhost:8080/api/projects/<pid>/generate
```

The response is `202 Accepted`, not proof that provider work has started. It
contains a stable `job_id` and queue snapshot. Repeating the request while the
same project is queued or running returns that active job instead of creating
a second full-project run. The Run page and
`GET /api/projects/<pid>/pipeline-state` show queued position, attempt count,
checkpoint-resume state, cancellation intent, and any exceptional operator
action.

Generation admission and decorated project mutation/direct-stage routes also
hold the sibling `domain/projects/.<pid>.operation.lock`. This extends the
active-job/admin/stage fences across server processes, so a second worker
cannot delete or mutate the same project while another worker admits or runs a
conflicting operation. A `409` with `code=project_locked` or `project_busy` is
a retry signal, not permission to bypass the lock file.

Subscribe to progress:
```bash
curl -N http://localhost:8080/api/projects/<pid>/stream
```

Each subscriber has its own bounded inbox and replay window. If the server
restarts and only SQLite still knows the active job, `/stream` hydrates a fresh
in-process event bus, wakes the dispatcher, and attaches normally. The old
process's event buffer is not durable, so refresh `pipeline-state` for current
queue/stage truth; only post-attachment events can stream from the new bus.

Queued and running projects may be cancelled through the same endpoint:

```bash
curl -X POST http://localhost:8080/api/projects/<pid>/cancel
```

Never call the exceptional `/queue/abandon` route as routine cancellation.
The UI offers **Abandon blocked job** only when an exact running lease is
expired and the prior owner fence cannot be verified. The API also requires
the displayed 32-hex job ID and an explicit paid-work-risk acknowledgement:

```bash
curl -X POST http://localhost:8080/api/projects/<pid>/queue/abandon \
  -H 'Content-Type: application/json' \
  -d '{"job_id":"<exact-32-hex-id>","acknowledge_paid_work_risk":true}'
```

It refuses an active lease, a live local owner, and a stopped owner that can be
safely requeued. After a successful abandonment, inspect the project
checkpoint and provider billing/history before starting new paid work.

### Approve a gate

```bash
# Plan
curl -X POST .../shots/<sid>/plan/approve

# Keyframe (need take_id from /pipeline-state or shot record)
curl -X POST .../shots/<sid>/keyframes/<take_id>/approve

# Performance (added 2026-05-24)
curl -X POST .../shots/<sid>/performance/<take_id>/approve

# Final
curl -X POST .../shots/<sid>/final/<take_id>/approve
```

### Inspect cost

```bash
curl http://localhost:8080/api/projects/<pid>/cost-live | jq
curl 'http://localhost:8080/api/projects/<pid>/provider-analytics?scope=project&limit=200' | jq
```

The cost DB is SQLite at `EXPERIMENTS_DB_PATH` — open with any sqlite
client for forensic analysis. Provider analytics report success rate, latency,
active reservations, failures, and health from durable paid-media attempts plus
planning, identity, and Tavily/Firecrawl request observations. The UI label **Estimated usage** and
response `cost_basis: "reconciled_estimate"` are intentional: media prices are
reconciled with observed terminal state and LLM costs use token-list pricing,
but provider invoices remain the financial authority. Research APIs contribute
outcome/latency without a fabricated dollar cost when their responses expose no
authoritative usage value.

Automatic health avoidance is narrower than the dashboard. Only the base-video
`AUTO` route removes an engine classified `unhealthy`; `unknown` and
`degraded` providers stay eligible. Pinned video engines, planning LLMs,
image, lipsync, and performance dispatch are not silently rerouted by this
score.

### Search traces

The Run page includes a project-scoped Trace console. The equivalent API is:

```bash
curl 'http://localhost:8080/api/projects/<pid>/traces?level=ERROR&q=timeout&limit=50' | jq
```

Filter by `q`, `level`, or `trace_id`; paginate with the returned
`next_before_event_id`. The index is bounded by the `CINEMA_TRACE_*` settings,
redacts credential-shaped fields and signed URL secrets, and never returns
another project's rows. It is a central local SQLite index, not a replacement
for deployment-wide log shipping; JSON stdout remains authoritative when the
index is unavailable.

### Inspect artifact history and package deliverables

The Preview panel's **Client delivery** section lists current and archived
versions for each logical deliverable. Select the desired version for each
item, then click **Package selected versions**. It builds and immediately
downloads a verified ZIP while leaving the raw MP4 download available.

API equivalents:

```bash
# Current records plus newest-first immutable history.
curl 'http://localhost:8080/api/projects/<pid>/artifacts?limit=50' | jq

# Package current client deliverables.
curl -X POST http://localhost:8080/api/projects/<pid>/deliverables/package | jq

# Or package explicit historical artifact IDs from that same project.
curl -X POST http://localhost:8080/api/projects/<pid>/deliverables/package \
  -H 'Content-Type: application/json' \
  -d '{"artifact_ids":["<artifact-id>"]}' | jq
```

Use the returned `download_url`; it includes the package SHA-256. Packages are
content-addressed, so building a newer selection does not change an older URL.
The ZIP contains allowlisted client media, `MANIFEST.json`, and
`SHA256SUMS.txt`; internal artifacts and credential-like paths are refused.

### Retry character creation safely

The Character UI generates one 32-lowercase-hex `creation_request_id` and keeps
it after a failed or lost response. API clients must do the same in the
multipart `POST /api/projects/<pid>/characters` body. A `409` with
`code=paid_work_pending` is retryable with that exact token and unchanged
inputs. `code=paid_work_reconciliation_required` is not retryable: reconcile
the provider/billing state first. `code=artifact_version_pending` is a safe
same-token retry that repairs immutable reference indexing without another
provider submission.

The server saves the pending reservation in `project.json` and stages a
fingerprinted private sidecar before paid dispatch. Inspect the operator-safe
projection with:

```bash
curl http://localhost:8080/api/projects/<pid>/characters/pending-creation | jq
```

Do not invent a new token while this returns a pending request. If provider and
billing history prove that no resumable paid work remains, clear only that
exact reservation with the confirmation-gated `DELETE` body:

```bash
curl -X DELETE http://localhost:8080/api/projects/<pid>/characters/pending-creation \
  -H 'Content-Type: application/json' \
  -d '{"creation_request_id":"<exact-32-hex-id>","confirmation":"reconciled_no_resumable_paid_work"}'
```

That action records reconciliation and removes the private staging; it does not
recover a provider result or authorize an uninvestigated replacement call.
Artifact history retains output/source/dependency hashes and available recipe,
provider, model, and seed evidence, but reports `bit_exact=false`. Provider
nondeterminism and codec/platform differences mean replay evidence is not a
promise of byte-identical regeneration.

### Clean up old projects

```bash
curl -X POST http://localhost:8080/api/projects/<pid>/cleanup
```

Removes temp files / unreferenced shots. Doesn't delete projects themselves.
There is no global `POST /api/cleanup-all` route. Use the confirmed per-project
delete UI/API for deletion; never infer a repository-wide destructive action
from the cleanup endpoint.

### Configure dialogue voice mode

Dialogue shots (purpose `dialogue_close_up` / `talking_head_full`) default to
**Veo silent video → per-shot TTS → lip-sync overlay** (`dialogue_voice_mode="overlay"`),
giving Veo's look with a consistent character voice. To switch to the legacy
Veo-embedded-voice path:

```bash
curl -X PUT http://localhost:8080/api/projects/<pid> \
  -H 'Content-Type: application/json' \
  -d '{"global_settings": {"dialogue_voice_mode": "native"}}'
```

| Value | Behaviour |
|---|---|
| `"overlay"` **(default)** | Veo silent + per-shot TTS overlay. Consistent character voice. Veo RAI-blocks fall through cascade; overlay still fires. |
| `"native"` | Veo generates its own embedded voice (legacy path). |

The UI also exposes this as a dropdown (`dialogue_voice_modes` list in the project
settings panel). For overlay quality, tune `lip_sync_mode` and
`lipsync_validation_threshold` alongside.

---

## 9. Troubleshooting

### `import cinema_pipeline` fails with `TypeError` or `unsupported operand type(s) for |`

You're on Python <3.10. PEP 604 union syntax is used throughout. Recreate
the venv with Python 3.13:

```bash
rm -rf .venv
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### Singleton identity check fails

```
AssertionError: singleton broken
```

Indicates one of `phase_c_vision._get_shared_validator`,
`face_validator_gate._get_validator`,
`performance/identity_gate._get_validator`, or `identity.get_shared_validator`
is returning a fresh instance. Either:
- A bad merge / refactor broke a delegation (check git log)
- A test reset module state without restoring (rerun in a fresh Python process)

### `_VEO_QUOTA_EXHAUSTED_UNTIL` errors / VEO always falls through

VEO returned 429 quota-exhausted; the 30-minute cooldown is in effect.
Either wait it out, or use `VEO_NATIVE` (direct Vertex AI, not gated by
the FAL-side flag). Process restart also clears the cooldown.

### `ComfyUI pod not responding` / workflows fail

Check `COMFYUI_SERVER_URL` — `curl $COMFYUI_SERVER_URL/object_info` should
return JSON. If the proxy is authenticated, include
`-H "Authorization: Bearer $COMFYUI_API_KEY"`. Generation preflight also
requires `/models` and `/queue`; its error names missing node classes, inputs,
or configured model choices. During execution, `/ws` terminal errors are
reported immediately and history polling is used if WebSocket attachment is
unavailable. If these probes fail, the pod is down, throttled, unauthorized, or
its installed graph contract does not match `pulid.json`.

### A paid provider reports a deferred or recovery-required job

The dispatcher deliberately stops before the next provider whenever an
adapter cannot prove that already-accepted billable work is terminal. FAL
queue requests, ComfyUI prompts, LTX, Runway Gen-4, Viggle, Suno, and other
durable-ID media paths resume/poll the recorded provider job instead of
submitting another. Non-resumable media calls and lost acknowledgements remain
`accepted_unknown`; automatic replay and paid fallback stop. The Review UI and
live-cost attempt list show the recovery record instead of presenting an
ordinary failed take.

For the legacy explicit video pins, treat recovery by capability, not by the
word "native":

- `KLING_NATIVE` persists the acknowledged Kling task ID and an identical retry
  polls/downloads that exact task. If the POST acknowledgement itself was lost,
  it is `accepted_unknown` and cannot be resubmitted automatically.
- `SORA_NATIVE` enters a synchronous `create_and_poll` boundary without a
  durable application-owned job-ID callback. Any uncertainty after that point
  is `accepted_unknown`; there is no automatic Sora retry or fallback.
- `FAL_SVD` is queue-backed FAL work. It persists the fast-SVD request ID and
  resumes status/result retrieval for that exact request.

For LTX, do not delete the `.ltx-image-to-video-*.job.json` sidecar or manually
reroute the shot while its state is `submitted`, `pending`, `processing`,
`completed`, or `submission_unknown`. Use **Check / Resume LTX Job** to resume an
exact known job. For `submission_unknown`, reconcile the request with
LTX/provider billing first.

Gemini/Veo records are labelled **Manual Recovery Required**. Copy the displayed
exact job ID and reconcile it in the corresponding provider console; automatic
Google-job resume is not implemented. Do not clear the marker or start a
fallback until you have confirmed that no job was accepted, recovered and
accounted for the accepted result, or explicitly authorized a new paid
generation.

Keyframe generation uses the same fail-closed rule. If Review shows **Keyframe
Job Recovery Required**, inspect the ComfyUI queue/history using the displayed
prompt ID when one is available. Recover and register any valid output, or
confirm that no live/recoverable job remains and account for any billable work.
Only then use **Confirm Manual Reconciliation**. That button clears the durable
shot marker through `POST .../keyframes/recovery/resolve`; it does not cancel,
retry, or create a take. All keyframe-generation and iteration controls remain
disabled until the refreshed project confirms the marker is gone. A fresh
`submission_claimed` record cannot be cleared during its displayed active
window (600-second provider deadline plus a 60-second safety margin); the API
returns 409 and leaves the marker untouched. Late responses are attempt-bound
and cannot clear or publish over a newer claim.

An LTX sidecar in explicit terminal `failed` or `expired` state does not need
manual deletion: an identical retry supersedes it under a per-request file
lock. Never delete or override pending, processing, submission-claimed, or
unknown sidecars.

This mechanism applies only where a caller explicitly owns the versioned
paid-attempt authority. Shared ensemble, Chief Director, Cinema Director,
style, and scene-decomposition LLM paths now reserve deterministic attempts and
a conservative token-cost upper bound before each SDK request. Success settles
the reservation once from returned token usage (including Anthropic cache
rates); ambiguity becomes `accepted_unknown`, and the same logical request is
blocked on restart. That is deterministic no-replay fencing, not provider-ID
resume. Planning health remains observable only and does not change routing.

### A queue job offers `Abandon blocked job`

This means all ordinary recovery checks have already found a narrow ambiguous
case: the row is still `running`, its lease is expired, no local pipeline owns
it, and the prior process fence cannot be verified. It does **not** prove the
provider work stopped.

Before using the action, inspect the exact job ID, project checkpoint,
`cost-live` attempts, trace ID (the queue job ID), and provider consoles. If
the prior owner is live, stop it normally. If its fence is provably stopped,
the queue will requeue it for checkpoint resume and the exceptional action is
correctly refused. Use abandonment only after accepting that provider work may
still exist outside local evidence; then reconcile that work before starting a
replacement run.

### SSE connection drops repeatedly

Bundle-C 3.1 added exponential-backoff reconnect (1s/2s/4s/.../30s, 10
attempts). If you're seeing repeated drops in the browser console, check:
- Network stability between client and `web_server.py`
- Whether the durable queue worker ended or the server process restarted (a
  finished bus emits END; a restarted process hydrates a fresh bus from the
  active queue row but cannot replay the prior process's buffered events)
- Whether a corporate proxy is closing long-lived connections; keep the
  application loopback-only and configure the proxy to bypass localhost.

### Cost tracking shows $0 despite real API calls

Bundle-A 1.3 fixed a silent `AttributeError` in `ShotController.cost_tracker`
that was swallowing cost-tracking writes. If you see new zero-cost reports
after the fix, suspect a different layer (look in `cost_tracker.py` and
`config/settings.py:budget_limit_usd`).

### LipSync threshold setting has no effect

Bundle-A 1.2 fixed `_sync_gate_settings()` being called with no args. If
post-fix you still see the default `(True, 0.65)` behavior, check that
the calling controller is passing `_settings = self.project.get("global_settings", {})`
through to `generate_lip_sync_video(..., settings=_settings)`.

### Project lock timeout (`Project '<pid>' is locked by another operation`)

There are two distinct per-project locks. `domain/projects/<pid>.lock` protects
the project-manager read-modify-write transaction; the web operation boundary
uses `domain/projects/.<pid>.operation.lock` across a decorated route. Lock
files may remain on disk after release and are not proof of a live owner. Check
the 409 `code`, active queue state, and running server processes; stop a stale
owner normally instead of deleting lock files underneath it.

---

## 10. Costs at a glance

Rough order-of-magnitude per ~5s shot, sourced from `cost_tracker.API_COST_USD`
(provider pages read through 2026-07-31; treat as ±30% estimates and
calibrate against your own invoices — will drift):

| Provider | Per shot (typical) | Notes |
|---|---|---|
| Anthropic (Sonnet) | $0.01–0.05 | Several calls per scene (chief director, decomposer, optimizer) |
| OpenAI (GPT-4o) | $0.02–0.10 | Parallel-quorum competitor in LLM ensemble; doubles cost when `competitive_generation=True` |
| Gemini Omni Flash | ~$0.56 | Default `target_api` PRIMARY for every shot type (native audio); actual duration is prompt-inferred/variable, so this is a flat-estimate figure, not duration-true like LTX below |
| Gemini Image (Nano Banana 2) | $0.067/image | Default image-gen PRIMARY for character shots (`GEMINI_IMAGE`); exact published 1K-resolution price |
| Kling v3 Pro (FAL) | ~$0.56 | Portrait/medium primary FALLBACK since 2026-07-11 (`KLING_3_0`) |
| Kling Native | ~$0.50 | Legacy kling-v1-6 fallback (pre-v3 estimate) |
| Seedance (FAL) | ~$1.51 | Action-shot primary fallback — notably the priciest engine; action-heavy projects should budget for this, not the older Sora figure below |
| Sora (native, via OpenAI) | ~$0.80 | `SORA_NATIVE` — explicit-only compatibility until its 2026-09-24 sunset; absent from automatic/template cascades. The FAL-hosted `SORA_2` route is retired/unreachable. |
| Runway Gen4 | ~$0.50 | Premium fallback |
| LTX | $0.36 floor (6s) – ~$0.48 (8s, the dispatcher's shared default) | Cheapest native video provider; billed duration-true off the actual dispatched length (6/8/10s only), not a flat per-clip guess |
| SadTalker | ~$0.045/5s shot (GPU-time estimate) | Mode-B driving-video synthesis (cached) |
| Act-Two performance | ~$0.25/shot (5s @ $0.05/s) | Per-shot, semaphore-limited; cost_tracker's `ACT_ONE` key name is legacy, retargeted to Act-Two |
| ElevenLabs TTS | $0.005–0.02/shot | Per dialogue line |
| FAL Stable Audio BGM | $0.05/project | Once per project, 47s loop |
| Lipsync (overlay) | $0.03–0.15 | Per shot; cascade tries up to 4 engines |
| RunPod ComfyUI pod | $0.30/hour ÷ throughput | Idle billing hurts; quota-watch is on you |

For a 20-shot project with dialogue + lipsync, expect **$10–30 in cloud
costs** (single production tier — there is no separate "max tier" spend
anymore) plus pod time if you use the ComfyUI fallback. Budget control is via
`global_settings.budget_limit_usd` on the project — when exceeded,
`ShotController.generate_motion_take` calls `lifecycle.pause()` to halt at the
next checkpoint.

The Provider analytics panel does not upgrade these figures to invoice data.
Its API states `cost_basis: "reconciled_estimate"`: media totals are repository
estimates reconciled against terminal outcome evidence, while planning LLM
totals are derived from returned token usage and repository model/list-price
tables (including Anthropic cache rates). Provider invoices remain the
financial authority. Planning SDK calls reserve deterministic no-replay paid
attempts, but cannot poll/resume a provider job because no durable job ID
exists. Tavily/Firecrawl requests record outcome/latency; their dollar cost
stays unknown when the API provides no authoritative usage. Claude Vision
identity also uses a nonresumable fence and blocks ambiguous submission from
replay.

---

## 11. Durable production controls

| Control | Operator surface | Operational boundary |
|---|---|---|
| Crash-resumable full runs | Run page queue banner and `pipeline-state.queue` | SQLite/WAL queue resumes the project checkpoint after a stopped owner and expired lease. One active job per project; stable retry ID. |
| Safe multi-project queue | Queued position plus Cancel | Fixed global concurrency (`PIPELINE_QUEUE_CONCURRENCY`, 1..8); accepting a job is not the same as starting provider work. |
| Paid-media recovery | Run/Review recovery states and `cost-live.attempts` | Durable-ID adapters resume the same task; ambiguous/nonresumable calls fail closed as `accepted_unknown`. This is the paid-media adapter boundary, not universal exactly-once execution. |
| Provider analytics | Run page **Provider analytics** | Success, latency, reservations, failures and known estimated usage from durable paid attempts plus planning/research observations; unknown vendor cost remains unknown and invoices remain authoritative. |
| Provider health | Health status/reasons in Provider analytics | Only `unhealthy` base-video engines are removed from `AUTO`. Unknown/degraded, pinned engines, LLM/image/lipsync/performance routes are not automatically removed. |
| Immutable artifacts | Preview → **Client delivery** → version selectors | Content-addressed bytes and hash-chained history, including generated character assets and paid Gemini/motion/lip-sync outputs rejected locally; retention failure blocks overwriting fallback. `bit_exact=false` remains truthful. Acquired web refs and LLM JSON are project revision data. |
| Client packaging | Preview → **Package selected versions** | Deterministic allowlisted ZIP; explicit historical IDs; hash-qualified immutable download URL. |
| Searchable traces | Run page **Trace** console | Bounded, redacted, project-scoped local index; stdout remains the deployment log stream. |

The protected live canary is separate validation evidence, not runtime health
history. Keep `runpod-pulid-production` and
`runpod-liveportrait-performance` on their distinct endpoints and secrets; one
contract cannot certify the other.

---

*This file is operations-only. For architectural claims, defer to
[ARCHITECTURE.md](ARCHITECTURE.md). §8 `dialogue_voice_mode` section added
2026-06-03 (Chunk 4 Task 9; scoped to §8 only — not a whole-file re-verify).*
