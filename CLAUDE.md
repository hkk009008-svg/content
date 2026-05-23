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

# Session-start protocol (read me first)

**This file, `AGENTS.md`, `HANDOFF.md`, and the user's MEMORY.md drift
from the actual code between sessions.** A few claims were wrong when
written; more become wrong as commits land. Before doing any non-trivial
work, verify the claims in this doc against the current source. If a
claim is stale, **fix this file in the same change** that exposes the
staleness — don't let a wrong claim survive your session.

Concrete protocol at session start (≤2 minutes):

1. Run the smoke block from the "Invariants" section below. If it
   fails, the doc is stale OR the working tree is broken — fix one or
   the other before proceeding with the user's task.
2. Spot-check "Single entry point" and "Top-level package layout":
   - `ls cinema/ cinema/phases/ cinema/review/ cinema/shots/`
   - `grep -n "^from cinema.phases" cinema_pipeline.py`
   - `wc -l cinema_pipeline.py web_server.py phase_c_ffmpeg.py`
   Compare each against the table.
3. `git log --oneline -20` — if any commit touched a module mentioned
   in this doc since it was last edited, re-read that section against
   the new code.
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

> `HANDOFF.md` at the repo root is the session-journal companion to this
> file. When this Architecture Preamble and HANDOFF disagree, **this
> file wins** — HANDOFF is journal-shaped (what changed last session),
> this file is current-state-shaped (what's true now).

## Single entry point

- **`web_server.py`** (Flask + SSE, ~1647 LOC, no auth, wide-open CORS)
  → **`cinema_pipeline.py:CinemaPipeline`** (~1004 LOC) — interactive
  dashboard with pause/resume + SSE progress + four operator review
  gates: **PLAN_REVIEW**, **KEYFRAME_REVIEW**, **PERFORMANCE_REVIEW**
  (auto-skipped if all shots routed to SKIP), **REVIEW**.
- The three Phase classes (`KeyframeRenderPhase`, `PerformanceCapturePhase`,
  `MotionRenderPhase`) **live under `cinema/phases/`**, not inline.
  `cinema_pipeline.py:25-27` imports them; the orchestrator calls
  `phase.run(ctx)` directly. It does NOT use the `cinema.pipeline`
  generic driver — that driver class exists at `cinema/pipeline.py`
  but has **zero callers** today (preserved as a primitive).
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
| `audio/` | `_client.py`, `srt.py`, `music.py`, `effects.py`, `voiceover.py`, `dialogue.py`, `foley.py`, `alignment.py`. Pedalboard is a **hard dep** — `audio/effects.py` imports it unconditionally with no try/except guard. `audio/__init__.py` is a 23-line docstring with **no exports**; callers reach into submodules directly. |
| `llm/` | `ensemble.py` (LLMEnsemble — **Anthropic + OpenAI only**, no Gemini in dispatch), `chief_director.py` (validates shot prompts → `APPROVED` / `REJECTED` / `MODIFIED`), `style_director.py` (GPT-4o only), `prompt_optimizer.py` (per-shot prompt + `suggested_video_api`), `negative_prompts.py`. |
| `identity/` | `validator.py` (`IdentityValidator`) + `types.py`. Canonical singleton factory is `identity.get_shared_validator()` — `phase_c_vision._get_shared_validator()` is kept as a backward-compat alias and delegates to the same factory. `face_validator_gate.py` and `performance/identity_gate.py` also delegate, so all four access paths return the same instance: ArcFace weights load once per process and rolling-stats history accumulates signal from per-shot validations + N=8 best-of grading + performance-gate scoring (commit cc34870). |
| `performance/` | `_router.py` (`dispatch(engine, ...)` with per-provider semaphores: ACT_ONE=1, LIVE_PORTRAIT=2, VIGGLE=1), engine adapters `act_one.py` / `live_portrait.py` / `viggle.py`, `driving_video.py` (Mode B autopilot — Hedra/SadTalker cascade), `motion_gate.py` (Farneback 12×12 flow histogram → cosine similarity — **advisory only**), `identity_gate.py`, plus `_cache.py`/`_net.py`/`_poll.py` helpers. |
| `domain/` | The real domain modules: `project_manager.py` (filelock-protected JSON CRUD via `filelock.FileLock` on `project.lock`, default 10s timeout), `continuity_engine.py` (composes `CharacterContinuityTracker` + `LocationPersistence` + `PhysicsPromptEngineer` + `TemporalConsistencyManager`), `character_manager.py`, `location_manager.py`, `scene_decomposer.py`, `dialogue_writer.py`, `language_defaults.py` (per-language TTS/lipsync defaults for English / Korean / Japanese / Mandarin), `shot_types.py`, `performance.py` (engine routing helpers), `projects/` (per-project runtime storage, 12-hex IDs). Root-level files (`character_manager.py`, `continuity_engine.py`, `dialogue_writer.py`, `location_manager.py`, `project_manager.py`, `scene_decomposer.py`) are ~400-byte `from domain.X import *` re-export shims. **Exception:** `pipeline_context.py` at root is NOT a shim — it loads `config/prompts/pipeline_context.md` into a `PIPELINE_CONTEXT` string consumed by LLM callers. |
| `config/` | `settings.py` → frozen `@dataclass(frozen=True) Settings` with env-derived API keys + paths ONLY. **Never** read project UI knobs from here. `prompts/` holds markdown context strings. |
| `data/` | Runtime data (SQLite cost-tracker DB, caches). Gitignored. |
| `prep/` | Operator-side prep CLIs: `lora_training.py`, `topaz_upscale.py`. |
| `docs/` | Older architecture docs. `HANDOFF.md` lives at the **repo root** (not under `docs/`). Older docs (`REFACTOR_HANDOFF.md`, `CINEMA_PIPELINE_MIGRATION_DESIGN.md`) describe pre-pivot or in-flight states — prefer this file. |
| `scripts/` | `calibrate_motion_floor.py`, `setup_runpod.sh`, `verify_llm_caching.py`. Each Python script self-bootstraps `sys.path` from repo root. |
| `tests/` | `tests/unit/` (pure logic, stub hosts) + `tests/integration/` (real APIs behind `@pytest.mark.e2e` + skipif on credentials). **Run pytest via `.venv/bin/python -m pytest`** (Python 3.13 venv required). |
| `web/` | Vite + React + TypeScript. No router — `App.tsx` uses `useState<'setup'\|'pipeline'\|'console'>` to switch shells. `web/src/components/console/*` is the Director's Console (warm-sepia `console-*` Tailwind classes). `web/src/components/pipeline/*` is the review-gate UI (cool-ivory `editorial-*` classes). Two palettes strictly separated in `tailwind.config.js:9-47`. Settings sections in `web/src/components/settings/*.tsx` (10 sections). SSE consumed via `hooks/useSSE.ts` → `hooks/usePipelineState.ts`. |
| (root) | `cinema_pipeline.py` (orchestrator), `web_server.py` (Flask/SSE, 59 routes), `phase_c_ffmpeg.py` (**the actual video router** — `generate_ai_video` dispatches to Kling/Sora/Veo/LTX/Runway/SEEDANCE — plus color grade + `two_pass_loudnorm` + stitch helpers), `phase_c_assembly.py` (image-only keyframe gen: `generate_ai_broll` + `RunPodComfyUI`), `phase_c_vision.py` (`_get_shared_validator()` singleton factory + DEPRECATED `validate_identity*` wrappers kept for backward compat), `workflow_selector.py` (5-template per-shot-type catalog + `MOTION_FIDELITY_FLOORS` + the `classify_shot_type` keyword classifier), `quality_max.py` (max-tier image path: N=8 best-of, ArcFace+aesthetic halt, FreeU/SLG/DetailDaemon/SUPIR, 4K upscale), `lip_sync.py` (overlay cascade sync.so/MuseTalk/LatentSync + generation cascade Hedra/Kling/Omnihuman/Creatify), `face_validator_gate.py`, `cost_tracker.py`, `coherence_analyzer.py`, native API adapters `kling_native.py` / `sora_native.py` / `veo_native.py` / `ltx_native.py`. |

## Video routing — the actual cascade

- `workflow_selector.WORKFLOW_TEMPLATES` has **5 keys**: portrait / medium /
  wide / action / landscape. Each declares `target_api` + ordered
  `video_fallbacks`.
- **SEEDANCE appears only in the `action` cascade** (last fallback). It is
  NOT a general multi-character fallback. The cascade is **keyword-driven**
  via `classify_shot_type`, not character-count-driven. A two-character
  dialogue shot classifies as `medium` and hits Kling → Runway → Sora →
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
    shot type anywhere else (not in `domain/shot_types.py`, not returned
    by `classify_shot_type`). And no `close_up` entry despite being a real
    shot type.
  - `make_project()` defaults still seed `vbench_overall_threshold: 0.60`
    though VBench routing was excised in commit `cda5022`.
  - `domain/continuity_engine.py:415` and `domain/scene_decomposer.py:937`
    import via the root-shim path (`from project_manager import ...`)
    rather than the canonical `domain.project_manager` — works but
    inconsistent with the rest of `domain/`.
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
always wins. This was fixed across 8 sites on 2026-05-23 and the last
holdout (`audio/dialogue.py`'s `settings: dict` parameter) was migrated
to `ctx: PipelineContext` in commit cc34870's follow-up — every
per-project knob read in `audio/`, `llm/`, `performance/`, `cinema/`,
and `quality_max.py` now flows through `get_project_setting(ctx, ...)`.

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
   `"CARTESIA_SONIC_2"` (settings plumbing works).
7. `phase_c_assembly.generate_ai_broll` is importable (used by
   `cinema/shots/controller.py` + `quality_max.py`).
8. `cinema/pipeline.py:CinemaPipeline` (the generic driver class) has
   zero callers in production code. The cinema_pipeline.py at repo
   root has its own `CinemaPipeline` class that does NOT inherit from
   nor use the generic driver.

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

Beyond the GitNexus checks above, the refactor-branch workflow expects:

- One commit per logical slice. Identity-check (`a is b`) for every
  re-export. Run the §0 smoke block before declaring a slice done.
- Don't combine concerns. A bug fix isn't a refactor isn't a feature.
- See REFACTOR_HANDOFF.md §6 for the canonical five-step slice playbook
  (read → write → re-export → verify with identity check → commit).
- **For work beyond a single slice (≥5 sub-tasks or ≥800 LOC of total
  change), don't implement in main context — orchestrate. See
  "Working a Multi-Task Plan" below.**

# Working a Multi-Task Plan

When the user points you at a written plan (e.g., `docs/superpowers/plans/*.md`)
with ≥5 sub-tasks, or you've drafted one yourself with comparable scope, you
ORCHESTRATE — you do not implement directly. Main context holds the plan,
TaskCreate state, and ~1-3k of summary per task; fresh subagents do the
reading, writing, and verification.

This is the mechanism that prevents quality degradation across long
(1M / 2M+ token) sessions: each subagent starts at ~0 tokens with a curated
self-contained prompt, returns a compact report, and disappears. Main context
grows linearly with the number of tasks, not with the volume of work.

## When to invoke

| Signal | Action |
|---|---|
| User references a plan file under `docs/superpowers/plans/` | Invoke `superpowers:subagent-driven-development` skill (subagents available here) |
| Plan has 5+ sub-tasks AND tasks are mostly independent | Same |
| Task is a single change OR tasks are tightly coupled | Stay in main context; the orchestration overhead isn't worth it |
| User is in an interactive exploration ("how does X work?") | Stay in main context; subagents hurt latency for Q&A |

## The per-task loop (sequential, never parallel)

For each task in the plan:

1. `TaskUpdate({taskId: N, status: "in_progress"})`
2. **Dispatch implementer** — `Agent({ subagent_type: "general-purpose", model: "sonnet", prompt: <curated, see template below> })`
3. Read the report. If status is `DONE_WITH_CONCERNS` / `BLOCKED` / `NEEDS_CONTEXT`, address the concern before reviewing.
4. **Dispatch spec compliance reviewer** — same subagent type. Reviewer reads the actual diff and compares to the spec line-by-line. Do NOT trust the implementer's self-report.
5. If spec issues → fix loop (see "Delegation heuristics" below) → re-review.
6. **Dispatch code quality reviewer** — `subagent_type: "superpowers:code-reviewer"`. Pass BASE_SHA, HEAD_SHA, what was implemented, plan reference.
7. If quality issues → fix loop → re-review.
8. `TaskUpdate({taskId: N, status: "completed"})` and move on.

After all tasks: dispatch a final cross-cutting reviewer with BASE_SHA = the
baseline commit and HEAD_SHA = current HEAD. Then invoke
`superpowers:finishing-a-development-branch`.

**Never dispatch multiple implementers in parallel** — they'd conflict on
files. Reviewers in parallel are fine but rarely needed.

## Delegation heuristics — Lane A / B / C

Three lanes for each unit of work. Match the lane to the task — wrong-lane
choices either waste tokens (lane B for trivial fixes) or burn main context
(lane A for big work that should have been delegated).

**Lane A — execute in main context (Edit / Bash directly):**
- File is **already in your context** AND change is ≤5 LOC
- Pure mechanical edit: rename, type alias, comment improvement, format fix
- A reviewer flagged a 1-2 line fix with clear instructions and you can see the surrounding code
- Test-data tweak (tighten a tolerance, swap a placeholder value)
- Final polish after a fresh subagent's commit you just reviewed

Costs: ~few hundred tokens. Risk: low — you can see what you're changing.

**Lane B — fresh implementer subagent:**
- Change touches ≥3 files OR a domain you haven't read yet
- ≥5 LOC of structural change (new function, new component, new module)
- Design judgment needed (naming, abstraction, layout choice)
- Multi-step task that benefits from fresh-eyes context
- Anything where the implementer needs to discover state you don't yet have

Costs: ~40-60k tokens in the subagent's context, ~1-3k in yours.
Risk: low if the prompt is well-formed; high if it's "implement task X" with no context.

**Lane C — Explore / grep subagent (read-only survey):**
- "Where is X defined?" / "Which files reference Y?" — open-ended search
- Codebase exploration before deciding how to dispatch lane B
- Verifying a reviewer claim before acting on it

Costs: ~10-30k tokens. No write actions. Use when you need findings, not a code change.

**Decision tree:**
1. Is this a 1-5 line mechanical change in a file you already understand? → **Lane A**
2. Is this open-ended search across multiple files with no code change? → **Lane C**
3. Everything else → **Lane B**
4. Special case: if a reviewer's claim contradicts what you remember about upstream behavior, do a quick **Lane C survey** (or single targeted `grep`/`Read`) before fixing. The reviewer may be wrong.

## Implementer prompt template

A good implementer prompt is 80-150 lines and lets the subagent act
**cold** — they have no memory of this session. Skeleton:

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

Per `/Users/.../CLAUDE.md`:
1. Run `gitnexus_impact({target: "<symbol>", direction: "upstream"})` before editing existing symbols
2. Run `gitnexus_detect_changes()` after edits — confirm scope is what you expect
3. <task-specific gotcha>
4. If GitNexus MCP isn't reachable in your environment, fall back to grep + file inspection.

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

## When You're in Over Your Head

If <X happens>, report BLOCKED with what you tried.

## Report Format

- Status: DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT
- gitnexus_impact findings (callers, risk) or grep-fallback equivalent
- Files changed (paths only)
- Verification command output
- Commit SHA
- Self-review findings
```

A **bad** implementer prompt is "implement task A1" — they'll burn context
discovering everything you already know, and the report will be vague.

## Spec reviewer prompt template

```
You are reviewing whether Task <N>'s implementation matches its spec.
**Do NOT trust the implementer's report** — read the actual code.

## What Was Requested

<paste exact requirements + numbered checklist of behaviors>

## What Implementer Claims

<list claims to be verified, including commit SHA>

## Your Job

1. `git show <SHA> -- <file>` — read the diff
2. Verify each requirement above
3. Look for: missing requirements, extra unrequested features, misunderstandings
4. <task-specific verification commands>

## Report

- ✅ Spec compliant
- ❌ Issues — list with file:line refs

Under <N> words.
```

## Code quality reviewer prompt template

```
Code quality review for Task <N> (commit `<SHA>`).

**WHAT_WAS_IMPLEMENTED:** <one-paragraph summary>
**PLAN_OR_REQUIREMENTS:** <reference to plan section>
**BASE_SHA:** `<sha>`
**HEAD_SHA:** `<sha>`
**DESCRIPTION:** <one-paragraph context>

**Working directory:** `<absolute>`
**Diff command:** `git diff <BASE>..<HEAD> -- <files>`

In addition to standard concerns, check:
- <task-specific concern 1> (e.g., concurrency if threading is involved)
- <task-specific concern 2> (e.g., public API stability if refactor)

Report: Strengths, Issues (Critical / Important / Minor), Assessment.
Under <N> words.
```

## Plan vs. source — the divergence rule

Plans sketch values that may be stale by execution time:
- Hex codes guessed before reading the actual mockup
- Function names not aligned with the file's naming convention
  (e.g., plan said `motion_floor_for`; file convention is `get_*` prefix)
- Type fields that don't exist yet
- Library APIs the plan author assumed exist

**Standing instruction to every implementer:** "The plan's sketch is
approximate. Where the plan matches the actual source / mockup / type / API,
use the plan's value. Where they differ, use the actual value and report
the divergence in your status report."

This is how to catch the plan being wrong without blocking on a re-spec.

## Commit discipline for reviewability

- **Baseline commit first.** If the working tree has uncommitted prep work
  foundational to the plan (new files, modified types, prep methods),
  commit it as `chore(baseline): ...` BEFORE dispatching any implementer.
  Otherwise each task's diff is polluted with prep noise.
- **One commit per task.** Don't amend across tasks. Reviewers need a clean
  BASE_SHA..HEAD_SHA range.
- **Fix commits are separate from feature commits.** When a reviewer finds
  an issue, the fix is its own commit on top — don't `--amend`. This
  preserves the audit trail showing what the reviewer caught.
- **Commit message convention:** `<type>(<scope>): <subject>` plus a
  short body explaining the *why* if non-obvious. End with the
  `Co-Authored-By: Claude Opus 4.7 (1M context)` trailer that Claude Code
  injects by default.

## Context hygiene (the long-session rule)

Quality degrades across very long contexts only if you let large bodies of
text accumulate. Mitigate by:

- **Don't `Read` files >500 lines in main context.** Dispatch a subagent
  with the specific question.
- **Don't re-`Read` files you just edited.** `Edit`/`Write` would have
  errored if the change failed. The harness tracks state.
- **Spot-check, don't re-verify.** If a reviewer says "spec compliant,"
  trust it. If something feels off, do a targeted single-file `Read` or
  `grep`, not a full re-review.
- **Summaries in main, full content in subagents.** Each subagent
  digests 40-60k tokens of code and returns a 500-2000 token summary.
  That's the ~20× compression you're paying for.

## Compaction signals and what to do

The harness may compact (summarize) older messages when context gets
long. A well-orchestrated session won't trigger this — main context stays
linear in task count, not in work volume — but be ready.

**Signals you're approaching compaction:**
- You start to forget specific file paths or commit SHAs from earlier
  in the session
- Reviewer prompts feel harder to assemble because you can't recall the
  implementer's exact claims
- A `<system-reminder>` mentions summarization, truncation, or compaction
- Token-count visibility (if shown) crosses ~70% of the model's window

**What to do when sensed:**
- **Commit pending work immediately.** Git is durable; chat is not. If
  you've been holding a multi-file change in conversation, commit it.
- **Record open decisions in TaskCreate.** Task descriptions persist
  across compactions. Move "still to decide: X vs Y" into a task body.
- **Dispatch a fresh subagent earlier than you normally would** — even
  for borderline lane-A work. The subagent's compact report will survive
  compaction better than scattered conversation text.
- **Don't re-`Read` files to "refresh" your context.** You'll burn the
  remaining budget faster. Trust git, TaskCreate, and the harness's
  state tracking.
- **Surface state to the user.** If you can't reliably complete the
  remaining work, say so and let them decide whether to continue or
  open a fresh session.

## AskUserQuestion discipline

Use `AskUserQuestion` for choices that:
- Are cross-cutting (affect multiple tasks)
- Set policy (e.g., advisory vs. auto-fail for a quality gate)
- Are reversible only with effort (renaming a public API, picking a license)

Don't ask for: which file a helper goes in, whether to use `const` or
`function`, naming choices that the file's existing convention answers.
Auto Mode says: make the reasonable call and keep going.

## Background work

`run_in_background: true` is for:
- `npx gitnexus analyze --embeddings` after a batch of commits — index will
  be ready before the next slice needs it.
- Long verification (`pytest -v` on a large suite, `vite build`, `gh pr create`
  on a slow network).
- Anything where you have independent work to do meanwhile.

**Don't** poll a background task you started — the harness notifies on
completion automatically. Just continue with other work.

## Pre-existing failures

If a test fails on the baseline (not introduced by this branch), don't fix
it inside a slice — it's scope creep. Track it explicitly in conversation.
Surface it to the operator at `superpowers:finishing-a-development-branch`
time so they decide: tighten tolerance, mark `xfail`, or ship as-is.

**But:** mark it `xfail` (or tighten tolerance) early in the branch if
possible, so a NEW failure stands out cleanly against a green-otherwise
suite. A red baseline masks new red.

## Quality vs. throughput watchpoints

Moving fast through multi-task plans means some checks get short-circuited.
Specific risk patterns to guard against:

| Watchpoint | What can slip through | Mitigation |
|---|---|---|
| **Concurrency in new code** | A `_running_cores.get()` without `_cores_lock` slipped past spec review; only the code-quality reviewer caught it. SQLite + threading is the common source. | When the implementer touches anything thread-shared (`_*_lock` adjacent, SQLite connections, global state), explicitly ask the code reviewer to look for lock discipline. |
| **Public-API semantic changes** | A refactor's prop/parameter names didn't match the data being passed; call-site labels happened to align by accident. | For refactors that change a public interface, the spec reviewer must verify call-site mappings are semantically correct, not just that visual/behavioral output matches. |
| **"Just className changes" with structural drift** | An implementer extracted local consts inside a constraint that said "only className strings." Semantically identical, but a deviation from the hard constraint. | When an implementer deviates from a hard constraint, verify the deviation is purely additive and re-run any tests touching that code. |
| **Plan-vs-convention naming conflicts** | A field labeled `engine` in plan was `target_api` in production code. Following plan literally creates a contract mismatch. | When plan and project convention conflict, surface the choice via `AskUserQuestion` rather than defaulting either way. |
| **Pre-existing failures masking new ones** | A flaky test was failing throughout the implementation; a new bug causing the same failure mode would have been invisible. | Mark pre-existing failures `xfail` (or tighten tolerance) early in the branch — see "Pre-existing failures" above. |

**Pattern:** the throughput optimization is "ship when the code quality
reviewer says approve." The watchpoint is making sure the reviewer is
*checking the right things*. A reviewer prompt that doesn't mention
threading won't catch a missing lock — you have to tell them.

## Failure modes and false positives observed

Reviewers and tooling will sometimes be wrong. Recognizing the pattern
prevents acting on bad input.

### Reviewer false positives

1. **"Buffer not capped / not newest-on-top" in a downstream consumer** —
   Spec reviewer flagged two missing requirements in a render component.
   Both were actually enforced upstream in the source hook
   (`setBuffer(prev => [event, ...prev].slice(0, 20))` — bounded AND
   prepended at the source). The reviewer didn't trace upstream
   semantics. **Mitigation:** when a "missing requirement" claim
   contradicts the dispatch prompt's stated upstream behavior, verify
   with a targeted `grep` before fixing.

2. **"Tests must land before X ships" — sequencing concern** — Reviewer
   assumed the plan's nominal task order; the actual dispatch order
   already satisfied the concern. **Mitigation:** reviewers don't know
   your dispatch sequence. Their sequencing concerns may be pre-satisfied.
   Read the concern, check `TaskList`, decide.

3. **"Function X not found in module Y"** — Final cross-cutting reviewer
   grepped the wrong file. The function lived in a sibling module.
   **Mitigation:** if a reviewer says "not found," double-check the
   scope you provided in their prompt. The answer is often one file over.

4. **Security-warning "fabricated model identity"** — Harness flagged the
   `Co-Authored-By:` trailer that the system prompt explicitly instructs
   you to add. **Mitigation:** automated security warnings can be wrong
   about instruction-following. If your action is clearly compliant with
   explicit user/system instructions, proceed and note the false
   positive in your response.

5. **"GitNexus MCP not available" from a subagent** — Subagents have a
   different MCP environment than the orchestrator. Several subagents
   couldn't reach GitNexus and fell back to grep + file inspection.
   **Mitigation:** don't require subagents to use GitNexus tools; tell
   them in the prompt that grep + file reading is an acceptable fallback
   for impact analysis when MCP isn't reachable.

### Tool and environment failure modes

6. **`Edit` requires `Read` first** — Trying to `Edit` a file the harness
   hasn't seen returns `File has not been read yet`. **Mitigation:**
   always `Read` (even a small offset+limit window) before the first
   `Edit` on a file in a session.

7. **System `python3` vs project `.venv/bin/python`** — Default `python3`
   doesn't have project test deps (pytest, etc.); the project venv does.
   **Mitigation:** for project-specific tooling (pytest, vite, npx,
   anything not in the standard library), use the project's binary
   explicitly: `.venv/bin/python -m pytest ...`, `npx ...` from the
   right directory.

8. **Background-task completion notifications mid-conversation** — The
   harness fires `<system-reminder>` blocks when a background command
   finishes. These are NOT user input. **Mitigation:** treat them as
   informational; don't confuse them with user acknowledgement of a
   pending question.

### Detection pattern

The common thread: **when a tool/reviewer/warning contradicts what you
already know to be true, do a quick targeted verification (single
`Read`, single `grep`) before acting on the claim.** A 5-second check
prevents a wrong fix that itself needs to be reverted.

## When NOT to use this pattern

- **Single-step tasks.** Just do them in main context.
- **Tightly-coupled refactors** where every change depends on the previous
  change's state in a way that prep-then-dispatch can't capture cleanly.
- **Interactive exploration** ("what does X do?"). Subagent overhead hurts
  here.
- **Tasks with constant operator feedback** — interactive sessions in main
  context fit better.
