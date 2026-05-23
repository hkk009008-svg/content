# Cinema Pipeline — Architecture Refactor Handoff (Round 2)

> **⚠️ PRE-PIVOT DOC — read with skepticism (updated 2026-05-23).**
>
> This document was written when the repo had TWO entry points
> (`main.py` CLI + `web_server.py` interactive). On 2026-05-23 the CLI
> was deleted entirely (YouTube generator legacy). The phase-wrappers in
> `cinema/phases/{blueprint,generation,audio,assembly,vision}.py` were
> CLI-only and are also gone. `phase_a_generator.py`, `llm/blueprint_director.py`,
> `vbench_evaluator.py`, `comfyui_workflow_gen.py`, `phase_c_assembly.assemble_final_video`,
> and all related files were removed.
>
> **Canonical current state lives in `/ARCHITECTURE.md` at repo root** (the
> prior `HANDOFF.md` pointer was archived to `docs/archive/` on 2026-05-24
> when ARCHITECTURE.md superseded the journal-shaped handoff). The
> "Slice X" / "Phase 6" / "two orchestrators" framing in this doc is
> historical context — useful to understand the refactor that produced
> the cinema pipeline, NOT the current state. The invariants below
> (re-export identity checks, phase_b_audio shims) are no longer
> meaningful — the audio refactor finished, the CLI is gone, and
> `phase_b_audio` is no longer a thing.
>
> Sections still useful: the five-step slice playbook (§6), the
> testing discipline (§7-8), the historical lessons. Skip §0-5 setup
> instructions — venv has been recreated on Python 3.13 with a
> direct-deps `requirements.txt`.

---

**Status:** V1.1 design-critique follow-up complete, 54 commits deep on branch `refactor/architecture-cleanup`.
**As of:** end of V1.1 (this commit). V1 architectural completion + V1.1 design-critique-derived improvements shipped.
**Last completed:** V1.1 final -- design-critique recommendations executed end-to-end. Shared `RunState` dataclass unifies all 9 run-state fields; host protocols are `@runtime_checkable`; CinemaPipeline delegate section is auto-generated via `tools/gen_delegates.py` (idempotent + --check mode); `tests/integration/test_cross_controller.py` formalizes the Lesson 8.17 behavioral-test template (catches the Slice-2 silent-regression class). Lessons renumbered to chronological order.
**Author of this doc:** previous chat session, end-of-day handoff.
**Supersedes:** the original handoff (which covered through Phase 6 slice 3). The original is preserved in git history at the parent of `92a0bba`.

This document is the operating manual for continuing the refactor. It is
**not** a summary — it's structured so the next chat can resume work at
max capacity without re-deriving context from commit history.

> **Most important sentence in this doc:** every refactor slice follows
> the same five-step playbook (read -> write -> re-export -> verify with
> identity check -> commit). The playbook is at section 6. Read it first.

---

## 0. Setup quickstart for the next chat

```bash
cd /Users/hyungkoookkim/Content
git status                          # untracked: projects/70940580b872/, .venv-py39-backup if upgrade in progress
git log --oneline -10               # HEAD should be 6f85c38 (handoff doc) or 42a290f (PipelineCore)
git branch --show-current           # should be refactor/architecture-cleanup
git tag -l | grep refactor          # should list pre-refactor-baseline
```

Sanity smoke (must pass cleanly):

```bash
PY=/Users/hyungkoookkim/Content/.venv/bin/python
cd /Users/hyungkoookkim/Content && $PY -c "
import sys; sys.path.insert(0, '.')

# 1. Compile-check everything in the project tree
import py_compile, pathlib
ok = failed = 0
for py in pathlib.Path('.').rglob('*.py'):
    rel = str(py)
    if any(d in rel for d in ('.venv', '.claude', '__pycache__', '.gitnexus', '.serena', 'web/node_modules')): continue
    try: py_compile.compile(str(py), doraise=True); ok += 1
    except py_compile.PyCompileError as e: failed += 1; print(f'FAIL {rel}: {e}')
print(f'COMPILE: {ok} ok, {failed} failed')

# 2. Phase 3 invariant: identity.validator does NOT pull phase_c_vision
before = set(sys.modules.keys())
import identity.validator
new = set(sys.modules.keys()) - before
assert not any('phase_c_vision' in m for m in new), 'identity cycle re-introduced'
print('OK identity cycle break')

# 3. Phase 4 invariant: LLMEnsemble shadow-bug fix
from llm import LLMEnsemble; LLMEnsemble()
print('OK LLMEnsemble instantiates')

# 4. Phase 5 invariant: 10 phase classes (8 original + 2 from Slice E proper) conform
from cinema.phases.base import Phase
from cinema.phases.topic import TopicPhase
from cinema.phases.blueprint import BlueprintPhase
from cinema.phases.generation import GenerationPhase
from cinema.phases.audio import AudioPhase
from cinema.phases.assembly import AssemblyPhase
from cinema.phases.vision import VisionPhase
from cinema.phases.upload import UploadPhase
from cinema.phases.learning import LearningPhase
from cinema.phases.keyframe_render import KeyframeRenderPhase
from cinema.phases.motion_render import MotionRenderPhase
for cls in (TopicPhase, BlueprintPhase, GenerationPhase, AudioPhase,
            AssemblyPhase, VisionPhase, UploadPhase, LearningPhase,
            KeyframeRenderPhase, MotionRenderPhase):
    assert isinstance(cls(), Phase), cls.__name__
print('OK 10 phase classes conform to Phase protocol')

# 5. Phase 6 invariant: canonical audio.* paths (phase_b_audio.py deleted)
from audio.srt import generate_srt
from audio.music import master_music, generate_fal_bgm
from audio.foley import generate_scene_foley
from audio.effects import apply_au_plugin, PEDALBOARD_AVAILABLE
from audio.voiceover import generate_voiceover, VOICE_DIRECTIONS
from audio.dialogue import generate_dialogue_voiceover
from audio._client import client
from elevenlabs.client import ElevenLabs
assert isinstance(client, ElevenLabs), 'audio._client.client invariant broken'
print('OK audio domain: 7 submodules + canonical paths + shared client')

# 6. Phase 7+ invariants: domain shims still work, web_services builder works
import project_manager as pm
import domain.project_manager as dpm
assert pm.make_shot is dpm.make_shot, 'domain shim broken'
print('OK domain re-export shim identity')
from web_services import make_progress_callback
import queue
q = queue.Queue(); cb = make_progress_callback(q); cb('S', 'd', 50)
assert q.qsize() == 1
print('OK web_services.make_progress_callback')

# 7. cinema/services.py - read-only endpoint helpers
from cinema.services import state_snapshot, checkpoint_info
s = state_snapshot('nonexistent-pid'); assert s['paused'] == False
assert checkpoint_info('nonexistent-pid') == {'resumable': False}
print('OK cinema/services.py helpers')

# 8. Main entry points compile + main.py imports
import main
print('OK main.py imports cleanly')
" 2>&1 | grep -v "FutureWarning\|NotOpenSSL\|warnings.warn"
```

If any of those FAIL, **stop and diagnose before doing any new work.**

> **3.9 venv caveat:** `cinema_pipeline.py`, `cinema/core.py`, `web_server.py`, and `vbench_evaluator.py` use PEP 604 (`X | None`) in function defaults, which py_compile accepts but runtime `import` rejects in 3.9. The smoke above intentionally avoids importing those modules at runtime. Production environment is 3.10+. See section 5 issue 1 for the venv-upgrade instructions handed to the user.

---

## 1. What the codebase is

**AI cinema/video generation pipeline.** Takes a topic, generates a 60-second YouTube Shorts video end-to-end (topic -> blueprint -> script -> audio -> per-shot gen -> assembly -> upload -> learning).

Two entry points:
- **`main.py:run_autonomous_pipeline`** — CLI / non-interactive. Uses `cinema.pipeline.CinemaPipeline` (the simple driver) for 3 migrated phases + legacy free-functions for the rest.
- **`web_server.py`** -> **`cinema_pipeline.CinemaPipeline`** — interactive Flask dashboard with operator review gates, pause/resume, SSE progress streaming. **Now decomposed** into mixins + LifecycleService + PipelineCore (see section 3).

User context (from memory profile):
- Solo architect-via-LLM, AuDHD+BPD configuration
- 25y music, 25y psychology, 3y cinema background
- Prefers blunt accurate engagement; no sycophancy, no comparative inflation

---

## 2. Branch state

38 commits ahead of `pre-refactor-baseline`. The most recent block (chronological, oldest first):

```
3b277de  Phase 5 - Phase protocol POC
c63420b  TopicPhase
d1066a3  BlueprintPhase
e554f93  UploadPhase (minimal)
e8e825a  LearningPhase
2955b09  VisionPhase
0006adc  AssemblyPhase
adb540c  AudioPhase
8fc8b4a  driver + main.py migrate (3 phases)

- Phase 6 audio decomposition -
8f9dc22  audio/srt.py            (slice 1)
ffe2e52  audio/music.py          (slice 2)
cf02946  audio/foley.py          (slice 3)
92a0bba  audio/effects.py        (slice 4)
4de520c  audio/voiceover.py + audio/_client.py (slice 5)
ea4bc45  audio/dialogue.py       (slice 6)

- Post-Phase-6 cleanups + Phase 7-10 -
188654f  delete dead llm/router.py + its test
0a7f9b3  delete dead LLMEnsemble.ensemble_quality_vote + EnsembleQualityResult
11596db  .env.example completed (all 18 env vars)
96262ff  tests/ reorg -> unit/ (12) + integration/ (3)
4205077  CLAUDE.md architecture preamble (Phase 10 partial)
8f54eb2  domain/ package - 6 project/character/location modules (Phase 8)
d8c1461  migrate 7 phase_b_audio callers + delete phase_b_audio.py
c21bbbb  docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md
bdedd17  web_services.make_progress_callback (Phase 7 partial)

- cinema_pipeline.py migration (Slices A-E) -
e31e266  Slice A: LifecycleService protocol + wired into PipelineContext
4db9b8a  Slice B: ShotControllerMixin
bcd5255  Slice C: ReviewControllerMixin
1387ce3  Slice D: CheckpointStoreMixin
a10b653  Slice E (scoped): LifecycleService adoption in CinemaPipeline
bc98a01  Phase 7 proper: cinema/services.py + read-only endpoint decoupling
362bed9  Slice E proper: KeyframeRenderPhase + MotionRenderPhase (Option B)

- Standalone controllers (slice 1 of 2-3) -
42a290f  PipelineCore extraction - split __init__ into long-lived + runtime

- Handoff -
6f85c38  docs(handoff): this file
0e369db  docs(handoff): regenerate with ASCII-friendly characters

- Standalone controllers (slice 2 of 3) -
11e5795  ShotController class - composition replaces ShotControllerMixin

- V1 close-out: Phases 0 through 4 -
294851b  chore: Phase 0 pre-V1-completion cleanup (latent imports, vertex-ai-key, sys.path.insert)
f9c575c  fix: restore _find_take + _mutate_shot delegates broken by Slice 2 (regression hunt)
22aa710  refactor(cinema/review): promote ReviewController to standalone (Slice 3b Phase 1a)
70cafc7  refactor(cinema/checkpoint): promote CheckpointStore to standalone (Slice 3b Phase 1b)
c62f9cd  refactor(web_server): cache PipelineCore per project (Slice 3b Phase 1c)
c1350ae  refactor(cinema/review): migrate _wait_for_gate to lifecycle.wait_for_gate (Phase 2)
82a27e6  docs(cinema): document Phase Protocol contracts, approval state, take lineage (Phase 3)
2f29c04  docs(handoff): close out V1 refactor (Phase 4)

- V1.1 design-critique follow-up -
75d65d7  V1.1 #4: renumber lessons 8.13-8.19 chronologically
285bd75  V1.1 #3: make host protocols @runtime_checkable
9de17c7  V1.1 #5: add RunState dataclass; unify scattered run-state ownership
d8135d7  V1.1 #2: auto-generate delegates via tools/gen_delegates.py
00e8f34  V1.1 #1: add tests/integration/test_cross_controller.py (formalizes Lesson 8.17)
<this>   V1.1 final: REFACTOR_HANDOFF.md refresh
```

**Branch:** `refactor/architecture-cleanup`
**Baseline tag:** `pre-refactor-baseline` (the very first commit, before any refactor work).

---

## 3. Top-level package layout (current)

```
Content/
- config/                          <- Phase 2 — settings singleton + prompts
  - settings.py
  - __init__.py
  - prompts/pipeline_context.md
- identity/                        <- Phase 3 — face validation domain
  - types.py
  - validator.py
  - __init__.py
- llm/                             <- Phase 4 — LLM domain
  - ensemble.py                    (ensemble_quality_vote deleted)
  - chief_director.py
  - blueprint_director.py
  - style_director.py
  - __init__.py                    (no longer exports EnsembleQualityResult)
- cinema/                          <- Phase 5 + cinema_pipeline migration
  - pipeline.py                    the simple driver (linear, non-interactive)
  - context.py                     PipelineContext + .lifecycle field
  - lifecycle.py                   LifecycleService protocol + Null + Threaded
  - core.py                        PipelineCore dataclass + build_pipeline_core factory
  - services.py                    state_snapshot + checkpoint_info (Phase 7 helpers)
  - checkpoint.py                  CheckpointStoreMixin
  - shots/
    - controller.py                ShotControllerMixin (12 methods)
    - __init__.py
  - review/
    - controller.py                ReviewControllerMixin (11 methods)
    - __init__.py
  - phases/                        10 Phase classes
    - base.py                      Phase protocol + PhaseResult
    - topic.py
    - blueprint.py
    - generation.py
    - audio.py
    - assembly.py
    - vision.py
    - upload.py
    - learning.py
    - keyframe_render.py           NEW - per-shot keyframe loop as Phase
    - motion_render.py             NEW - per-shot motion loop as Phase
    - __init__.py
- audio/                           <- Phase 6 — 7 focused submodules
  - _client.py                     shared ElevenLabs singleton
  - srt.py
  - music.py
  - effects.py
  - voiceover.py
  - dialogue.py
  - foley.py
  - __init__.py
- domain/                          <- Phase 8 — project/scene/character/location
  - project_manager.py
  - character_manager.py
  - location_manager.py
  - continuity_engine.py
  - scene_decomposer.py
  - dialogue_writer.py
  - __init__.py
- data/                            runtime data (gitignored experiments.db)
- docs/
  - REFACTOR_HANDOFF.md            this file
  - CINEMA_PIPELINE_MIGRATION_DESIGN.md
- tests/
  - conftest.py                    pytest fixtures + sys.path bootstrap
  - analyze_sweep_results.py       analysis utility (not a test)
  - unit/                          12 files - pure logic + mocks
  - integration/                   3 files - exercise real APIs / e2e
- (root)                           legacy + glue
  - cinema_pipeline.py             interactive orchestrator (now mixin-composed)
  - web_server.py                  Flask app
  - web_services.py                make_progress_callback (Phase 7 partial)
  - main.py                        CLI entry
  - run_example.py
  - cleanup.py
  - project_manager.py             root re-export shim -> domain.project_manager
  - character_manager.py           (and 5 more domain shims)
  - phase_a_generator.py           legacy module - not yet migrated
  - phase_c_assembly.py
  - phase_c_ffmpeg.py
  - phase_c_vision.py
  - phase_d_upload.py
  - phase_e_learning.py
  - phase_0_topic.py
  - (per-shot loop deps not yet touched - lip_sync, workflow_selector,
       kling/sora/veo/ltx_native, comfyui_workflow_gen, cost_tracker,
       quality_tracker, vbench_evaluator, coherence_analyzer,
       research_engine, web_research, etc.)
```

**Notably gone:** `phase_b_audio.py` (deleted in commit `d8c1461`).

---

## 4. Invariants (MUST be preserved by every commit)

Each is verified by the section 0 smoke block. The "why" tells you what the invariant protects.

| # | Invariant | Why |
|---|---|---|
| 1 | All `.py` files compile (`py_compile`) | Baseline correctness |
| 2 | `import identity.validator` does NOT pull `phase_c_vision` | Phase 3 broke the historical circular import |
| 3 | `LLMEnsemble()` instantiates without error | Phase 4 fixed a name-shadow bug that would have crashed at runtime |
| 4 | `isinstance(<each Phase class>(), Phase) == True` (10 classes — 8 original + 2 render) | The Phase protocol contract |
| 5 | All canonical `audio.*` paths import + `audio._client.client` is an `ElevenLabs` instance | Phase 6 + the post-Phase-6 phase_b_audio deletion |
| 6 | `main.py` imports cleanly | Entry-point regression check |
| 7 | `project_manager.X is domain.project_manager.X` (and 5 other domain modules) | Phase 8 re-export shim integrity |
| 8 | `web_services.make_progress_callback(queue)` emits dict events into the queue | Phase 7 partial |
| 9 | `cinema.services.state_snapshot(pid)` and `checkpoint_info(pid)` return the expected shapes | Phase 7 deep decoupling |

**Retired:**
- Old invariant 7 (`phase_b_audio.client` is an `ElevenLabs` instance) — retired with the file deletion. Successor is invariant 5 (audio._client.client).

**Verification limit on local 3.9 venv:**
- `cinema_pipeline.py`, `cinema/core.py`, `web_server.py`, `vbench_evaluator.py` py_compile in 3.9 but fail at runtime import (PEP 604 in function defaults). Production environment is 3.10+. AST + selective import are the verification strategies for those files until the venv upgrades (see section 5 issue 1).

---

## 5. Open issues (flag for future work, not blocking)

Updated from the original handoff. RESOLVED = closed this round, UPDATED = status changed, OPEN = still open.

| # | Issue | Status | Notes |
|---|---|---|---|
| 1 | Python 3.9 vs PEP 604 syntax | DEFERRED | Out of V1 scope (user-side action). User has instructions to upgrade to 3.11 via `brew install python@3.11`. `requirements-frozen-py39.txt` is the migration snapshot. AST + selective-import verification remains the strategy for `cinema_pipeline.py` / `web_server.py` / `cinema/core.py` / `vbench_evaluator.py` until upgrade. |
| 2 | `.env.example` incomplete | RESOLVED | Resolved in `11596db`. All 18 env vars documented. |
| 3 | `llm/router.py` dead | RESOLVED | Deleted in `188654f`. |
| 4 | `LLMEnsemble.ensemble_quality_vote` dead | RESOLVED | Deleted in `0a7f9b3` along with `EnsembleQualityResult`. |
| 5 | `cinema_pipeline.py` god module | RESOLVED | Decomposed via Slices A-E + standalone-controllers Slices 1+2+3b (Phases 1a/1b/1c) + V1.1 #5 (RunState). File now 1,036 lines (was 1,526; -32%). `class CinemaPipeline:` with EMPTY base class list. Three standalone controllers + LifecycleService + PipelineCore + shared RunState, all composed. ~150 LOC of forwarder + delegate boilerplate is auto-generated by `tools/gen_delegates.py`. |
| 6 | `tests/` reorg into unit/integration | RESOLVED | Resolved in `96262ff`. |
| 7 | No structured logging | DEFERRED | Out of V1 scope (multi-week, ~100-file `print()` -> logger conversion). Phase 10's preamble portion landed in `4205077`. Filed as a separate future track. |
| 8 | Lazy imports in `audio/` | RESOLVED | Resolved in Slices 4-6. All audio submodules use eager top-level imports. `audio/_client.py` is the cycle-free shared dependency. |
| 9 | V2 plugin architecture (cinema_pipeline_v2 path) | N/A | Per user, that path is dead. Critique filed (V2_HANDOFF_CRITIQUE deltas) -- the V2-applicable contract gaps that map to V1 are addressed in `docs/CONTRACTS.md`. |
| 10 | `vertex-ai-key.json` (empty) at repo root | RESOLVED | Deleted in Phase 0 (`294851b`). |
| 11 | Cleanup `PipelineContext` dict-API methods | DEFERRED | Out of V1 scope. Still has `__getitem__`/`__setitem__`/`get`/`update`/... for legacy `ctx["foo"]` compat. Removable once all callers migrate to `ctx.foo`. No urgency. |
| 12 | Per-test `sys.path.insert` lines now point at the wrong dir | RESOLVED | Phase 0 (`294851b`) bulk-removed via Python script -- 16 files cleaned (3 patterns: A semicolon-form, B standalone, C PROJECT_ROOT-block). Conftest's legitimate PROJECT_ROOT line untouched. |
| 13 | `_wait_for_gate` doesn't use `lifecycle.wait_for_gate` | RESOLVED | Phase 2 (`c1350ae`). Now uses predicate-poll via `lifecycle.wait_for_gate`. Pattern I consistently applied across the codebase. Behavior change: no Resume click needed after approvals (auto-resolves within poll_interval). Manual pause still works independently. |
| 14 | Latent missing imports in `cinema/shots/controller.py` | RESOLVED | Phase 0 (`294851b`). Added: `time`, `get_reference_image`, `face_swap_video_frames`, `generate_lip_sync_video`, `generate_rife_interpolation`, `upscale_video_seedvr2`, `stitch_modules`. Previously latent NameError in `apply_correction` / `diagnose_clip` / `generate_scene_preview` code paths. |
| 15 | Slice 2 regression: cross-mixin `self._find_take` broken | RESOLVED | Phase 0.5 (`f9c575c`). Slice 2 dropped ShotControllerMixin but didn't add `_find_take` + `_mutate_shot` delegates -- ReviewControllerMixin's call chain silently broke. Restored via delegates on CinemaPipeline. Hunt + fix took 2 turns; behavioral verification template added (see Lesson 8.17). |
| 16 | Unused `import sys, os` lines in 5 test files (Phase 0 follow-up) | OPEN | Phase 0's Pattern A removed the `; sys.path.insert(...)` clause but kept the bare imports. Some are now likely unused. Removing safely requires AST-level reference detection per file. Polish opportunity. |
| 17 | Web endpoints don't call `lifecycle.signal_gate` after approvals | OPEN | Phase 2 left the polling fallback in place. If endpoints called `pipeline.lifecycle.signal_gate(gate_name)` after each approval, the gate-wait would unblock within ~60ms instead of ~500ms (verified empirically). UX optimization, not a correctness issue. |
| 18 | `_running_cores` cache invalidation | OPEN | Phase 1c added the cache without invalidation. If `settings.json` changes on disk while the server runs, cached `ContinuityEngine` / `ChiefDirector` have stale config. Operational fix today: restart the server. A file-watcher or settings-version hook would invalidate cleanly. |
| 19 | Scattered run-state ownership | RESOLVED | V1.1 #5 (`9de17c7`). Added `cinema/runstate.py` with a `RunState` dataclass holding all 9 per-run fields. All three controllers + the orchestrator share ONE instance; mutations propagate by reference. CheckpointStoreHost protocol deleted entirely (host became unnecessary; CheckpointStore reads/writes runstate directly). |
| 20 | Host protocols not `@runtime_checkable` | RESOLVED | V1.1 #3 (`285bd75`). All three host protocols now decorated. `isinstance(host, ShotControllerHost)` works in tests; brings them to parity with the existing `Phase` protocol. |
| 21 | Delegate boilerplate on CinemaPipeline (~30 methods) | RESOLVED | V1.1 #2 (`d8135d7`). `tools/gen_delegates.py` auto-generates the delegate + forwarder section between marker comments. Idempotent + `--check` mode for drift detection. Pre-commit-hook ready. |
| 22 | No integration test for cross-controller chains | RESOLVED | V1.1 #1 (`00e8f34`). `tests/integration/test_cross_controller.py` runs 10 behavioral tests exercising every cross-controller call chain end-to-end. Works under pytest AND as a standalone Python script (bootstraps its own sys.path). |
| 23 | Lesson numbering off-by-order (8.13 wedged between 8.15 and 8.16) | RESOLVED | V1.1 #4 (`75d65d7`). Lessons 8.7-8.19 now chronologically ordered. |

---

## 6. The five-step refactor slice playbook (CANONICAL)

**Unchanged from the original handoff.** Every slice still follows this same shape. If a slice can't fit, that's a signal the slice is too ambitious — split it.

### Step 1 — Read
- Identify the target function(s) and their line range.
- Check **external callers** with grep.
- Check **internal module dependencies**: does the function use module-level symbols (client, settings, constants, other private helpers)?
- For each module-level dep that lives elsewhere, decide: move with it, lazy-import, or refactor to inject.

### Step 2 — Write the new module
- Place under the **top-level domain package** (`audio/`, `identity/`, `llm/`, `domain/`, `cinema/`). Not under `cinema/phases/` — that's for Phase wrappers.
- Same function bodies; minimal docstring + module banner.
- Lazy imports inside function bodies if there's a circular-dep risk.
- Public name matches the legacy name exactly (no renames during the move).

### Step 3 — Update the legacy module with re-export
- **Remove** the old function definitions. For large blocks, use AST-based extraction via a Python script (this round used the pattern repeatedly — see section 7 Pattern J).
- **Add** a re-export at the top: `from new.module import X  # noqa: F401`.
- **Leave a marker comment** where the function used to be.

### Step 4 — Verify (identity-check + compile)

**Identity check is the strongest guarantee.** `a is b` proves it's the same Python object via both paths.

```bash
cd /Users/hyungkoookkim/Content && PY=/Users/hyungkoookkim/Content/.venv/bin/python && $PY -c "
import sys; sys.path.insert(0, '.')
import py_compile, pathlib
ok = failed = 0
for py in pathlib.Path('.').rglob('*.py'):
    rel = str(py)
    if any(d in rel for d in ('.venv', '.claude', '__pycache__', '.gitnexus', '.serena', 'web/node_modules')): continue
    try: py_compile.compile(str(py), doraise=True); ok += 1
    except py_compile.PyCompileError as e: failed += 1; print(f'FAIL {rel}: {e}')
print(f'COMPILE: {ok} ok, {failed} failed')

from new.module import target as new_path
from legacy.module import target as legacy_path
assert new_path is legacy_path, f'identity mismatch'
print('OK identity holds')

# Run the section 0 smoke block to confirm all 9 invariants still hold
"
```

### Step 5 — Commit
- One commit per slice. Stable history > heroic mega-commits.
- Title: `refactor(<package>): <verb> <subject>`
- Body: what moved + cross-module dep handling + verification summary + line-count tally.

---

## 7. Patterns established during this refactor (USE THESE)

**Patterns A-F are unchanged from the original handoff. New patterns G-K were added this round.**

### Pattern A — Re-export shim for backward compat
When moving a function out of a legacy module, leave a re-export at the old name. Identity check `audio.X.fn is legacy.X.fn` proves it's the same object.

### Pattern B — Lazy import to break circular deps during migration
Defer the import to call time. Document **why** in a comment, and **when it can become eager** (typically when the dep relocates to a leaf module).

### Pattern C — `PipelineContext` dict-API compat
`cinema.context.PipelineContext` is a dataclass that ALSO implements `__getitem__`, `__setitem__`, `get`, `update`, `keys`, `items`, `values`, `as_dict`. Legacy `def f(ctx: dict)` keeps working when passed a `PipelineContext`.

### Pattern D — Phase wrappers do ONE thing
`cinema/phases/*.py` classes each wrap **one** orchestrator-level entry function. Where a legacy module has multiple "phase-worthy" operations, **don't combine them** — defer the second one or split.

### Pattern E — "Validator service" vs. "Phase"
Not everything is a phase. If a function is called *per-shot inside a loop*, it's a **validator service**, not a Phase. Phases are for orchestrator-driven steps.

### Pattern F — File-system as ground truth for I/O phases
AssemblyPhase / AudioPhase / UploadPhase use a post-condition "output file exists" check rather than trusting the wrapped function's return value.

### Pattern G — Mixin composition for class decomposition (NEW)

When a god class has 30+ methods that group naturally but share state heavily, decompose into mixins rather than self-proxying composition. Each mixin file becomes independently readable while preserving the `self.X` access patterns:

```python
# cinema/shots/controller.py
class ShotControllerMixin:
    """Per-shot generation methods. Designed as a mixin on CinemaPipeline."""
    def generate_keyframe_take(self, scene_id, shot_id): ...

# cinema_pipeline.py
class CinemaPipeline(ShotControllerMixin, ReviewControllerMixin, CheckpointStoreMixin):
    pass
```

**Verify via AST:**
- `CinemaPipeline.bases` contains all expected mixins
- 0 of the moved methods remain in `CinemaPipeline.__dict__` (no duplicates)
- All moved methods are accessible via `getattr(CinemaPipeline, method_name)` (resolved via MRO)

Used by Slices B/C/D of the cinema_pipeline migration. The result: ~700 LOC moved out of `cinema_pipeline.py` with zero method-body rewrites.

### Pattern H — Property proxies for backward-compat after refactor (NEW)

When you want to extract long-lived state into a dataclass (`PipelineCore`) but existing code reads it via `self.X`, add `@property` accessors that return `self._core.X`. Critical: properties return the **underlying object reference**, not a copy — so in-place mutations like `self.project.clear()` still mutate the dict that `self._core.project` points to.

```python
class CinemaPipeline(...):
    def __init__(self, project_id, core=None):
        self._core = core or build_pipeline_core(project_id)

    @property
    def project(self) -> dict:
        return self._core.project  # reference, not copy — mutations persist
```

Used by the standalone-controllers slice 1 (PipelineCore extraction).

### Pattern I — LifecycleService injection via PipelineContext (NEW)

Pause/resume/cancel/progress are pipeline-wide concerns. Instead of each component owning its own flags, define a Protocol (`LifecycleService` in `cinema/lifecycle.py`) and inject one instance via `PipelineContext.lifecycle`:

```python
# Non-interactive CLI: default is NullLifecycle (no-op)
ctx = PipelineContext(topic="...")
# ctx.lifecycle is NullLifecycle() — calls are no-ops

# Interactive web server: ThreadedLifecycle (Event-backed)
ctx = PipelineContext(lifecycle=ThreadedLifecycle(progress_callback=cb))
# ctx.lifecycle.check_pause() blocks; cancel() flips the flag; etc.
```

Phases call `ctx.lifecycle.is_cancelled()` / `check_pause()` / `report_progress()` voluntarily at pause-safe points.

### Pattern J — Hybrid extraction (loops as phases, gates inline) (NEW)

When an orchestrator's `generate()` method contains a mix of phase-shaped logic (transformations) and not-phase-shaped logic (gate waits, operator input), don't force everything into the Phase protocol. Extract only the phase-shaped parts; let the rest stay procedural.

Used by Slice E proper: `KeyframeRenderPhase` and `MotionRenderPhase` were extracted; the three gates (`PLAN_REVIEW`, `KEYFRAME_REVIEW`, `REVIEW`) stayed as inline `_wait_for_gate(...)` calls in `generate()`. The cost-benefit:
- YES Per-shot loop becomes testable in isolation (build a fake `shot_generator`)
- YES The loop logic is reusable from main.py or scripts
- NO The two orchestrators (driver vs CinemaPipeline) don't fully unify
- YES Avoids the "gate-phase" hack (a "phase" that does nothing but wait)

### Pattern L — TYPE_CHECKING guard for PEP-604-incompatible transitive imports (NEW in Slice 2)

When a new file needs to type-annotate parameters with a class whose module transitively imports a file with PEP 604 in function defaults (e.g., `cinema.core` -> `vbench_evaluator.py`'s `tolerance: float | None = None`), don't import the type at runtime. With `from __future__ import annotations` in effect, annotations are strings and never evaluated, so the import is purely for type-checkers.

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cinema.core import PipelineCore  # only for type-checkers

class ShotController:
    def __init__(self, core: PipelineCore, ...):  # string annotation at runtime
        self._core = core
```

This restored the local 3.9 verification path for `cinema/shots/controller.py` after Slice 2 introduced the new `PipelineCore` parameter. Without the guard, importing the module on 3.9 fails at `cinema.core`'s `vbench_evaluator` import.

Use whenever a new module:
- Needs a type from a 3.9-broken module, AND
- Doesn't use that name at runtime (only as an annotation).

Don't use for runtime usage — Protocols you `isinstance`-check against, classes you instantiate, etc.

### Pattern K — AST-based bulk method extraction (NEW)

When moving many methods out of a class file, hand-editing is error-prone. Use a Python script with `ast` to identify exact line ranges and extract them precisely:

```python
import ast
tree = ast.parse(open("source.py").read())
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TargetClass")
src_lines = open("source.py").read().splitlines(keepends=True)

for item in cls.body:
    if isinstance(item, ast.FunctionDef) and item.name in MOVE_THESE:
        start = item.decorator_list[0].lineno if item.decorator_list else item.lineno
        end = item.end_lineno
        body = "".join(src_lines[start-1:end])
        # ... write to new file ...
```

Used by Slices B/C/D of the cinema_pipeline migration. Avoids regex fragility for multi-line method bodies. The handoff includes the script template — adapt the `MOVE_THESE` set per slice.

### Pattern M — Shared RunState dataclass (NEW in V1.1)

When multiple components need to read + write the same per-run mutable state, give them a SHARED dataclass instance rather than scattering state ownership. The pattern:

```python
@dataclass
class RunState:
    field_a: dict = field(default_factory=dict)
    field_b: list = field(default_factory=list)
    ...

class Orchestrator:
    def __init__(self):
        self._runstate = RunState()  # one instance
        self._ctrl_x = ControllerX(core, lifecycle, host, self._runstate)
        self._ctrl_y = ControllerY(core, lifecycle, host, self._runstate)
        # both controllers hold the SAME reference; mutations propagate
```

Used in V1.1 #5 (`9de17c7`). Before: state ownership was scattered (ShotController owned `shot_results`, ReviewController owned `review_clips`, CinemaPipeline owned 7 other fields). After: one canonical RunState; finding a field is one file-read; adding a field is one line.

When NOT to use:
- For long-lived deps (those go in a separate immutable Core).
- For per-call ephemera (use function locals or `PipelineContext`).
- For state that ONE component genuinely owns (no cross-reads).

When TO use:
- When 2+ components mutate the same state via different code paths.
- When the orchestrator AND controllers need read access to the same fields.
- When state ownership questions repeatedly require consulting docs.

### Pattern N — Marker-block code generation (NEW in V1.1)

When delegation boilerplate accumulates (~30 methods of mechanical forwarding), generate the section via a script and mark it with `# GENERATED BEGIN / END` comments. Hand-edits outside the markers survive; edits inside are overwritten on regen.

```python
# in target file:
class Foo:
    def something_else(self): ...

    # GENERATED BEGIN -- tools/gen_X.py
    # ... mechanical content rewritten by the script ...
    # GENERATED END

    def more_handwritten(self): ...
```

Script provides:
- Default mode: rewrite the marker block in place
- `--check` mode: exit non-zero if regen would change the file (CI / pre-commit gate)
- `--print` mode: dump the generated section to stdout

The `--check` mode is what makes the script trustworthy. Without drift detection, hand-edits inside the marker block silently survive until someone re-runs the generator.

Used by V1.1 #2 (`d8135d7`) -- `tools/gen_delegates.py` generates 9 RunState forwarders + 24 controller delegates on CinemaPipeline. Configuration (which methods to delegate) is a hard-coded list in the script; adding a new delegated method requires editing that list. Methods purely internal to a controller don't need delegates.

When NOT to use:
- For genuinely complex code that requires per-instance reasoning.
- For sections with embedded business logic.
- When the boilerplate is < ~10 lines (overhead not worth it).

When TO use:
- When the section is mechanically derived from elsewhere (controller method list, dataclass fields, schema).
- When signature drift between source-of-truth and consumer is a real risk.
- When the section is large enough that maintainers stop reading it carefully.

---

## 8. Lessons learned / Specific pitfalls

**Items 8.1-8.6 are unchanged from the original handoff. New items 8.7-8.13 added this round.**

### 8.1-8.6 (preserved from original)
- 8.1 Phase 2 settings-shadow bug
- 8.2 Bulk-migration script import-insertion site
- 8.3 `cinema_pipeline_v2_runner.py` collision
- 8.4 Package vs module import shadow
- 8.5 `git stash --include-untracked` undid staged `git rm --cached`
- 8.6 Multi-line imports break naive grep-based inventory

### 8.7 The cwd reset on long Bash scripts (NEW)

Bash commands that span multiple seconds (e.g., long Python heredocs) sometimes execute with cwd reset to the user's home directory instead of the project root. Symptom: a `pathlib.Path('.').rglob('*.py')` returns 100,000+ files (scanning `~/.cache`, `~/Library`, etc.) instead of the project's ~100.

**Fix:** always prefix scripts with `cd /Users/hyungkoookkim/Content && PY=/...` to make the working directory explicit. The Bash tool's persistent-cwd contract is unreliable for run_in_background and long-running commands.

### 8.8 PEP 604 in function defaults vs annotations (NEW)

`def f(x: int | None = None):` is two different things to Python 3.9:
- **Annotation** (`x: int | None`) — stored as a string if `from __future__ import annotations`, never evaluated at runtime.
- **Default value** (`= None`) — annotation expression evaluated at function definition time -> `TypeError: unsupported operand type(s) for |`.

Files in this repo with PEP 604 in function defaults that fail to runtime-import on 3.9: `vbench_evaluator.py`, `cinema_pipeline.py`, `web_server.py`, `cinema/core.py` (transitively via vbench_evaluator import). py_compile passes for all of them — the bytecode is fine; only the import-time evaluation fails.

Don't conflate "compiles" with "imports". The section 0 smoke test does both for the modules that CAN runtime-import on 3.9; for the others, py_compile + AST inspection are the verification ceiling.

### 8.9 Mixin pattern preserves identity (NEW)

When a method moves from a class body into a mixin: `LegacyClass.method is Mixin.method` evaluates True (the function object is reached via MRO; not copied). This means the identity-check pattern from section 6 Step 4 still works on mixin moves.

But: gitnexus_detect_changes flags every moved method as "Modified" because it tracks symbols by **file location**, not Python identity. The "Modified" count after a mixin extraction is the count of moved methods — but `affected_processes` is correctly 0 because the call edges are preserved.

### 8.10 `gitnexus_impact "HIGH" risk` is often a false positive on extractions (NEW)

When extracting a method, gitnexus_impact computes the transitive reach (depth 1 -> 2 -> 3 callers) and reports the maximum reach as the risk label. For methods called transitively by `run_pipeline` -> `generate` -> ..., the label becomes HIGH even though only the d=1 callers (which are usually 1-2 internal methods) actually need to be updated.

**Mitigation:** focus on the d=1 list explicitly. If d=1 is all-internal-to-the-file-being-modified AND the slice preserves the import surface (re-export shim or mixin MRO), the HIGH risk label is benign.

### 8.11 Property accessors and mutable references (NEW)

`@property def x(self): return self._core.x` returns the **same object** that `self._core.x` holds, not a copy. So:

- YES `self.x.clear()` clears the underlying dict (works through the property)
- YES `self.x.append(...)` mutates the underlying list
- YES `self.x.frob = "y"` sets an attribute on the underlying instance
- NO `self.x = new_value` does NOT work — it tries to set an attribute on the host class, hitting the property's lack of a setter

This bit me when planning the `_refresh_project_snapshot` integration. The method calls `self.project.clear()` + `self.project.update(latest)` — both work through the property. But if any caller wrote `self.project = latest` (full assignment) instead, the property would have needed a setter.

### 8.12 The hook for gitnexus index staleness lags behind reality (NEW)

The `PostToolUse:Bash` hook reports "GitNexus index is stale" with a "last indexed: <sha>" marker that doesn't update when you re-run `npx gitnexus analyze`. After running analyze, the hook will still claim staleness on subsequent commits.

The index IS fresh after analyze (verify by looking at `.gitnexus/meta.json` or by the analyze run's "N nodes | M edges" output). The hook's marker is just a cached value somewhere that doesn't catch up. Not actionable.

### 8.13 Dead-import sweep after extraction (NEW)

When a slice moves methods/constructors into a new module, imports in the source file become dead. Examples from this round:

- After Slice E adoption: `import threading` became dead (the Event lived inside ThreadedLifecycle now).
- After PipelineCore extraction: 6 imports became dead (VBenchEvaluator, QualityTracker, CostTracker, LLMEnsemble, ChiefDirector, ContinuityEngine — all moved into `cinema/core.py`).

**Sweep pattern:** after the structural change, grep for each previously-imported name in the source file. If it appears ONLY in the import line, remove the import.

```bash
for name in LLMEnsemble VBenchEvaluator ContinuityEngine; do
  count=$(grep -c "\b${name}\b" cinema_pipeline.py)
  echo "$name: $count occurrences"
done
```

If `count == 1`, the import is dead. Remove it in the same commit as the structural change (it's caused by, not orthogonal to, the slice).

### 8.14 ShotControllerHost protocol with underscore method names (NEW in Slice 2)

When extracting a class whose methods call into other classes' "private" `_foo` methods, the Protocol that declares the interface looks weird:

```python
class ShotControllerHost(Protocol):
    def _refresh_project_snapshot(self) -> Optional[dict]: ...
    def _save_checkpoint(self) -> None: ...
```

Python's Protocol matching is by name regardless of convention — leading underscores are fine. The alternative is to rename the host's methods to public, which expands the slice. Pick name-stability over visual consistency unless you're already touching the host's other API.

### 8.15 Composition slice's "Modified" symbols include the renamed class members (NEW in Slice 2)

After Slice 2, gitnexus_detect_changes reports every method in `cinema/shots/controller.py` as "Modified" with `risk_level: critical`. The reason: the class containing them was renamed (`ShotControllerMixin` -> `ShotController`) and many bodies got `self._host._X` substitutions. The behavior is preserved (verified by the 11 Slice 2 checks), but file-location-based change detection can't see that.

Mitigation: cross-check with the actual behavioral verification (Slice 2-A through Slice 2-K in the commit's verification block). detect_changes's risk label is one input; the behavioral pass is the trump card.

### 8.16 Composition slices can silently break cross-mixin self.X calls (NEW in V1 close-out)

When Slice 2 dropped `ShotControllerMixin` from `CinemaPipeline`'s base list and composed `ShotController` instead, the public method surface was preserved via 6 delegate methods. But 6 PRIVATE helpers (`_find_take`, `_mutate_shot`, `_take_output_path`, ...) only existed on the composed instance. `ReviewControllerMixin` had been calling `self._find_take` and `self._mutate_shot` via MRO -- those calls silently broke (AttributeError on first invocation).

The breakage was dormant because:
- The §0 smoke can't runtime-import `cinema_pipeline.py` (PEP 604; Lesson 8.8).
- Slice 2-I behavioral check used a stub host with `_resolve_take_path` stubbed -- exercising ShotController in isolation, never the real CinemaPipeline -> ReviewControllerMixin chain.
- The structural Slice 2 checks (A-G) verified delegate presence but not the cross-controller call graph.

Bug found + fixed in Phase 0.5 (`f9c575c`) by adding `_find_take` + `_mutate_shot` delegates to CinemaPipeline.

**Lesson:** when composition replaces mixin, identify EVERY method that other mixins call via `self.X`. Public + private. Add delegates for the ones still called. The Pattern G identity check (`a is b`) used to catch this for free via MRO; composition has to do it explicitly.

### 8.17 Behavioral test template for cross-controller chains (NEW)

The Slice 2-I check that missed Lesson 8.16's bug used a single-controller stub. The Phase 1a verification block introduced a better template: build a `TestPipeline` host that satisfies BOTH `ShotControllerHost` AND `ReviewControllerHost`, instantiate both controllers, exercise the cross-controller chain end-to-end. Example from `c1350ae`'s verification:

```python
class TestPipeline:  # satisfies both ControllerHost protocols
    def __init__(self, core, lifecycle):
        self._shot_ctrl = ShotController(core, lifecycle, self)
        self._review_ctrl = ReviewController(core, lifecycle, self)
        # ... satisfy both protocols by delegating

# Exercise the actual chain: ReviewController calls host._find_take
# which delegates to ShotController._find_take
manifest = host._review_ctrl._rebuild_review_clips()
# -> self._resolve_take_path(...) -> self._host._find_take(...) -> ShotController._find_take(...)
# If any link is broken, this raises AttributeError or returns wrong shape
```

Future composition slices MUST exercise the cross-controller chain explicitly, not stub the cross-call. Filed as Phase 4 follow-up #7 to formalize as `tests/integration/test_cross_controller.py`.

### 8.18 Thread safety for module-level caches in Flask (NEW)

`web_server.py`'s `_running_pipelines: dict[str, CinemaPipeline]` was added before Phase 1c without a lock -- the GIL makes single-bucket reads/writes atomic, but the "check-then-set" pattern in `_get_stage_pipeline` (look up by pid; if None, build) had a theoretical race where two concurrent requests could both build a pipeline.

Phase 1c added `_running_cores: dict[str, PipelineCore]` with `_cores_lock: threading.Lock` for the same pattern, because PipelineCore construction is expensive (~500ms). The lock prevents wasted builds under contention.

The existing `_running_pipelines` race wasn't fixed because (a) the user is a solo operator typically making 1 request at a time, and (b) the race produces a wasted CinemaPipeline construction, not a corrupted cache. Documenting the inconsistency: cache locking pattern should be uniform; can be aligned in a future polish slice.

### 8.19 lifecycle.wait_for_gate changes the UX subtly (NEW in Phase 2)

Phase 2 migrated `_wait_for_gate` from the old `pause() + _check_pause()` cycle to `lifecycle.wait_for_gate(predicate)`. The functional difference: operator no longer needs to click "Resume" after approving all shots at a gate. The predicate polls every 500ms and the gate auto-resolves.

This was a UX change worth documenting because:
- Old workflow: Approve all → click Resume → pipeline continues
- New workflow: Approve all → pipeline auto-continues within 500ms

Manual pause (via Pause button -> `pipeline.pause()`) still works independently; the other `lifecycle.check_pause()` call sites in the generate() loop honor manual pause.

If you want to restore the "click Resume" requirement (e.g., for batch UX where the operator wants a final go-ahead), revert this Phase or add a separate manual-gate concept. The current code is open to either direction.

### 8.20 Integration tests need their own sys.path bootstrap (NEW in V1.1)

`tests/integration/test_cross_controller.py` runs under pytest AND as a standalone Python script. Pytest's conftest.py handles `sys.path.insert(0, PROJECT_ROOT)` at module-load time -- but standalone invocation (`python tests/integration/X.py`) doesn't load conftest.

Pattern: each integration test file that needs to be standalone-runnable adds at the top:

```python
import sys, os
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
```

This is NOT the same as the dead `sys.path.insert` lines that Phase 0 removed -- those used `__file__/..` which evaluated to `tests/`, not project root. The two-dirs-up pattern correctly reaches project root from `tests/integration/`.

When the venv eventually upgrades to 3.10+ and pytest is on PATH, this bootstrap is redundant (conftest covers it). Until then, useful for ad-hoc test invocation during development.

### 8.21 Idempotent generators need drift detection to be trustworthy (NEW in V1.1)

`tools/gen_delegates.py` (V1.1 #2) regenerates a marker-delimited block in `cinema_pipeline.py`. The script has three modes:

- default: rewrite the marker block in place
- `--check`: exit non-zero if regen would change the file (drift detected)
- `--print`: dump generated section to stdout

The `--check` mode is what makes the script worth running. Without it, hand-edits inside the marker block silently survive until someone re-runs the generator -- the same class of bug as the Slice 2 silent regression (Lesson 8.16), just for generated code.

Verification template: simulate drift by appending a fake method inside the marker block, run `--check`, assert non-zero exit. The V1.1 #2 verification block includes this (test G).

If you build any future generator (e.g., for the integration-test harness, or for a schema-derived API), include `--check` mode. The hand-edits-survive bug is otherwise indistinguishable from "looks right at glance" until something breaks.

---

## 9. Remaining work — concrete roadmap

### 9.1 Standalone controllers (RESOLVED)

All three slices on this track shipped. Final state:

- **Slice 1 (`42a290f`)** -- PipelineCore extraction. Long-lived deps separated from runtime state.
- **Slice 2 (`11e5795`)** -- ShotController standalone via composition. Owns `shot_results`.
- **Slice 3b (`22aa710` + `70cafc7` + `c62f9cd`)** -- ReviewController + CheckpointStore standalone; web_server PipelineCore caching. Slice 3b was the "full" path (vs. 3a's pragmatic shortcut).

`cinema_pipeline.py` is now 1,027 lines (was 1,526). `class CinemaPipeline:` has an EMPTY base list. The orchestrator composes:

```python
self._core       = PipelineCore(...)              # heavy long-lived deps + services
self.lifecycle   = ThreadedLifecycle(...)         # per-run progress + cancel
self._shot_ctrl  = ShotController(core, lifecycle, host=self)
self._review_ctrl = ReviewController(core, lifecycle, host=self)
self._checkpoint = CheckpointStore(core, lifecycle, host=self)
```

CinemaPipeline itself has ~30 delegate methods that forward to the three controllers. Each controller has its own `ControllerHost(Protocol)` declaring exactly which `self.X` attributes/methods it needs from the host. CinemaPipeline implements all three protocols.

State ownership at end of V1:
- `shot_results` -> ShotController
- `review_clips` -> ReviewController
- (CheckpointStore has no per-run state -- pure file I/O)
- `scene_clips`, `scene_audio`, `failed_shots`, `current_*`, `_completed_scene_indices` -> orchestrator (CinemaPipeline)

web_server.py caches `PipelineCore` instances per project_id via `_running_cores: dict[str, PipelineCore]` + `_cores_lock: threading.Lock`. The 4 CinemaPipeline construction sites now reuse the cached core, amortizing the heavy service construction (ContinuityEngine + ChiefDirector + LLMEnsemble + VBenchEvaluator + QualityTracker + CostTracker) across endpoint calls.

### 9.2 Original workflow doc Phases 7-10 (post-Phase-6)

| Phase | Status |
|---|---|
| 7 -- Web service layer | RESOLVED. `web_services.py` + `cinema/services.py` decoupled the 2 read-only endpoints in Phase 7 proper. Slice 3b (Phase 1c) caches PipelineCore per project, amortizing construction across the remaining 5 endpoints. The "decouple per-endpoint construction from CinemaPipeline" framing is delivered via the cache rather than per-endpoint controller construction. |
| 8 -- Domain reorg | RESOLVED (`8f54eb2`). |
| 9 -- Tests reorg | RESOLVED (`96262ff`). |
| 10 -- Structured logging + CLAUDE.md preamble | DEFERRED. Preamble done (`4205077`). Structured logging out of V1 scope -- multi-week, ~100-file effort. Filed as separate future track. |

### 9.3 Other follow-ups (post-V1 and post-V1.1)

V1.1 #1-#5 items resolved this round are removed from this list. What remains:

| # | Item | Effort | Status |
|---|---|---|---|
| 1 | Python venv upgrade to 3.10+ (env, not code) | user-side | DEFERRED out of V1 scope |
| 2 | Cleanup `PipelineContext` dict-API methods (after all callers migrate to `ctx.X`) | medium | DEFERRED out of V1 scope (no urgency) |
| 3 | Structured logging conversion | weeks | DEFERRED out of V1 scope |
| 4 | Unused `import sys, os` lines in 5 test files (Phase 0 follow-up) | small | OPEN (polish; needs AST-level reference detection per file) |
| 5 | Web endpoints call `lifecycle.signal_gate` after approvals | small | OPEN (UX optimization; polling fallback already works) |
| 6 | `_running_cores` cache invalidation on settings.json change | small | OPEN (operational fix today: restart server) |
| 7 | Behavioral-test template for cross-controller chains (Lesson 8.17) | medium | RESOLVED in V1.1 #1 (`00e8f34`) |
| 8 | Pre-commit hook running `python tools/gen_delegates.py --check` | trivial | OPEN (user decision -- script supports it, hook not enabled) |
| 9 | Add `tests/integration/test_cross_controller.py` to whatever CI/test-runner the user actually uses | trivial | OPEN (file exists and works standalone; integration with CI is user-side) |
| 10 | Mass-rename host-protocol underscore-prefixed methods to public names (visual consistency) | medium | OPEN (Lesson 8.14 -- the underscore convention is technically correct but visually weird) |

---

## 10. User preferences observed

**Unchanged from the original handoff.** All preferences are still operative. Adding two observations from this round:

| Preference | Implication |
|---|---|
| **One-letter answers preferred** ("1", "2", "proceed", "go with b") | User signals direction; you proceed without re-asking. Reserve `AskUserQuestion` for genuine forks. |
| **Step-by-step, not auto-batched** | Each slice = one commit; pause between phases. Within a slice, batching tool calls is fine. |
| **No over-engineering** | YAGNI strictly enforced. |
| **No sycophancy / no inflation** | Per memory profile: "blunt accurate engagement". |
| **Explicit deferrals** | Document narrowed scope in the slice's commit message + the handoff doc. User is OK with reduced scope as long as it's intentional and visible. |
| **Identity-check verification is valued** | `a is b` test pattern. Use it for every re-export. |
| **(NEW) Design docs gate hard architectural slices** | When the original handoff said "Don't start cinema_pipeline.py migration without a design doc", that wasn't a polite suggestion. Writing the doc first (`c21bbbb`) was what unblocked Slices A-E and let me deliver Option B for Slice E without architectural drift. Repeat this pattern for the standalone-controllers Slice 2. |
| **(NEW) User explicitly asks for options before big decisions** | When a slice has multiple valid approaches, present the options + a recommendation + the main trade-off in 2-3 sentences. User picks; then execute. This worked well for Slice E (Option B) and Phase 7 scope decisions. |

---

## 11. Verification recipe for the next slice (standalone-controllers Slice 2)

When the next chat does standalone-controllers Slice 2 (extract `ShotController` class), this is the expected verification block:

```bash
PY=/Users/hyungkoookkim/Content/.venv/bin/python
cd /Users/hyungkoookkim/Content && $PY -c "
import sys; sys.path.insert(0, '.')

# 1. Compile (must be 0 failures)
import py_compile, pathlib
ok = failed = 0
for py in pathlib.Path('.').rglob('*.py'):
    rel = str(py)
    if any(d in rel for d in ('.venv', '.claude', '__pycache__', '.gitnexus', '.serena', 'web/node_modules')): continue
    try: py_compile.compile(str(py), doraise=True); ok += 1
    except py_compile.PyCompileError as e: failed += 1; print(f'FAIL {rel}: {e}')
print(f'COMPILE: {ok} ok, {failed} failed')

# 2. ShotController is constructable from PipelineCore + LifecycleService alone
#    (NO CinemaPipeline construction needed — that's the whole point of the slice)
from cinema.core import PipelineCore  # NOTE: won't import on 3.9 because of vbench
from cinema.lifecycle import NullLifecycle
from cinema.shots.controller import ShotController  # new standalone class
# Build a Core with fakes for testing
# ... (test fixture pattern TBD by Slice 2's design)

# 3. The methods on ShotController are the same callable objects as on ShotControllerMixin
#    (identity check — verifies the mixin's methods didn't get duplicated)
from cinema.shots.controller import ShotControllerMixin
for name in ('generate_keyframe_take', 'generate_motion_take', 'regenerate_shot',
             'diagnose_clip', 'apply_correction', 'generate_scene_preview'):
    # Whether mixin survives as a shim OR the methods migrate fully — must decide in Slice 2
    pass

# 4. All section 0 invariants still hold (re-run that block)
" 2>&1 | grep -v 'FutureWarning\|NotOpenSSL\|warnings.warn'
```

---

## 12. Standard rollback recipes

| Want to undo | Command |
|---|---|
| Last commit only | `git revert HEAD` (preserves history) |
| Last commit, destructive | `git reset --hard HEAD~1` |
| Standalone-controllers slice 1 only | `git revert 42a290f` |
| All cinema_pipeline migration (back to pre-Slice-A state) | `git reset --hard bdedd17` |
| All Phase 6+ work (back to pre-Phase-6) | `git reset --hard 8fc8b4a` |
| All refactor work (back to pre-refactor baseline) | `git reset --hard pre-refactor-baseline` |
| Selective revert | `git revert <commit>` then resolve conflicts |

---

## 13. Tips for the next chat

1. **Read section 6 (the playbook) before anything else.** Then section 0 (smoke test). These two together are 80% of what you need to operate.

2. **Don't skip the identity check** (or its AST equivalent for class moves). It catches the subtle bug where you accidentally redefined a function with slightly different behavior. `assert a is b` >> `assert callable(b)`.

3. **The 3.9 venv constraint is real but not blocking.** py_compile + AST inspection cover ~80% of what runtime tests would. The remaining 20% (does `cinema_pipeline.py` actually start? does `web_server.py` serve requests?) requires the user to run on their production 3.10+ environment.

4. **`PipelineContext` field list is FIXED** from empirical ctx inventory. Adding new fields requires editing `cinema/context.py`. The `lifecycle` field is required for any phase that wants pause/progress capabilities.

5. **The simple driver in `cinema/pipeline.py` is *just* a phase iterator.** Don't add retry/skip/fallback logic to it. Those concerns belong to phases themselves (or to wrapper phases).

6. **The mixin pattern (Pattern G) is the established way to decompose god classes** in this codebase. Don't try to invent a "better" pattern unless you're prepared to defend it against the existing one.

7. **Open design questions in `docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md` section 7 are still open.** Three questions about assembly ownership, checkpoint storage contract, and controller caching. If your slice touches any of those, resolve the relevant question first or document the deferral.

8. **The user said "do 1" / "go with b" / "proceed".** Match that energy. Brief options-with-recommendation; let them pick; execute. Don't over-explain.

9. **Update this handoff doc at the end of your session.** Replace the "**As of:**" line, add your new commits to section 2, update section 5 issues, update section 9 roadmap. The next chat reads this doc cold.

---

## 14. Quick-reference command palette

```bash
# Where are we?
git -C /Users/hyungkoookkim/Content log --oneline -20
git -C /Users/hyungkoookkim/Content branch --show-current
git -C /Users/hyungkoookkim/Content status --short

# Diff a recent slice
git -C /Users/hyungkoookkim/Content show 42a290f --stat
git -C /Users/hyungkoookkim/Content show 42a290f -- cinema/core.py

# Run smoke (the canonical version is at section 0)
PY=/Users/hyungkoookkim/Content/.venv/bin/python
cd /Users/hyungkoookkim/Content && $PY -c "...section 0 block..."

# Find a function across the codebase
grep -rn -E "^def function_name\b" --include="*.py" --exclude-dir=.venv --exclude-dir=.claude /Users/hyungkoookkim/Content

# Find external callers
grep -rn -E "(from module import|module\.function\b)" --include="*.py" --exclude-dir=.venv --exclude-dir=.claude /Users/hyungkoookkim/Content

# AST-extract methods from a class (the Pattern K script)
PY=/Users/hyungkoookkim/Content/.venv/bin/python
$PY <<'PYEOF'
import ast
src = open("cinema_pipeline.py").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CinemaPipeline")
src_lines = src.splitlines(keepends=True)
MOVE_THESE = {"method_a", "method_b"}
for item in cls.body:
    if isinstance(item, ast.FunctionDef) and item.name in MOVE_THESE:
        start = item.decorator_list[0].lineno if item.decorator_list else item.lineno
        end = item.end_lineno
        body = "".join(src_lines[start-1:end])
        print(f"--- {item.name} ({start}..{end}) ---")
        print(body)
PYEOF

# GitNexus
npx gitnexus analyze   # refresh after commits (the hook reminds you; sometimes lags — see lesson 8.12)
```

---

## 15. End of handoff (V1 + V1.1 close-out)

V1 architectural completion shipped in commits `294851b` through `2f29c04`. V1.1 design-critique follow-up shipped in commits `75d65d7` through this commit. Branch `refactor/architecture-cleanup` is at 54 commits ahead of `pre-refactor-baseline`. Ready to merge to main OR to keep as a feature branch indefinitely -- both states are stable.

### What V1 close-out delivered

| Track | Outcome |
|-------|---------|
| `cinema_pipeline.py` god-module decomposition | DONE. Empty base class list. 1,526 -> 1,036 lines (-32%). ShotController + ReviewController + CheckpointStore standalone; LifecycleService + PipelineCore + RunState composed. |
| Web server PipelineCore caching | DONE. `_running_cores` cache with `threading.Lock` amortizes heavy service construction across endpoint calls. |
| Lifecycle consistency | DONE. `_wait_for_gate` migrated to `lifecycle.wait_for_gate`. Pattern I consistently applied. |
| Contract documentation | DONE. `docs/CONTRACTS.md` documents Phase Protocol behavioral contracts, approval state model, take lineage. |
| Slice 2 silent regression | FIXED in Phase 0.5. Behavioral-test template (Lesson 8.17) added; formalized as integration test in V1.1. |
| Latent import bugs | FIXED in Phase 0. 7 names now bound at module scope in `cinema/shots/controller.py`. |
| Dead `sys.path.insert` lines | FIXED in Phase 0. 16 test files cleaned via Python AST script. |
| `vertex-ai-key.json` | DELETED in Phase 0. |

### What V1.1 delivered (design-critique follow-up)

| Item | Outcome |
|------|---------|
| #4 Lesson renumber | DONE (`75d65d7`). 8.7-8.19 monotonic. |
| #3 `@runtime_checkable` host protocols | DONE (`285bd75`). `isinstance(host, ShotControllerHost)` works in tests. |
| #5 Shared RunState dataclass | DONE (`9de17c7`). `cinema/runstate.py`. All 9 fields in one place. CheckpointStoreHost protocol deleted (no longer needed). |
| #2 Auto-generated delegate section | DONE (`d8135d7`). `tools/gen_delegates.py` regenerates marker-delimited block. `--check` mode catches drift. |
| #1 Cross-controller integration test | DONE (`00e8f34`). `tests/integration/test_cross_controller.py` -- 10 tests covering the Slice 2 regression class + V1.1 #5 sharing invariant + Phase 2 lifecycle.wait_for_gate behavior. |

### What's explicitly out of V1 / V1.1 scope (deferred)

- Python 3.9 -> 3.10+ venv upgrade (user-side)
- Structured logging conversion (multi-week)
- `PipelineContext` dict-API cleanup (waits for all callers to migrate)
- Unused-import sweep (5 files, Phase 0 follow-up)
- Web-endpoint `lifecycle.signal_gate` calls (UX optimization)
- `_running_cores` cache invalidation hook (operational fix: restart server)
- Pre-commit hook for `gen_delegates --check` (user decision)
- Host-protocol underscore-prefix rename (visual consistency only)

### For the next session picking this up

If V2 ever revives: the V2-applicable contract gaps (approval state semantics, take lineage, behavioral contracts on Phase Protocol) are in `docs/CONTRACTS.md`. Regenerate any V2 handoff doc under the calibration framework rather than editing the existing one.

If V1 continues with polish: §9.3 has 10 OPEN items. Pick by leverage; none block anything.

If a future composition slice is needed: use the V1.1 #1 integration test pattern. Build a `WiredHost` that satisfies the relevant ControllerHost protocols; exercise every cross-controller chain end-to-end; verify under both the AST surface and the behavioral surface. The Slice 2 regression survived 8 commits because only the AST surface was checked.

If a future RunState field is needed: add it to `cinema/runstate.py`'s dataclass, then re-run `python tools/gen_delegates.py` to auto-add the forwarder pair on CinemaPipeline. No manual editing required.

The architecture is in a sustainable place. Mixin -> composition is structurally complete. Run-state ownership is uniform. Cross-controller chains have an integration test. Future development can build on top of standalone controllers (Shot/Review/Checkpoint) + shared RunState + cached PipelineCore without needing to reason about CinemaPipeline as a god class.

Good luck.
