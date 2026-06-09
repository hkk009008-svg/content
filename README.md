# Content — Interactive AI Cinema Pipeline

A topic-to-cinematic-short pipeline. Operator drives via a web UI; the system
generates per-shot keyframes, performance capture, motion video, dialogue
audio, foley/BGM, and stitches a 1–2 minute final cut. Four operator review
gates (PLAN / KEYFRAME / PERFORMANCE / REVIEW) ensure identity, continuity,
and motion quality before the assembly stage.

This is a single-operator, single-machine tool. Not a multi-tenant SaaS.

---

## What's where

| Need to | Read |
|---|---|
| Understand the codebase (entry, orchestrator, phases, gates, all subsystems) | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Learn the whole program end-to-end + drive it to max capability (macro + micro + user manual) | [docs/PROGRAM-MANUAL.md](docs/PROGRAM-MANUAL.md) |
| Run it locally / set up env / troubleshoot | [OPERATIONS.md](OPERATIONS.md) |
| See WHY the architecture is shaped this way (settled decisions) | [DECISIONS.md](DECISIONS.md) |
| Strategic direction + open critique from current leadership | [docs/STRATEGIC_REVIEW-2026-05-24.md](docs/STRATEGIC_REVIEW-2026-05-24.md) |
| Execute a session from the roadmap (operator manual) | [docs/HANDOFF-roadmap-2026-05-24.md](docs/HANDOFF-roadmap-2026-05-24.md) |
| Work in this repo as Claude Code | [CLAUDE.md](CLAUDE.md) |
| Work in this repo as another AI agent (Cursor, Aider, Copilot, Codex, …) | [AGENTS.md](AGENTS.md) |
| See what was true at past handoff dates | [docs/archive/](docs/archive/) |

---

## 30-second quick start

```bash
# Python 3.13 venv + deps
/opt/homebrew/bin/python3.13 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Frontend
cd web && npm install && cd ..

# API keys (fill in)
cp .env.example .env

# Smoke test
.venv/bin/python -c "import cinema_pipeline; print('OK')"

# Run (Flask backend on :8080 + Vite dev on :3000 with /api proxy)
.venv/bin/python web_server.py &
cd web && npm run dev
```

Open `http://localhost:3000`.

For pod setup (ComfyUI workflows, models), see [OPERATIONS.md](OPERATIONS.md).

---

## Stack at a glance

- **Backend:** Python 3.13, Flask + SSE, ~17 cloud API providers
- **Frontend:** React 19 + Vite 6 + Tailwind 3, no router (3-mode `useState`)
- **Image generation:** ComfyUI + PuLID (production) / N=8 adaptive best-of (max tier)
- **Video generation:** 9-engine cascade (Kling / Sora / Veo / LTX / Runway / SEEDANCE / …)
- **Identity:** GhostFaceNet via DeepFace, process-singleton, 4-way access converge
- **LLMs:** Anthropic + OpenAI parallel quorum + judge (Gemini opt-in)
- **Audio:** ElevenLabs (TTS) + FAL Stable Audio (BGM) + Pedalboard (DSP)
- **Lipsync:** 4-engine overlay cascade + 4-engine generation cascade, all FAL

---

## Project conventions in 60 seconds

1. **One entry point** — `web_server.py` → `cinema_pipeline.py:CinemaPipeline`. No CLI.
2. **Truth lives in `ARCHITECTURE.md`** — every claim there is cross-referenced to file:line and verified against source.
3. **Per-project settings via `get_project_setting(ctx, ...)`** — never `getattr(settings, ...)`. The frozen `Settings` dataclass is env-derived API keys ONLY.
4. **Identity is a singleton** — always reach for `identity.get_shared_validator()`. Four backward-compat aliases exist; all converge.
5. **Gates use predicate-poll** — operator approvals via REST mutate `project.json`; the worker thread polls disk state every 500ms. State survives crashes and SSE disconnects.
6. **One commit per logical slice** — run the §15 smoke block in ARCHITECTURE.md before declaring done.

---

## Status

The post-pivot codebase is stable and shipping. There is no active migration.
Strategic direction and open work are tracked in
[docs/STRATEGIC_REVIEW-2026-05-24.md](docs/STRATEGIC_REVIEW-2026-05-24.md).

**CI:** Three independent jobs run on every push to `main` and every pull
request — `ARCHITECTURE.md §15` singleton/ctx smoke, `pytest tests/unit/`,
and `tsc --noEmit`. All must pass. See [.github/workflows/ci.yml](.github/workflows/ci.yml).
Baseline 2026-05-24: 478 pass / 3 skip / 0 fail.

Last architecture verification: see the `*Last verified: ...*` footer in
[ARCHITECTURE.md](ARCHITECTURE.md).
