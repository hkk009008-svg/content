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
| Strategic direction + open critique from current leadership | [docs/STRATEGIC_REVIEW-2026-06-10.md](docs/STRATEGIC_REVIEW-2026-06-10.md) |
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

- **Backend:** Python 3.13, Flask + SSE (per-subscriber broadcast bus with replay), ~17 cloud API providers
- **Frontend:** React 19 + Vite 6 + Tailwind 3, no router (4-mode `useState`: Setup / Edit / Run / Capability)
- **Image generation:** Gemini 3.1 Flash Image ("Nano Banana 2") is the default primary; ComfyUI + PuLID is the reference-conditioned fallback. Single production tier — the old max tier (N=8 adaptive best-of) was retired.
- **Video generation:** Gemini Omni Flash (native audio) is the default primary; a typed 9-engine fallback cascade follows (Kling / Veo / LTX / Runway / SEEDANCE / …). Sora is a dated pre-sunset fallback only (retires 2026-09-24).
- **Identity:** GhostFaceNet via DeepFace, process-singleton, 4-way access converge
- **LLMs:** Anthropic + OpenAI parallel quorum + judge (Gemini opt-in)
- **Audio:** ElevenLabs (TTS) + FAL Stable Audio (BGM) + Pedalboard (DSP)
- **Lipsync:** 4-engine overlay cascade + 2-engine generation cascade, all FAL

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

The post-pivot codebase is stable and shipping. A comprehensive product-
unification pass is in progress (provider-contract repair, project-scoped
state authority, portable media, documentation truth) — see
`docs/superpowers/plans/2026-07-30-comprehensive-product-unification.md` for
the live task board. Prior strategic direction is tracked in
[docs/STRATEGIC_REVIEW-2026-06-10.md](docs/STRATEGIC_REVIEW-2026-06-10.md).

**CI:** Three jobs run on every push to `main` and every pull request —
`ARCHITECTURE.md §15` singleton/ctx smoke, `pytest tests/unit/`, and
`tsc --noEmit`. See [.github/workflows/ci.yml](.github/workflows/ci.yml).
**CI status:** the pytest job collects and passes — the collection-time
sys.path gap was closed in `0326f24a` (NF-1 of the 2026-06-10 strategic
review) by adding `[tool.pytest.ini_options] pythonpath = ["."]` to
`pyproject.toml`. See [.github/workflows/ci.yml](.github/workflows/ci.yml)
for the live suite and its current pass count.

Last architecture verification: see the `*Last verified: ...*` footer in
[ARCHITECTURE.md](ARCHITECTURE.md).
