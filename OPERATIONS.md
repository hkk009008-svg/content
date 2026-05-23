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
| `GEMINI_API_KEY` | Optional | Opt-in Gemini dispatch via `models=["gemini-2.5-pro", ...]` |
| `GOOGLE_API_KEY` | Optional | Veo direct API path (falls back to Vertex AI if absent) |

### Video generation

| Var | Required? | Used by |
|---|---|---|
| `KLING_ACCESS_KEY` + `KLING_SECRET_KEY` | Recommended (primary video) | KLING_NATIVE engine — JWT auth |
| `FAL_KEY` | Recommended (used by many cascades) | FAL routes: Sora, Veo (fal proxy), Kling 3.0, LTX (proxy), Hedra, all lipsync engines, music, FLUX image fallback |
| `LTX_API_KEY` | Optional | LTX_NATIVE direct (preferred over FAL proxy) |
| `RUNWAYML_API_SECRET` | Optional | RUNWAY_GEN4, RUNWAY (gen3a_turbo), Act-One performance |
| `SEEDANCE_API_KEY` | Optional | SEEDANCE engine (action cascade only) |

### Audio + performance capture

| Var | Required? | Used by |
|---|---|---|
| `ELEVENLABS_API_KEY` | Yes (TTS) | Dialogue voiceover, voice direction profiles, foley (when reactivated) |
| `CARTESIA_API_KEY` | Optional | Cartesia Sonic 2 TTS path |
| `STABILITY_API_KEY` | Optional | Stable Audio 2 foley generator (currently dormant in audio/ — see DECISIONS.md) |
| `SUNO_API_KEY` (+ `SUNO_API_BASE`) | Optional | Suno V5 BGM (defaults to FAL Stable Audio) |
| `VIGGLE_API_KEY` | Optional | Viggle performance capture (Mode A only) |
| `HEDRA_API_KEY` | Optional | Direct Hedra REST fallback (FAL proxy is the preferred path) |

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

The pipeline needs a ComfyUI pod for image generation (production + max
tier) and certain performance capture paths (LivePortrait, SadTalker).

### Recommended pod spec

- **GPU:** A40 / A100 / RTX 6000 Ada (≥24GB VRAM) — required for FLUX +
  PuLID + SUPIR. Max tier uses heavy stacks.
- **Disk:** ≥50GB (models + temp output)
- **Network:** ComfyUI listens on `:8188` by default. Expose this port.

### Bootstrap script

`scripts/setup_runpod.sh` installs ComfyUI + the custom node packs the
workflows depend on. Run it on the pod after first boot.

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
| `pulid.json` | Production-tier keyframe gen — `phase_c_assembly.generate_ai_broll` |
| `pulid_max.json` | Max-tier — `quality_max.generate_ai_broll_max` |

Both are loaded once per process (module-level cache, lock-guarded) and
deep-copied per shot. Operator-side edits to the workflow JSONs take
effect on next process restart.

### Model files required on the pod

For production (`pulid.json`):
- FLUX.1-dev base
- PuLID-FLUX face encoder weights
- ArcFace / InsightFace landmark model

For max (`pulid_max.json`) — adds:
- AlignYourSteps scheduler weights
- LAION Aesthetic Predictor v2 (`shunk031/aesthetics-predictor-v2-sac-logos-ava1-l14-linearMSE`)
- CLIP ViT-L/14 (`openai/clip-vit-large-patch14`)
- SUPIR V2 (~35GB)
- Optional: HiDream-I1-Full (only loaded if operator selects HIDREAM_I1 image API)

---

## 7. Verification — smoke + tests

### §15 smoke (run at every session start)

```bash
.venv/bin/python -c "
import cinema_pipeline
from cinema.context import PipelineContext, get_project_setting
from phase_c_vision import _get_shared_validator
from phase_c_assembly import generate_ai_broll
from identity import get_shared_validator
from face_validator_gate import _get_validator as fvg
from performance.identity_gate import _get_validator as pig
a, b = _get_shared_validator(), _get_shared_validator()
c, d, e = get_shared_validator(), fvg(), pig()
assert a is b is c is d is e, 'singleton broken'
ctx = PipelineContext(global_settings={'tts_provider': 'CARTESIA_SONIC_2'})
assert get_project_setting(ctx, 'tts_provider') == 'CARTESIA_SONIC_2'
print('OK')
"
```

### Unit tests

```bash
.venv/bin/python -m pytest tests/unit/ -q
```

Expected: 6 pass, 3 skipped (3 documented pre-existing mock-drift failures).

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

### Force re-index GitNexus

```bash
npx gitnexus analyze --embeddings
```

Without `--embeddings`, previously generated embeddings are deleted (per
the script's behavior). Always pass `--embeddings` to preserve them.

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

### Project lock timeout (`Timeout while waiting for project.lock`)

Another process is holding the per-project filelock. Likely a previous
`web_server.py` instance still alive. Check `ps aux | grep web_server`
and kill stale processes.

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
| Hedra Character-3 | ~$0.05/shot | Mode-B driving-video synthesis (cached) |
| Act-One performance | ~$0.10/shot | Per-shot, semaphore-limited |
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
[ARCHITECTURE.md](ARCHITECTURE.md).*
