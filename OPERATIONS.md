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
- §5 [Pod setup — RunPod / Railway ComfyUI](#5-pod-setup--runpod--railway-comfyui)
- §6 [ComfyUI workflows & models](#6-comfyui-workflows--models)
- §7 [Verification — smoke + tests](#7-verification--smoke--tests)
- §8 [Common operational tasks](#8-common-operational-tasks)
- §9 [Troubleshooting](#9-troubleshooting)
- §10 [Costs at a glance](#10-costs-at-a-glance)

---

## 1. Prerequisites

| Requirement | Why |
|---|---|
| **Python 3.13** | PEP 604 union syntax + recent `concurrent.futures` semantics. 3.11+ is the floor but 3.13 is the tested target. |
| **Node 20+ / npm** | Vite 6 dev server + TypeScript 5.7 |
| **macOS or Linux** | `audio/effects.py` uses macOS AU plugins where available; Linux falls back to FFmpeg. Pedalboard works on both. |
| **ffmpeg** in PATH | Stitching, color grade, two-pass loudnorm, frame extraction. `brew install ffmpeg`. |
| **RunPod or Railway ComfyUI pod** | Image generation (production tier + max tier both call ComfyUI). LivePortrait + SadTalker also run on this pod. |
| **Cloud API keys** (~17 providers) | See §3 |
| **Disk space** | ~50GB for cache + projects + exports. ArcFace weights are auto-downloaded by DeepFace (~700MB). |

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
| `GEMINI_API_KEY` | Optional | Opt-in Gemini dispatch via `models=["gemini-2.5-pro", ...]`; also `gemini_omni_native.GeminiOmniAPI` (video, WS2 `GEMINI_OMNI` — the `target_api` PRIMARY for all shot types) and `gemini_image_native.GeminiImageAPI` (image, WS3 Nano Banana — the image PRIMARY for all projects). Both accept either this or `GOOGLE_API_KEY` (`settings.google_api_key or settings.gemini_api_key`). |
| `GOOGLE_API_KEY` | Optional | Veo direct API path (falls back to Vertex AI if absent); also `gemini_omni_native.GeminiOmniAPI` (video) and `gemini_image_native.GeminiImageAPI` (image) — same either-key contract as `GEMINI_API_KEY` above. |

### Video generation

| Var | Required? | Used by |
|---|---|---|
| `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` | Optional (legacy fallback) | KLING_NATIVE — legacy kling-v1-6 JWT route (fallback + storyboard mode; primary Kling is fal KLING_3_0 via FAL_KEY since 2026-07-11) |
| `FAL_KEY` | Recommended (used by many cascades) | FAL routes: Seedance (action primary since 2026-07-11), Sora, Veo (fal proxy), Kling 3.0, LTX (proxy), all lipsync engines, music, FLUX image fallback |
| `LTX_API_KEY` | Optional | LTX_NATIVE direct (preferred over FAL proxy) |
| `RUNWAYML_API_SECRET` | Optional | RUNWAY_GEN4, RUNWAY (gen3a_turbo), Act-Two performance |

### Audio + performance capture

| Var | Required? | Used by |
|---|---|---|
| `ELEVENLABS_API_KEY` | Yes (TTS) | Dialogue voiceover, voice direction profiles, foley (when reactivated) |
| `CARTESIA_API_KEY` | Optional | Cartesia Sonic 2 TTS path |
| `STABILITY_API_KEY` | Optional | Stable Audio 2 foley generator (currently dormant in audio/ — see DECISIONS.md) |
| `SUNO_API_KEY` (+ `SUNO_API_BASE`) | Optional | Suno V5 BGM (defaults to FAL Stable Audio) |
| `VIGGLE_API_KEY` | Optional | Viggle performance capture (Mode A only) |

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
| `PEXELS_API_KEY` | Optional | Stock footage fallback (rarely hit) |

### Infrastructure

| Var | Default | Purpose |
|---|---|---|
| `COMFYUI_SERVER_URL` | `http://127.0.0.1:8188` | Pod address. Set to your RunPod/Railway URL. |
| `EXPERIMENTS_DB_PATH` | `data/experiments.db` | SQLite cost tracker DB |
| `PERFORMANCE_CACHE_DIR` | `data/cache/driving` | Content-hash cache for Mode-B driving videos |
| `MOTION_GATE_SAMPLES` | `8` | Number of frame pairs sampled by `motion_gate.score_motion_fidelity` |
| `IDENTITY_EMBED_MODEL` | `GhostFaceNet` | DeepFace embedding backbone for identity QC (single chokepoint: `identity.validator.EMBED_MODEL`). ⚠️ All calibrated identity thresholds assume GhostFaceNet scores — non-default values (e.g. `Buffalo_L`, non-commercial license) fire a structural warning and need a pod re-calibration pass before the gates are meaningful. |
| `WEB_BIND_HOST` | `127.0.0.1` | Flask bind. Set to `0.0.0.0` for LAN access (then tighten `WEB_CORS_ORIGINS`). |
| `WEB_CORS_ORIGINS` | `localhost-only dev origins` | Comma-separated origin allowlist. `*` opts back into the pre-hardening wide-open behavior. |

### Minimal viable config

For a working "happy path" run you need:
- `ANTHROPIC_API_KEY` + `OPENAI_API_KEY` (LLM)
- `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` OR `FAL_KEY` (video — at least one cascade path live)
- `ELEVENLABS_API_KEY` (TTS — audio path)
- `COMFYUI_SERVER_URL` pointing at a working pod (image gen)

Everything else expands capability or adds fallback paths.

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

`Ctrl+C` the Flask process. Daemon threads die with the process. Any
in-flight cloud API call will complete (FAL/cloud APIs are sync-poll
servers), but the local state won't persist past the `None` sentinel to
the SSE queue. If a pipeline is mid-run, the checkpoint may not reflect
the latest progress — resume will replay the last completed scene.

To cancel a single project's run without killing the server:
```bash
curl -X POST http://localhost:8080/api/projects/<pid>/cancel
```

---

## 5. Pod setup — RunPod / Railway ComfyUI

The pipeline needs a ComfyUI pod for image generation (production tier,
`pulid.json`) and certain performance capture paths (LivePortrait, SadTalker).

### Recommended pod spec

- **GPU:** RTX 4090 (24GB) recommended. The production `pulid.json` graph is
  all-fp8 (FLUX-dev-fp8 ~12GB + t5xxl-fp8 ~5GB + PuLID) and fits comfortably
  in 24GB. The max tier (SUPIR/48GB+) that used to justify a bigger card
  (A40/A100/RTX 6000 Ada) was retired in WS1, so a big card is no longer needed.
- **Disk:** models ~21GB + Python env (torch/CUDA/insightface) ~10-12GB +
  ComfyUI+nodes ~1GB + working/output ~5-10GB. Use an **80GB network volume
  mounted at `/workspace`** for full-setup persistence (ComfyUI + nodes +
  models all survive a pod restart, no re-download) — or 40GB if you only
  want to persist the models and reinstall the rest per-pod.
- **Network:** ComfyUI listens on `:8188` by default. Expose this port.

### Bootstrap script

`scripts/setup_runpod.sh` installs ComfyUI + the custom node packs the
workflows depend on (incl. `ComfyUI-PuLID-Flux`), the InsightFace runtime
stack + `antelopev2` model that `PulidInsightFaceLoader` needs to register,
and runs a post-start `/object_info` check that the PuLID nodes are
available (C-D4 guard). Run it on the pod after first boot; it targets
`$WORKSPACE` (default `/workspace`, RunPod's persistent network volume) so
a restarted pod doesn't re-download anything already there.

The script is production-only — the max tier (`--max`/`--max-fp16`: SUPIR,
Impact-Pack + Subpack, Detail-Daemon, fp16/Redux gated downloads, ReActor)
was retired in WS1 and those flags no longer exist.
[docs/RUNBOOK-max-tier-test.md](docs/RUNBOOK-max-tier-test.md) documents that
retired tier's provisioning steps; treat it as historical.

### torch / CUDA build (driver-dependent)

The pod's torch build must match the **host NVIDIA driver's max CUDA**, not just
the GPU model. A `cuXYZ` wheel only uses the GPU if the driver supports CUDA ≥ X.Y —
e.g. cu130 wheels need a CUDA-13.0 driver, but common Novita/RunPod hosts cap at
CUDA 12.4 (driver 550.x on an RTX 6000 Ada), where cu130 silently can't see the GPU.
ComfyUI also **hard-imports torchaudio** at startup, so torch / torchvision /
torchaudio must be installed as **one matched set per channel** or ComfyUI crashes
with `undefined symbol ..._ZNK5torch8autograd4Node4nameEv` (the lesson from `3fe8299`).

`setup_runpod.sh` (step 5) handles this automatically: it reads the driver's max
CUDA from `nvidia-smi`'s `CUDA Version: X.Y` header and installs the matched stack:

| Driver max CUDA | Channel | torch / torchvision / torchaudio | Verified on |
|---|---|---|---|
| ≥ 13.0 | `cu130` | 2.11.0 / 0.26.0 / 2.11.0 | H100 sm_90 |
| ≥ 12.4 | `cu124` | 2.6.0 / 0.21.0 / 2.6.0 | RTX 6000 Ada (Novita) |
| ≥ 11.8 | `cu118` | 2.4.1 / 0.19.1 / 2.4.1 | — |

If detection fails (no `nvidia-smi`, or a driver older than CUDA 11.8) the script
warns and defaults to `cu124`. **Check the driver first** — `nvidia-smi` top-right
shows `CUDA Version`. If a build still fails with a torch/CUDA error, override the
pin in `setup_runpod.sh` step 5 to the channel matching that driver, keeping torch /
torchvision / torchaudio as one matched set (note: cu124's highest torch is 2.6.0 —
torch 2.11.0 is cu130-only).

### Required custom nodes

The pruning logic in `quality_max.py:_probe_node_availability` removes any
node not on the pod. The full max-tier capability needs:

- PuLID-FLUX (`ApplyPulidFlux`, `PulidFluxModelLoader`, `PulidFluxInsightFaceLoader`)
- FLUX Union ControlNet Pro (Shakker-Labs)
- FLUX Redux (`StyleModelApplyAdvanced`)
- `SkipLayerGuidanceDiT`, `FreeU_V2`, `DifferentialDiffusion`
- `AlignYourStepsScheduler`, `DetailDaemonSamplerNode`
- `LatentBlend`, `LatentUpscaleBy`
- `DepthAnythingV2Preprocessor`, `DWPreprocessor`, `CannyEdgePreprocessor`
- `FaceDetailer` (Impact Pack)
- `SUPIR_model_loader_v2`, `SUPIR_sample`, `SUPIR_decode`
- `LivePortraitProcess` (Kijai's port, for LivePortrait performance capture)
- `SadTalker` (for Mode-B driving-video synthesis)

Missing nodes degrade gracefully — production tier strips them and runs
`pulid.json`; max tier falls back to production if `pulid_max.json` can't
load.

### Cost control

ComfyUI pods bill by the second. Idle pods cost real money. Options:
- Run on RunPod's autoscale tier
- Manually stop the pod when not actively generating
- For development, use FAL-only paths (skip max tier; bypass PuLID workflow)

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

For production (`pulid.json`), installed by `scripts/setup_runpod.sh`:
- FLUX.1-dev fp8 checkpoint (`flux1-dev-fp8.safetensors`, ~12GB)
- T5-XXL fp8 + CLIP-L text encoders (`t5xxl_fp8_e4m3fn.safetensors`, `clip_l.safetensors`)
- FLUX VAE (`ae.safetensors`)
- PuLID-FLUX face encoder weights (`pulid_flux_v0.9.1.safetensors`)
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

Subscribe to progress:
```bash
curl -N http://localhost:8080/api/projects/<pid>/stream
```

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
curl http://localhost:8080/api/cost-live | jq
```

The cost DB is SQLite at `EXPERIMENTS_DB_PATH` — open with any sqlite
client for forensic analysis.

### Clean up old projects

```bash
curl -X POST http://localhost:8080/api/cleanup
```

Removes temp files / unreferenced shots. Doesn't delete projects themselves.

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
return JSON. If it doesn't, the pod is down, throttled, or the URL is wrong.

### SSE connection drops repeatedly

Bundle-C 3.1 added exponential-backoff reconnect (1s/2s/4s/.../30s, 10
attempts). If you're seeing repeated drops in the browser console, check:
- Network stability between client and `web_server.py`
- Whether `web_server.py` daemon thread crashed (SSE generator emits END)
- Whether a corporate proxy is closing long-lived connections (set
  `WEB_BIND_HOST=0.0.0.0` and access via LAN IP to bypass localhost
  proxying quirks)

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

Another process is holding the per-project filelock
(`domain/projects/<pid>.lock` — a sibling of the project directory, removed
automatically on release). Likely a previous `web_server.py` instance still
alive. Check `ps aux | grep web_server` and kill stale processes.

---

## 10. Costs at a glance

Rough order-of-magnitude per shot (current 2026-05 prices, will drift):

| Provider | Per shot (typical) | Notes |
|---|---|---|
| Anthropic (Sonnet) | $0.01–0.05 | Several calls per scene (chief director, decomposer, optimizer) |
| OpenAI (GPT-4o) | $0.02–0.10 | Parallel-quorum competitor in LLM ensemble; doubles cost when `competitive_generation=True` |
| Kling Native | $0.10–0.30 | 5s video, image-to-video |
| Sora 2 (via FAL) | $0.30–0.60 | Action cascades hit this; longer if 8s+ |
| Runway Gen4 | $0.30–0.40 | Premium fallback |
| LTX | $0.05–0.15 | Cheapest video provider |
| SadTalker | ~$0.045/5s shot (GPU-time estimate) | Mode-B driving-video synthesis (cached) |
| Act-Two performance | ~$0.25/shot (5s @ $0.05/s) | Per-shot, semaphore-limited; cost_tracker's `ACT_ONE` key name is legacy, retargeted to Act-Two |
| ElevenLabs TTS | $0.005–0.02/shot | Per dialogue line |
| FAL Stable Audio BGM | $0.05/project | Once per project, 47s loop |
| Lipsync (overlay) | $0.03–0.15 | Per shot; cascade tries up to 4 engines |
| RunPod ComfyUI pod | $0.30/hour ÷ throughput | Idle billing hurts; quota-watch is on you |

For a 20-shot project with max tier + lipsync, expect **$10–30 in cloud
costs** plus pod time. Budget control is via `global_settings.budget_limit_usd`
on the project — when exceeded, `ShotController.generate_motion_take`
calls `lifecycle.pause()` to halt at the next checkpoint.

---

*This file is operations-only. For architectural claims, defer to
[ARCHITECTURE.md](ARCHITECTURE.md). §8 `dialogue_voice_mode` section added
2026-06-03 (Chunk 4 Task 9; scoped to §8 only — not a whole-file re-verify).*
