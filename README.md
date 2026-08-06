# Content — interactive AI cinema pipeline

Content turns a concept into a reviewed cinematic short. The web application
manages story planning, reference-conditioned keyframes, performance capture,
motion video, dialogue and sound, review gates, final assembly, immutable
artifact history, and client delivery packages.

This is a local, single-operator production tool. It is not a multi-tenant
service, and the Flask application must remain loopback-only.

## Start here

| Goal | Document |
| --- | --- |
| Run, configure, verify, or troubleshoot the application | [OPERATIONS.md](OPERATIONS.md) |
| Understand the production architecture and safety boundaries | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Learn the UI and the complete operator workflow | [docs/PROGRAM-MANUAL.md](docs/PROGRAM-MANUAL.md) |
| Review settled architectural decisions | [DECISIONS.md](DECISIONS.md) |
| Run an explicitly authorized live contract check | [docs/LIVE_CONTRACT_CANARY.md](docs/LIVE_CONTRACT_CANARY.md) |
| Work in the repository as Codex or another agent | [AGENTS.md](AGENTS.md) |
| Work in the repository as Claude Code | [CLAUDE.md](CLAUDE.md) |

Historical plans, handoffs, and investigations are evidence of earlier states;
they do not override these active documents or current source and tests.

## Quick start

```bash
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

cd web
npm install
cd ..

cp .env.example .env
.venv/bin/python web_server.py
```

In a second terminal:

```bash
cd web
npm run dev
```

Open `http://localhost:3000`. The frontend proxies `/api` to the loopback Flask
server.

For the Finder/Spotlight production launcher, install the tracked app once:

```bash
.venv/bin/python scripts/install_cinemaker_shortcut.py
```

Open `Cinemaker` from `~/Applications`. The launcher serves the production UI
on `http://localhost:8080` and automatically rebuilds ignored `web/dist` output
when a fresh-start cleanup removed it.

Before a production session, run:

```bash
.venv/bin/python scripts/ci_smoke.py
cd web && npm test -- --run && npm run build
```

## Current production routes

- Image generation defaults to Gemini multi-reference. A local FLUX.2 Klein
  4B route appears in Setup only when the authenticated Windows worker proves
  its exact package, model, workflow, fixed execution canary, license review,
  and 1/2/4-reference benchmark. Guarded FAL and Pollinations routes remain
  the supported cloud fallbacks.
- Local performance capture uses the same Windows RTX worker through the
  role-bound LivePortrait capability. Cloud performance adapters remain
  explicit alternatives where configured.
- Motion generation uses the typed video-provider catalog and project policy.
  AUTO routing can avoid providers whose reconciled recent outcomes score
  unhealthy; an operator-pinned provider is never silently overridden.
- Identity validation uses the shared GhostFaceNet validator and approved
  project reference images. Removed image-training and provider-tuning
  controls are not stored, rendered, or dispatched.

## Durable production controls

The application includes the seven production controls exposed in the UI:

1. Crash-resumable full-project jobs with idempotent queue admission and
   durable checkpoints.
2. Provider success, latency, unresolved-job, reservation, and reconciled-cost
   analytics.
3. A bounded durable queue for safely running multiple projects.
4. Immutable artifact versions with hashes, recipes, dependencies, and source
   provenance.
5. Automatic provider health scoring for AUTO video routing.
6. One-click deterministic ZIP packaging of verified client deliverables.
7. Project-scoped searchable structured traces with secret-safe fields.

Run shows queue state, provider health, costs, and traces. Preview exposes
artifact versions and client packaging. Setup exposes GPU readiness, a guarded
start-only Windows worker control, and only enables the local image route after
live proof.

## Stack

- Python 3.13, Flask, SQLite, SSE, and a phase-oriented cinema orchestrator.
- React 19, Vite, Tailwind, Vitest, Testing Library, and automated accessibility
  checks.
- Immutable JSON/project state plus SQLite ledgers for jobs, provider attempts,
  costs, and traces.
- Local Windows 11 RTX execution behind an authenticated loopback/LAN tunnel;
  API keys and worker endpoints stay server-side.

Source, tests, live readiness records, immutable evidence, and current Git state
are authoritative. A static config value, reachable port, successful schema
probe, or old benchmark never implies production readiness by itself.
