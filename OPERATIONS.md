# Operations guide

This guide covers current installation, day-to-day operation, Windows GPU
workers, verification, recovery, and a safe fresh-start reset.

## 1. Prerequisites

- macOS host with Python 3.13, Node.js/npm, Git, and ffmpeg.
- Windows 11 workstation for optional local GPU execution.
- API credentials only for the cloud routes you intend to use.
- Enough local storage for projects, immutable versions, packages, SQLite
  ledgers, and—if enabled—the FLUX.2 model/cache set.

The Flask app is a local single-operator service. Keep `WEB_BIND_HOST` on
`127.0.0.1`.

## 2. First-time setup

```bash
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

cd web
npm install
cd ..

cp .env.example .env
.venv/bin/python scripts/check_env_example.py
.venv/bin/python scripts/ci_smoke.py
```

Edit `.env` without committing it. Do not paste API keys, bearer tokens, worker
URLs, or provider responses containing secrets into tracked files or issue
logs.

## 3. Environment configuration

### Core cloud credentials

| Route | Environment variables |
| --- | --- |
| Creative LLMs | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, optional `GEMINI_API_KEY` |
| Default cloud image | `GEMINI_API_KEY` |
| FAL image/video/lipsync fallbacks | `FAL_KEY` |
| Google/Veo video | `GOOGLE_API_KEY`, optional `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` plus ADC |
| Runway video and Act-Two | `RUNWAYML_API_SECRET` |
| LTX video | `LTX_API_KEY` or FAL route |
| Kling native fallback | `KLING_ACCESS_KEY`, `KLING_SECRET_KEY` |
| Dialogue/TTS | `ELEVENLABS_API_KEY`, optional `CARTESIA_API_KEY` |
| Music/foley alternatives | `STABILITY_API_KEY`, `SUNO_API_KEY` |
| Research | `FIRECRAWL_API_KEY`, `TAVILY_API_KEY` |

You do not need to fund every provider. A practical starting set is Gemini for
images, one strong video provider or FAL for the cascade, ElevenLabs for audio,
and the local Windows worker if you want zero-provider-charge image/performance
execution. Provider costs shown in the UI are reconciled estimates; invoices
remain authoritative.

### Durable stores

| Variable | Default | Meaning |
| --- | --- | --- |
| `EXPERIMENTS_DB_PATH` | `data/experiments.db` | Provider attempts, costs, and analytics |
| `PIPELINE_JOB_DB_PATH` | `data/pipeline_jobs.db` | Crash-resumable full-project queue |
| `PIPELINE_QUEUE_CONCURRENCY` | `1` | Global project worker count, 1–8 |
| `CINEMA_TRACE_DB_PATH` | `data/telemetry.db` | Searchable project trace index |
| `CINEMA_TRACE_RETENTION_DAYS` | `30` | Trace age bound |
| `CINEMA_TRACE_MAX_EVENTS` | `50000` | Trace row bound |

Use filesystem-backed SQLite files. Memory databases and SQLite URI forms are
rejected for the durable job queue.

### Shared Windows GPU gateway

The normal Mac configuration points both roles to the same authenticated
loopback tunnel, commonly `http://127.0.0.1:18189`:

```dotenv
COMFYUI_SERVER_URL=http://127.0.0.1:18189
COMFYUI_API_KEY_FILE=/absolute/path/to/a/mode-0600-token-file
PERFORMANCE_COMFYUI_SERVER_URL=http://127.0.0.1:18189
PERFORMANCE_COMFYUI_API_KEY_FILE=/absolute/path/to/the-same-mode-0600-token-file
```

The two resolved credentials must be identical when the endpoint is shared.
Direct API-key variables remain supported and outrank their `_FILE` forms.
Leave the URLs unset until the gateway is installed and its exact capabilities
are ready.

## 4. Run and stop

Install or refresh the per-user production shortcut:

```bash
.venv/bin/python scripts/install_cinemaker_shortcut.py
```

Open `Cinemaker` from `~/Applications` or Spotlight. The app-bound launcher
starts the loopback backend at `http://localhost:8080`, opens the browser only
after it answers, writes `logs/cinemaker-launch.log`, and automatically runs
the production web build if `web/dist` was removed. It does not start the
Windows GPU task automatically.

Production-style backend:

```bash
.venv/bin/python web_server.py
```

Frontend development server in another terminal:

```bash
cd web
npm run dev
```

Open `http://localhost:3000`. Stop both foreground processes with `Ctrl-C` and
wait for the queue dispatcher to finish its bounded shutdown. A running lease
left by a terminated process becomes resumable only after it expires; do not
start duplicate ad-hoc pipeline processes to “help” it.

## 5. Local Windows RTX worker

The Windows packages are:

- [deploy/windows-liveportrait-worker/README.md](deploy/windows-liveportrait-worker/README.md)
  for the authenticated unified gateway and LivePortrait capability.
- [deploy/windows-flux2-klein/README.md](deploy/windows-flux2-klein/README.md)
  for FLUX.2 installation, fixed probe, and 1/2/4-reference benchmark.

### Readiness sequence

1. Install/register the LivePortrait worker and Mac loopback tunnel.
2. Verify the `performance-liveportrait` fixed execution proof.
3. Run the FLUX.2 guarded installer against the pinned package.
4. Run exactly one fixed FLUX.2 execution probe.
5. Run the sequential 1-, 2-, and 4-reference benchmark.
6. Start/restart the unified gateway with its FLUX.2 state root.
7. Install the restricted worker-control key described by the LivePortrait
   package; Setup → GPU workers then exposes `Start Windows worker` only while
   the fixed task is stopped and the GPU is idle.
8. From the Mac, require a successful dedicated-control-key `status`, then start
   the worker from Setup and refresh until both roles show their truthful states.
   This is the end-to-end authentication and tunnel proof; an established TCP
   socket alone is not sufficient.
9. In Setup → Image, select Local FLUX.2 only after it becomes enabled.

Before steps 3–6, stop any other workload using the RTX GPU—including game
builds, model inference, rendering, or another ComfyUI session. Installation is
mostly network/disk work, but the probe, benchmark, warm-up, and worker restart
require an idle GPU so memory and latency evidence are valid.

The shared worker has one ComfyUI queue. Both application adapters persist and
resume exact prompt IDs; this prevents duplicate jobs but does not create
parallel GPU capacity. Keep `PIPELINE_QUEUE_CONCURRENCY=1` until you have a
measured reason to increase project concurrency.

The UI intentionally has no Stop control. Stop the task from Windows only after
the queue is known idle; stopping after prompt acceptance can create an
ambiguous outcome that must be reconciled instead of retried.

### Operator-visible states

| State | Meaning |
| --- | --- |
| `not_installed` | Candidate exists but the pinned local artifacts/runtime are absent. |
| `needs_benchmark` | Install and fixed execution probe passed; benchmark remains required. |
| `ready` | Exact hashes, live schema, execution proof, license state, and benchmark passed. |
| `blocked` | A policy, license, manifest, model, authentication, or evidence contract failed. |
| `offline` | A configured worker cannot be reached through the bounded authenticated probe. |

Never infer Ready from port reachability, `/system_stats`, static preflight, or
old evidence.

## 6. Day-to-day UI operation

### Create and configure

Create a project from the project selector. In Setup:

- choose the supported image backend;
- upload clear character and location references;
- configure video, voice, auto-approve, and budget policy;
- inspect GPU worker readiness; and
- save settings before starting a run.

Settings writes are revision-guarded. If another tab changed the project, the
UI refreshes current truth instead of overwriting it.

### Start and monitor

Start generation from Run. Admission writes a durable queue row before the
worker begins. Repeated clicks return the same active job. The page shows queue
position, job ID, running attempt, resume state, cancellation request, and any
operator recovery action.

Run's right rail provides:

- provider success, p95 latency, reconciled estimated usage, reservations,
  unresolved outcomes, and health reasons; and
- searchable project traces by message/fields, level, or exact trace ID.

The `Costs & health` top-bar link returns directly to these surfaces.

### Review gates and UNKNOWN outcomes

Approve only the take you inspected. Provider acceptance, execution, and
approval are separate facts.

If a paid or local GPU request may have been accepted but its outcome is not
known, the UI shows recovery required and suppresses replacement work. Resume
or reconcile the exact job through the offered action. Do not clear SQLite rows,
delete sidecars, or press Generate repeatedly.

### Version and package deliverables

Preview → Client delivery lists current and archived immutable artifact
versions. Inspect recipe/provenance, choose one version per logical deliverable,
then select **Package selected versions**. The server rehashes every selected
file and downloads a deterministic ZIP containing only allowlisted client
deliverables and its manifest.

## 7. Verification

Fast contract checks:

```bash
.venv/bin/python scripts/ci_smoke.py
.venv/bin/python scripts/check_env_example.py
.venv/bin/python scripts/check_skill_twin_parity.py
.venv/bin/python scripts/product_surface_inventory.py --check
.venv/bin/python deploy/windows-flux2-klein/preflight.py
```

Complete backend and frontend checks:

```bash
.venv/bin/pytest -q
cd web
npm test -- --run
npm run build
```

Offline checks do not authorize provider spending or GPU execution. Protected
Runway and Windows LivePortrait canaries are documented in
[docs/LIVE_CONTRACT_CANARY.md](docs/LIVE_CONTRACT_CANARY.md). The FLUX.2 local
probe/benchmark is a separate guarded Windows workflow.

## 8. Common recovery cases

### Unsupported image backend

Open Setup → Image and select Gemini multi-reference, or select Local FLUX.2
only if the live worker is Ready. Unsupported stored values remain unselected
and block the run.

### Local worker is reachable but not ready

Read the blocker code in Setup → GPU workers. Verify endpoint/token equality,
the shared gateway capability response, state-root path, exact package hashes,
execution evidence, benchmark evidence, and current license status. Do not
bypass the UI by editing project JSON.

### Local FLUX.2 result is UNKNOWN

Reconcile the exact durable prompt ID and worker history/output. Do not submit
a replacement image locally or through a cloud fallback until the accepted job
is proven terminal and its artifact disposition is known.

### Paid provider is pending or UNKNOWN

Use the Review recovery action. The provider-attempt ledger retains the exact
request fingerprint and external job ID. A timeout is not evidence that no bill
or output exists.

### Queue job offers an abandon action

Confirm the worker lease is expired and no provider/local job is still active.
Abandon only when the UI says the job is unverifiable and you accept that a
late result could still exist. The action closes the durable queue row; it does
not erase external work.

### Trace or analytics page is empty

Verify the project has produced events/attempts and the SQLite paths are
writable. Analytics excludes nonterminal outcomes from terminal latency and
labels insufficient or malformed evidence `unknown`.

### Project lock conflict

Let the active queue/direct-stage operation finish. Lock conflicts prevent
concurrent project mutation and are safer than forcing an overlapping write.

## 9. Fresh-start reset

A clean start removes runtime-owned project data and test residue, not source,
fixtures, dependencies, Git metadata, registered worktrees, or tracked
sentinels.

Before cleanup:

1. Stop backend/frontend/test processes and wait for leases/tests to exit.
2. Confirm no Windows probe or benchmark is running.
3. Inventory `domain/projects`, legacy top-level `projects`, local SQLite files,
   caches, logs, temp outputs, and bytecode.
4. Move the exact runtime-owned paths to a timestamped Trash folder rather than
   deleting them permanently.
5. Preserve tracked `.gitkeep` files, source test fixtures, accepted worker
   evidence needed for the current release, `.venv`, `node_modules`, `.git`, and
   registered worktrees.
6. Re-run smoke, tests, build, and product inventory after cleanup.

Do not use a recursive deletion against the repository root, home directory,
an unresolved variable, or a broad volume path.

## 10. Operational truth boundaries

- UI provider cost is a reconciled estimate, not invoice truth.
- Local GPU routes have no provider charge, but electricity/hardware cost is
  not invoice-tracked.
- Artifact history preserves exact prior bytes and recipe/provenance; stochastic
  regeneration is not promised bit-exact.
- Trace search is local to this app, not an external log service.
- Automatic health avoidance affects AUTO base-video routing only.
- Explicit provider pins and local-backend selections fail closed rather than
  silently changing operator intent.
