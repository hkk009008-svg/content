<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Content** (2836 symbols, 17637 relationships, 239 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/Content/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/Content/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Content/clusters` | All functional areas |
| `gitnexus://repo/Content/processes` | All execution flows |
| `gitnexus://repo/Content/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

# About this document

This file is the **agent-agnostic root** for AI coding tools working in this
repo (Cursor, Aider, Copilot, Continue, Claude Code, etc.). The GitNexus
block above is auto-managed and identical to the one in `CLAUDE.md`.
Everything below is the agent-agnostic project guide — canonical project
facts plus the discipline that ships clean code here.

**Claude Code specifically:** `CLAUDE.md` is the Claude-specific companion.
It mirrors this file's discipline section using Claude's actual tool
syntax (`Agent` subagent dispatch, `subagent_type` values, prompt
templates, `Skill` invocation, `TaskCreate`/`TaskUpdate`,
`AskUserQuestion`, the `superpowers:subagent-driven-development` skill,
etc.). Claude Code agents read **both** files; this one defines the
principles, `CLAUDE.md` defines the mechanics.

**Non-Claude agents:** read this file as your source of truth. Translate
the principles ("fresh context per task", "two-stage review",
"verify-before-acting") into your tool's analogous mechanisms (new chat
session, manual diff review, `git grep` for verification, etc.).

# Session-start protocol (read me first)

**This file, `CLAUDE.md`, `HANDOFF.md`, and the user's memory files
drift from the actual code between sessions.** A few claims were wrong
when written; more become wrong as commits land. Before doing any
non-trivial work, verify the claims in this doc against the current
source. If a claim is stale, **fix this file in the same change** that
exposes the staleness — don't let a wrong claim survive your session.

Concrete protocol at session start (≤2 minutes):

1. Run the smoke block from the "Invariants" section below. If it
   fails, the doc is stale OR the working tree is broken — fix one or
   the other before proceeding with the user's task.
2. Spot-check "Single entry point" and "Top-level package layout":
   `ls cinema/ cinema/phases/`, `grep -n "^from cinema.phases" cinema_pipeline.py`,
   `wc -l cinema_pipeline.py web_server.py phase_c_ffmpeg.py`. Compare to
   what this file claims.
3. `git log --oneline -20` — if a recent commit touched a module
   mentioned here, re-read that section against the new code.
4. **If you find a stale claim:** edit this file first, in the same
   commit (or a "docs:" prep commit right before) the user's task lands.
   The user has stated this as a standing requirement.

Trust the code; update the prose when it diverges.

# Architecture Preamble

Interactive AI cinema pipeline. **Pivot complete (2026-05-23):** the
project was originally a YouTube Shorts generator (CLI entry `main.py`),
pivoted to interactive cinema production with operator review gates.
The CLI and all YouTube-era components are deleted — `main.py` no longer
exists at the repo root. There is now **one entry point** to the
production pipeline.

> `HANDOFF.md` at the repo root is the session-journal companion. When
> this Architecture Preamble and HANDOFF disagree, **this file wins**
> — HANDOFF is journal-shaped (what changed last session), this file
> is current-state-shaped (what's true now).

## Single entry point

- **`web_server.py`** (Flask + SSE, ~1647 LOC, no auth, wide-open CORS)
  → **`cinema_pipeline.py:CinemaPipeline`** (~1004 LOC) — interactive
  dashboard with pause/resume + SSE progress + four operator review
  gates: **PLAN_REVIEW**, **KEYFRAME_REVIEW**, **PERFORMANCE_REVIEW**
  (auto-skipped if all shots routed to SKIP), **REVIEW**.
- The three Phase classes (`KeyframeRenderPhase`, `PerformanceCapturePhase`,
  `MotionRenderPhase`) **live under `cinema/phases/`**, not inline in
  `cinema_pipeline.py`. The orchestrator imports them at file top
  (`cinema_pipeline.py:25-27`) and calls `phase.run(ctx)` directly. It
  does NOT use the `cinema.pipeline` generic driver — that driver class
  exists at `cinema/pipeline.py` but has **zero callers** today.
- `CinemaPipeline.__init__` composes:
  - **`PipelineCore`** (long-lived per-project deps: project dict,
    continuity, director, cost_tracker, ensemble) — built via
    `cinema.core.build_pipeline_core(pid)`.
  - **`ThreadedLifecycle`** (cancel/pause/gate-wait/progress).
  - **`RunState`** (per-run mutable: shot_results, scene_clips,
    current_*, completed_scene_indices).
  - **`ShotController`** (per-shot work — keyframe / performance /
    motion / regenerate / diagnose / correct).
  - **`ReviewController`** (gates + take approvals).
  - **`CheckpointStore`** (atomic JSON resume).
  The forwarder block marked `# GENERATED BEGIN/END` in `cinema_pipeline.py`
  is autogenerated by `tools/gen_delegates.py` — don't edit by hand.

## Top-level package layout

| Path | Owns |
|------|------|
| `cinema/` | Orchestration substrate. `context.py` → `PipelineContext` + `get_project_setting`. `core.py` → `PipelineCore` + `build_pipeline_core(pid)`. `lifecycle.py` → `LifecycleService` protocol with `NullLifecycle` (CLI/tests) + `ThreadedLifecycle` (web). `runstate.py` → `RunState`. `checkpoint.py` → `CheckpointStore` atomic JSON resume. `services.py` → stateless helpers (`state_snapshot`, `checkpoint_info`) used by web endpoints to avoid spinning a full `CinemaPipeline`. `phases/base.py` → `Phase` protocol + `PhaseResult`. `phases/{keyframe_render,motion_render,performance}.py` → the three Phase implementations. `pipeline.py` → generic Phase iterator with **zero current callers**. `shots/controller.py` → `ShotController` (the per-shot workhorse, ~1198 LOC). `review/controller.py` → `ReviewController`. |
| `audio/` | `_client.py`, `srt.py`, `music.py`, `effects.py`, `voiceover.py`, `dialogue.py`, `foley.py`, `alignment.py`. Pedalboard is a **hard dep** — `audio/effects.py` imports it unconditionally, no try/except guard. `audio/__init__.py` is a 23-line docstring with **no exports**; callers reach into submodules directly. |
| `llm/` | `ensemble.py` (LLMEnsemble — **Anthropic + OpenAI only**, no Gemini in dispatch), `chief_director.py` (validates shot prompts → `APPROVED` / `REJECTED` / `MODIFIED`), `style_director.py` (GPT-4o only), `prompt_optimizer.py` (per-shot prompt + `suggested_video_api`), `negative_prompts.py`. |
| `identity/` | `validator.py` (`IdentityValidator`) + `types.py`. Consumed via the **singleton factory** `phase_c_vision._get_shared_validator()` — never construct fresh validators. Note: `face_validator_gate.py` and `performance/identity_gate.py` each maintain their own independent ArcFace singleton with its own lock; three independent loads is intentional but worth knowing. |
| `performance/` | `_router.py` (`dispatch(engine, ...)` with per-provider semaphores: ACT_ONE=1, LIVE_PORTRAIT=2, VIGGLE=1), engine adapters `act_one.py` / `live_portrait.py` / `viggle.py`, `driving_video.py` (Mode B autopilot — Hedra/SadTalker cascade), `motion_gate.py` (Farneback 12×12 flow histogram → cosine similarity — **advisory only**), `identity_gate.py`, plus `_cache.py` / `_net.py` / `_poll.py` helpers. |
| `domain/` | Real domain modules: `project_manager.py` (filelock-protected JSON CRUD via `filelock.FileLock` on `project.lock`, default 10s timeout), `continuity_engine.py` (composes `CharacterContinuityTracker` + `LocationPersistence` + `PhysicsPromptEngineer` + `TemporalConsistencyManager`), `character_manager.py`, `location_manager.py`, `scene_decomposer.py`, `dialogue_writer.py`, `language_defaults.py` (per-language TTS/lipsync defaults for English / Korean / Japanese / Mandarin), `shot_types.py`, `performance.py` (engine routing helpers), `projects/` (per-project runtime storage, 12-hex IDs). Root-level `character_manager.py`, `continuity_engine.py`, `dialogue_writer.py`, `location_manager.py`, `project_manager.py`, `scene_decomposer.py` are ~400-byte `from domain.X import *` re-export shims. **Exception:** `pipeline_context.py` at root is NOT a shim — it loads `config/prompts/pipeline_context.md` into a `PIPELINE_CONTEXT` string consumed by LLM callers. |
| `config/` | `settings.py` → frozen `@dataclass(frozen=True) Settings` with env-derived API keys + paths ONLY. **Never** read project UI knobs from here. `prompts/` holds markdown context strings. |
| `data/` | Runtime data (SQLite cost-tracker DB, caches). Gitignored. |
| `prep/` | Operator-side prep CLIs: `lora_training.py`, `topaz_upscale.py`. |
| `docs/` | Older architecture docs. `HANDOFF.md` lives at the **repo root** (not under `docs/`). Older docs (`REFACTOR_HANDOFF.md`, `CINEMA_PIPELINE_MIGRATION_DESIGN.md`) describe pre-pivot or in-flight states — prefer this file. |
| `scripts/` | `calibrate_motion_floor.py`, `setup_runpod.sh`, `verify_llm_caching.py`. Each Python script self-bootstraps `sys.path` from repo root. |
| `tests/` | `tests/unit/` (pure logic) + `tests/integration/` (real APIs behind `@pytest.mark.e2e` + skipif on credentials; `tests/integration/test_cross_controller.py` is **misfiled** — it's a unit-style stub test, not an integration test). **Run pytest via `.venv/bin/python -m pytest`** (Python 3.13 venv required). |
| `web/` | Vite + React + TypeScript. No router — `App.tsx` uses `useState<'setup'\|'pipeline'\|'console'>` to switch shells. `web/src/components/console/*` is the Director's Console (warm-sepia `console-*` Tailwind classes). `web/src/components/pipeline/*` is the review-gate UI (cool-ivory `editorial-*` classes). Two palettes strictly separated in `tailwind.config.js:9-47`. Settings sections in `web/src/components/settings/*.tsx` (10 sections). SSE consumed via `hooks/useSSE.ts` → `hooks/usePipelineState.ts`. |
| (root) | `cinema_pipeline.py` (orchestrator), `web_server.py` (Flask/SSE, 61 routes), `phase_c_ffmpeg.py` (**the actual video router** — `generate_ai_video` dispatches to Kling/Sora/Veo/LTX/Runway/SEEDANCE — plus color grade + `two_pass_loudnorm` + stitch helpers), `phase_c_assembly.py` (image-only keyframe gen: `generate_ai_broll` + `RunPodComfyUI`), `phase_c_vision.py` (`_get_shared_validator()` singleton factory + DEPRECATED `validate_identity*` wrappers kept for backward compat), `workflow_selector.py` (5-template per-shot-type catalog + `MOTION_FIDELITY_FLOORS` + `classify_shot_type` keyword classifier), `quality_max.py` (max-tier image path: N=8 best-of, ArcFace+aesthetic halt, FreeU/SLG/DetailDaemon/SUPIR, 4K upscale), `lip_sync.py` (overlay cascade sync.so/MuseTalk/LatentSync + generation cascade Hedra/Kling/Omnihuman/Creatify), `face_validator_gate.py`, `cost_tracker.py`, `coherence_analyzer.py`, native API adapters `kling_native.py` / `sora_native.py` / `veo_native.py` / `ltx_native.py`. |

## Video routing — the actual cascade

- `workflow_selector.WORKFLOW_TEMPLATES` has **5 keys**: portrait / medium /
  wide / action / landscape. Each declares `target_api` + ordered
  `video_fallbacks`.
- **SEEDANCE appears only in the `action` cascade** (last fallback). It is
  NOT a general multi-character fallback. The cascade is keyword-driven
  via `classify_shot_type`, not character-count-driven. Two-character
  dialogue shots classify as `medium` and hit Kling → Runway → Sora →
  LTX — never SEEDANCE.
- When an operator pins `target_api` to a specific engine, `video_fallbacks`
  becomes `None` and `phase_c_ffmpeg.py`'s built-in default cascade
  applies: `["KLING_NATIVE","SORA_NATIVE","RUNWAY_GEN4","LTX","VEO_NATIVE","KLING_3_0","SORA_2","VEO","RUNWAY"]`.
- `_VEO_QUOTA_EXHAUSTED` is a sticky module-global in `phase_c_ffmpeg.py`
  — once VEO returns a 429, it short-circuits for the rest of the
  process lifetime. No reset.
- **Known small-bug catalog** (pre-existing, not session-fresh):
  - `workflow_selector.get_adaptive_pulid_weight` has no `return` —
    falls off the end, returns `None`. Callers expecting a float get None.
  - `MOTION_FIDELITY_FLOORS["macro"]` is a phantom — `macro` is not a
    shot type anywhere else. And no `close_up` entry despite being a
    real shot type.
  - `make_project()` defaults still seed `vbench_overall_threshold: 0.60`
    though VBench routing was excised in commit `cda5022`.
  - `domain/continuity_engine.py:415` and `domain/scene_decomposer.py:937`
    import via the root-shim path (`from project_manager import ...`)
    rather than the canonical `domain.project_manager` — works but
    inconsistent.
- **Known dead-code candidates** in `phase_c_ffmpeg.py` (no active callers):
  `generate_ass_subtitles`, `execute_master_ffmpeg_assembly`,
  `normalize_clip`, `probe_audio`. ~250 LOC total. All pre-pivot YouTube CLI.

## Phase protocol contract

Phase classes (in `cinema/phases/`) satisfy:

```python
class Phase(Protocol):
    name: str
    def run(self, ctx: PipelineContext) -> PhaseResult: ...
```

`PipelineContext` (in `cinema/context.py`) is a dataclass that *also*
implements the dict API (`__getitem__`, `__setitem__`, `get`, `update`,
`keys`, `items`, `values`, `as_dict`) — so legacy `def f(ctx: dict)`
functions keep working when passed a `PipelineContext`.

**Per-project UI settings** are populated by `cinema_pipeline.py` at
`PipelineContext(global_settings=project.get("global_settings", {}))`
construction. All consumers MUST use the helper:

```python
from cinema.context import get_project_setting
value = get_project_setting(ctx, "knob_name", default)
```

`config.settings.Settings` is for env-derived API keys ONLY. Reading
project-knob keys from it (the historical `getattr(settings, ...)`
pattern) is a silent-failure bug — it returns `None` and the default
always wins. This was fixed across 8 sites on 2026-05-23. **Known
remaining exception:** `audio/dialogue.py:143-149` takes a `settings: dict`
arg and reads with raw `.get` (works because callers pass
`project["global_settings"]` as a plain dict, but inconsistent with the
helper pattern).

## Invariants (verified by smoke test 2026-05-23)

1. All `.py` files compile cleanly on Python 3.13.
2. `import cinema_pipeline` succeeds without `TypeError`.
3. `LLMEnsemble()` instantiates.
4. `import identity.validator` does NOT pull `phase_c_vision` (lazy import
   via `identity/__init__.py:make_validator`).
5. `phase_c_vision._get_shared_validator()` returns the same instance
   across calls (singleton, no lock — fine for the single-orchestrator
   pipeline).
6. `PipelineContext(global_settings={"tts_provider": "CARTESIA_SONIC_2"})`
   + `get_project_setting(ctx, "tts_provider")` returns
   `"CARTESIA_SONIC_2"`.
7. `phase_c_assembly.generate_ai_broll` is importable.
8. `cinema/pipeline.py:CinemaPipeline` (the generic driver class) has
   zero callers in production code. The cinema_pipeline.py at repo root
   has its own `CinemaPipeline` class that does NOT inherit from nor
   use the generic driver.

Smoke block:

```bash
.venv/bin/python -c "
import cinema_pipeline
from cinema.context import PipelineContext, get_project_setting
from phase_c_vision import _get_shared_validator
from phase_c_assembly import generate_ai_broll
v1, v2 = _get_shared_validator(), _get_shared_validator()
assert v1 is v2
ctx = PipelineContext(global_settings={'tts_provider': 'CARTESIA_SONIC_2'})
assert get_project_setting(ctx, 'tts_provider') == 'CARTESIA_SONIC_2'
print('OK')
"
```

## When you change something

Beyond the GitNexus checks at the top of this file, the refactor-branch
workflow expects:

- One commit per logical slice. Identity-check (`a is b`) for every
  re-export. Run the §0 smoke block before declaring a slice done.
- Don't combine concerns. A bug fix isn't a refactor isn't a feature.
- See `docs/REFACTOR_HANDOFF.md` §6 for the canonical five-step slice
  playbook (read → write → re-export → verify with identity check →
  commit).
- For multi-task work (≥5 sub-tasks or ≥800 LOC of total change), don't
  implement everything in your current context — orchestrate via fresh
  contexts. See "Multi-task orchestration" below.

# Multi-task orchestration

When you encounter a written plan (e.g., `docs/superpowers/plans/*.md`)
with ≥5 sub-tasks, or you've drafted one with comparable scope, the
discipline that ships clean code here is to ORCHESTRATE, not implement
everything yourself.

The mechanism: each task is handed to a **fresh context** with a curated
prompt; the result comes back as a compact report; you review it; you move
on. Your main context grows linearly with the number of tasks, not with
the volume of work — which is what prevents quality degradation across
long (1M / 2M+ token) sessions.

**Claude Code:** see `CLAUDE.md` § "Working a Multi-Task Plan" for the
tool-specific implementation (Agent subagent dispatch, prompt templates,
`superpowers:subagent-driven-development` skill, TaskCreate tracking).
Everything below is the universal principle set.

## When to invoke

| Signal | Action |
|---|---|
| Written plan with 5+ mostly-independent sub-tasks | Orchestrate via fresh contexts |
| Single change OR tightly-coupled tasks | Stay in your current context |
| Interactive exploration ("how does X work?") | Stay in your current context |

## The per-task loop (sequential, never parallel)

For each task:

1. **Mark in_progress** in your task tracker.
2. **Dispatch an implementer to a fresh context.** Whatever your tool's
   mechanism is (Claude: `Agent` subagent; Cursor: new chat; Aider: new
   session; manual: co-developer with a written ticket). Give them a
   curated prompt — see "Prompt template" below.
3. **Read the implementer's report.** Don't trust it blindly; their
   self-review may be optimistic.
4. **Dispatch a spec compliance reviewer to a fresh context.** Their job:
   read the actual diff and compare to the spec line-by-line. They should
   verify by reading code, not by trusting the report.
5. If spec issues → fix loop (see "Delegation heuristics") → re-review.
6. **Dispatch a code quality reviewer to a fresh context.** Strengths,
   Issues (Critical / Important / Minor), Assessment. Pass the BASE_SHA
   and HEAD_SHA so they can scope the diff cleanly.
7. If quality issues → fix loop → re-review.
8. **Mark completed.** Move to next task.

After all tasks: run a final cross-cutting reviewer with the full
baseline-to-HEAD diff, then merge / open PR / hand off.

**Never dispatch multiple implementers in parallel** — they'd conflict on
files. Reviewers in parallel are fine but rarely necessary.

## Delegation heuristics — Lane A / B / C

Three lanes for each unit of work. Match the lane to the task — wrong-lane
choices either waste resources (Lane B for trivial fixes) or burn your
main context (Lane A for big work that should be delegated).

**Lane A — execute in your current context (manual edit / direct tool):**
- File is **already loaded in your context** AND change is ≤5 LOC
- Pure mechanical edit: rename, type alias, comment improvement, format fix
- A reviewer flagged a 1-2 line fix with clear instructions and you can see the surrounding code
- Test-data tweak (tighten a tolerance, swap a placeholder value)
- Final polish after a fresh implementer's commit you just reviewed

Cost: minimal. Risk: low — you can see what you're changing.

**Lane B — fresh implementer in an isolated context:**
- Change touches ≥3 files OR a domain you haven't read yet
- ≥5 LOC of structural change (new function, new component, new module)
- Design judgment needed (naming, abstraction, layout choice)
- Multi-step task that benefits from fresh-eyes context
- Anything where the implementer needs to discover state you don't yet have

Cost: full task context in the fresh instance. Risk: low if the prompt is
well-formed; high if it's "implement task X" with no context.

**Lane C — read-only survey (search / grep, no writes):**
- "Where is X defined?" / "Which files reference Y?" — open-ended search
- Codebase exploration before deciding how to dispatch Lane B
- Verifying a reviewer's claim before acting on it

Cost: read-only, scoped. Use when you need findings, not a code change.

**Decision tree:**
1. Is this a 1-5 line mechanical change in a file you already understand? → **Lane A**
2. Is this open-ended search across multiple files with no code change? → **Lane C**
3. Everything else → **Lane B**
4. Special case: if a reviewer's claim contradicts what you remember about
   upstream behavior, do a quick **Lane C survey** before fixing. The
   reviewer may be wrong.

## Prompt template (for Lane B implementers)

The fresh instance has no memory of your session. The prompt must let them
act **cold**. A good implementer prompt is 80-150 lines and includes:

```
You are implementing Task <ID> from `<plan path>` (Slice <S>, sub-slice <ID>).
Working dir: `<absolute>`. Branch: `<branch>`. Latest commit: `<sha>`.

## Task Description (verbatim from plan §X.Y)

<paste exact plan text — code blocks, tables, prose intact>

## Critical Context

- <what shipped before that this builds on>
- <what's coming after that depends on this>
- <any plan-vs-source divergences already discovered>

## Where Exactly

- File path: <absolute path>
- Insertion point: <line ~N> after <existing landmark>
- Surrounding pattern to match: <existing convention>

## Project conventions you MUST follow

Per `AGENTS.md` (or `CLAUDE.md` if you're Claude Code):
1. Run impact analysis before editing existing symbols (GitNexus or grep fallback)
2. Run scope check after edits — confirm only expected files changed
3. <task-specific gotcha>

## Verification

1. `<command>` — expected: <result>
2. `<command>` — expected: <result>

## Before You Begin

If you have questions about:
- <ambiguity 1>
- <ambiguity 2>

**Ask before implementing.**

## Your Job

1-7. <numbered steps>

## Report Format

- Status: DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT
- Impact findings (callers, risk) or grep-fallback equivalent
- Files changed (paths only)
- Verification command output
- Commit SHA
- Self-review findings
```

A **bad** implementer prompt is "implement task A1" — the fresh instance
burns context discovering things you already know, and the report comes
back vague.

For spec and code-quality reviewer prompts, see `CLAUDE.md` §§ "Spec
reviewer prompt template" and "Code quality reviewer prompt template" —
the structure transfers directly to non-Claude tools.

## Plan vs. source — the divergence rule

Plans sketch values that may be stale by execution time:
- Hex codes guessed before reading the actual mockup
- Function names not aligned with the file's naming convention
- Type fields that don't exist yet
- Library APIs the plan author assumed exist

**Standing instruction to every implementer:** "The plan's sketch is
approximate. Where the plan matches the actual source / mockup / type /
API, use the plan's value. Where they differ, use the actual value and
report the divergence in your status report."

This catches the plan being wrong without blocking on a re-spec.

## Commit discipline for reviewability

- **Baseline commit first.** If the working tree has uncommitted prep work
  foundational to the plan, commit it as `chore(baseline): ...` BEFORE
  dispatching any implementer. Otherwise each task's diff is polluted
  with prep noise.
- **One commit per task.** Don't amend across tasks. Reviewers need a
  clean BASE_SHA..HEAD_SHA range.
- **Fix commits are separate from feature commits.** When a reviewer
  finds an issue, the fix is its own commit on top — don't `--amend`.
  This preserves the audit trail.
- **Commit message convention:** `<type>(<scope>): <subject>` plus a
  short body explaining the *why* if non-obvious.

## Context hygiene (the long-session rule)

Quality degrades across very long contexts only if you let large bodies
of text accumulate. Mitigate by:

- **Don't read files >500 lines in your own context.** Dispatch a fresh
  instance with the specific question.
- **Don't re-read files you just edited.** Your tool should track state;
  if the edit succeeded, trust it.
- **Spot-check, don't re-verify.** If a reviewer says "spec compliant,"
  trust it. If something feels off, do a targeted single-file read or
  grep, not a full re-review.
- **Summaries in your main context, full content in fresh instances.**
  Each fresh instance digests 40-60k tokens of code and returns a
  500-2000 token summary. That's the ~20× compression you're paying for.

## Compaction signals and what to do

When your tool summarizes/truncates older messages (compaction), watch for:

- You start to forget file paths or commit SHAs you used earlier
- Reviewer prompts feel harder to assemble because you can't recall the
  implementer's exact claims
- A system message mentions summarization or truncation
- Token-count visibility (if shown) crosses ~70% of the context window

**Respond by:**
- **Commit pending work immediately.** Git is durable; chat is not.
- **Record open decisions in your task tracker.** Task descriptions
  persist across compactions.
- **Dispatch fresh instances earlier than you normally would** — even
  for borderline Lane-A work. The compact report survives compaction
  better than scattered conversation.
- **Don't re-read files to "refresh" your context.** You'll burn the
  remaining budget faster.
- **Surface state to the operator.** If you can't reliably complete the
  remaining work, say so and let them decide whether to continue or
  start a fresh session.

## Quality vs. throughput watchpoints

Moving fast through multi-task plans means some checks short-circuit.
Specific risk patterns to guard against:

| Watchpoint | What can slip through | Mitigation |
|---|---|---|
| **Concurrency in new code** | Missing locks around thread-shared state (SQLite, globals, `_*_lock` adjacent code) — spec review often misses these. | When the implementer touches thread-shared state, explicitly ask the code reviewer to check lock discipline. |
| **Public-API semantic changes** | Refactors that change prop/parameter names can be visually correct but semantically wrong. | For interface refactors, the spec reviewer must verify call-site mappings are semantically correct, not just that output matches. |
| **"Just X" with structural drift** | An implementer extends beyond a stated constraint (e.g., "only className strings" turns into local const extraction). | When an implementer deviates from a hard constraint, verify the deviation is purely additive and re-run touched tests. |
| **Plan-vs-convention naming conflicts** | A field labeled one way in plan, differently in production code. Following plan literally creates a contract mismatch. | When plan and project convention conflict, surface the choice to the operator rather than defaulting either way. |
| **Pre-existing failures masking new ones** | A flaky test failing throughout makes a new failure invisible. | Mark pre-existing failures `xfail` (or tighten tolerance) early in the branch so NEW failures stand out. |

**Pattern:** the throughput optimization is "ship when the code quality
reviewer says approve." The watchpoint is making sure the reviewer is
*checking the right things*. A reviewer prompt that doesn't mention
threading won't catch a missing lock — you have to tell them.

## Failure modes and false positives

Reviewers and tooling will sometimes be wrong. Recognizing the pattern
prevents acting on bad input.

**Reviewer false positives observed in practice:**

1. **"Missing requirement" claims that contradict upstream behavior** —
   The reviewer didn't trace upstream semantics (e.g., flagged "buffer
   not capped" when the buffer is bounded at its source). **Mitigation:**
   when a "missing requirement" claim contradicts the dispatch prompt's
   stated upstream behavior, verify with a targeted grep before fixing.

2. **Sequencing concerns based on nominal task order** — Reviewer assumed
   the plan's nominal task order; your actual dispatch order may already
   satisfy the concern. **Mitigation:** check your task tracker before
   re-arranging work.

3. **"Function X not found in module Y"** — Reviewer grepped the wrong
   file. The function lived in a sibling module. **Mitigation:** if a
   reviewer says "not found," double-check the scope you provided in
   their prompt. The answer is often one file over.

4. **Security warnings on instruction-following actions** — Automated
   scanners can flag compliant behavior (e.g., the operator/system
   prompt explicitly asks for behavior the scanner doesn't recognize).
   **Mitigation:** if your action is clearly compliant with explicit
   operator/system instructions, proceed and note the false positive.

5. **Fresh instance "tool X not available"** — Fresh instances may have
   a different tool environment than you do (different MCP servers,
   different env vars, etc.). **Mitigation:** don't require fresh
   instances to use tools you have; provide fallback instructions
   (grep + file reading instead of MCP impact analysis) in their prompt.

**Tool/environment failure modes:**

6. **Edit tools that require Read first** — Many tools (including
   Claude Code's `Edit`) require a `Read` on a file before edits.
   **Mitigation:** always read (even a small window) before the first
   edit on a file.

7. **Wrong Python interpreter** — System `python3` may lack project
   test deps; the project's venv has them. **Mitigation:** use the
   project's binary explicitly: `.venv/bin/python -m pytest ...`.

8. **Background-task completion notifications** — Async notifications
   may appear in your conversation but are NOT operator input.
   **Mitigation:** treat them as informational; don't confuse them with
   operator acknowledgement of a pending question.

**Detection pattern:** when a tool/reviewer/warning contradicts what you
already know to be true, do a quick targeted verification (single read,
single grep) before acting on the claim. A 5-second check prevents a
wrong fix that itself needs reverting.

## When NOT to orchestrate

- **Single-step tasks.** Just do them.
- **Tightly-coupled refactors** where each change depends on the
  previous change's state in a way that prep-then-dispatch can't
  capture cleanly.
- **Interactive exploration** ("what does X do?"). Fresh-instance
  overhead hurts here.
- **Tasks needing constant operator feedback** — interactive sessions
  fit better.

# Coordinating with CLAUDE.md

This file (`AGENTS.md`) and `CLAUDE.md` are sibling documents. They share
the GitNexus block (auto-managed) and the Architecture Preamble. They
diverge on tooling specifics:

| Topic | This file (AGENTS.md) | CLAUDE.md |
|---|---|---|
| GitNexus rules | ✓ (canonical) | ✓ (canonical, identical) |
| Architecture + invariants | ✓ (canonical) | ✓ (canonical, identical) |
| Multi-task discipline | ✓ Universal principles | ✓ Same principles + Claude tool syntax |
| Lane A/B/C heuristic | ✓ Universal | ✓ Same |
| Prompt templates | ✓ Universal skeleton | ✓ Same + Claude-specific examples |
| Tool syntax (`Agent`, `Skill`, `TaskCreate`) | — | ✓ Claude Code only |
| `superpowers:*` skill invocation | — | ✓ Claude Code only |
| `AskUserQuestion` discipline | — | ✓ Claude Code only |

**If a Claude Code agent reads both files** and the guidance differs, the
order of precedence is:
1. The operator's explicit instructions (highest)
2. `CLAUDE.md` Claude-specific extensions
3. This file's universal principles
4. The model's default behavior (lowest)

**If a non-Claude agent reads only this file:** the universal principles
above are complete and standalone. Apply them with your tool's analogous
mechanisms. The `CLAUDE.md` references are optional reading.
