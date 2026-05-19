# Cinema Pipeline — Architecture Refactor Handoff (Round 2)

**Status:** in progress, 37 commits deep on branch `refactor/architecture-cleanup`.
**As of:** end of standalone-controllers slice 1 (commit `42a290f`).
**Last completed:** `PipelineCore` extraction — `CinemaPipeline.__init__` split into long-lived deps + per-run runtime state.
**Author of this doc:** previous chat session, end-of-day handoff.
**Supersedes:** the original handoff (which covered through Phase 6 slice 3). The original is preserved in git history at the parent of `92a0bba`.

This document is the operating manual for continuing the refactor. It is
**not** a summary — it's structured so the next chat can resume work at
max capacity without re-deriving context from commit history.

> **Most important sentence in this doc:** every refactor slice follows
> the same five-step playbook (read → write → re-export → verify with
> identity check → commit). The playbook is at §6. Read it first.

---

## 0. Setup quickstart for the next chat

```bash
cd /Users/hyungkoookkim/Content
git status                          # untracked: docs/, projects/70940580b872/, .venv-py39-backup if upgrade in progress
git log --oneline -10               # HEAD should be 42a290f (PipelineCore extraction)
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
print(f'COMPILE: {ok} ok, {failed} failed')   # expected: 106 ok, 0 failed (count grows as files are added)

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

# 7. cinema/services.py — read-only endpoint helpers
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

> **3.9 venv caveat:** `cinema_pipeline.py`, `cinema/core.py`, `web_server.py`, and `vbench_evaluator.py` use PEP 604 (`X | None`) in function defaults, which py_compile accepts but runtime `import` rejects in 3.9. The smoke above intentionally avoids importing those modules at runtime. Production environment is 3.10+. See §5 issue 1 for the venv-upgrade instructions handed to the user.

---

## 1. What the codebase is

**AI cinema/video generation pipeline.** Takes a topic, generates a 60-second YouTube Shorts video end-to-end (topic → blueprint → script → audio → per-shot gen → assembly → upload → learning).

Two entry points:
- **`main.py:run_autonomous_pipeline`** — CLI / non-interactive. Uses `cinema.pipeline.CinemaPipeline` (the simple driver) for 3 migrated phases + legacy free-functions for the rest.
- **`web_server.py`** → **`cinema_pipeline.CinemaPipeline`** — interactive Flask dashboard with operator review gates, pause/resume, SSE progress streaming. **Now decomposed** into mixins + LifecycleService + PipelineCore (see §3).

User context (from memory profile):
- Solo architect-via-LLM, AuDHD+BPD configuration
- 25y music, 25y psychology, 3y cinema background
- Prefers blunt accurate engagement; no sycophancy, no comparative inflation

---

## 2. Branch state

37 commits ahead of `pre-refactor-baseline`. The most recent block (chronological, oldest first):

```
3b277de  Phase 5 — Phase protocol POC
c63420b  TopicPhase
d1066a3  BlueprintPhase
e554f93  UploadPhase (minimal)
e8e825a  LearningPhase
2955b09  VisionPhase
0006adc  AssemblyPhase
adb540c  AudioPhase
8fc8b4a  driver + main.py migrate (3 phases)

— Phase 6 audio decomposition —
8f9dc22  audio/srt.py            (slice 1)
ffe2e52  audio/music.py          (slice 2)
cf02946  audio/foley.py          (slice 3)
92a0bba  audio/effects.py        (slice 4)
4de520c  audio/voiceover.py + audio/_client.py (slice 5)
ea4bc45  audio/dialogue.py       (slice 6)

— Post-Phase-6 cleanups + Phase 7-10 —
188654f  delete dead llm/router.py + its test
0a7f9b3  delete dead LLMEnsemble.ensemble_quality_vote + EnsembleQualityResult
11596db  .env.example completed (all 18 env vars)
96262ff  tests/ reorg → unit/ (12) + integration/ (3)
4205077  CLAUDE.md architecture preamble (Phase 10 partial)
8f54eb2  domain/ package — 6 project/character/location modules (Phase 8)
d8c1461  migrate 7 phase_b_audio callers + delete phase_b_audio.py
c21bbbb  docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md
bdedd17  web_services.make_progress_callback (Phase 7 partial)

— cinema_pipeline.py migration (Slices A-E) —
e31e266  Slice A: LifecycleService protocol + wired into PipelineContext
4db9b8a  Slice B: ShotControllerMixin
bcd5255  Slice C: ReviewControllerMixin
1387ce3  Slice D: CheckpointStoreMixin
a10b653  Slice E (scoped): LifecycleService adoption in CinemaPipeline
bc98a01  Phase 7 proper: cinema/services.py + read-only endpoint decoupling
362bed9  Slice E proper: KeyframeRenderPhase + MotionRenderPhase (Option B)

— Standalone controllers (slice 1 of 2-3) —
42a290f  PipelineCore extraction — split __init__ into long-lived + runtime
```

**Branch:** `refactor/architecture-cleanup`
**Baseline tag:** `pre-refactor-baseline` (the very first commit, before any refactor work).

---

## 3. Top-level package layout (current)

```
Content/
├── config/                          ← Phase 2 — settings singleton + prompts
│   ├── settings.py
│   ├── __init__.py
│   └── prompts/pipeline_context.md
├── identity/                        ← Phase 3 — face validation domain
│   ├── types.py
│   ├── validator.py
│   └── __init__.py
├── llm/                             ← Phase 4 — LLM domain
│   ├── ensemble.py                  (ensemble_quality_vote deleted)
│   ├── chief_director.py
│   ├── blueprint_director.py
│   ├── style_director.py
│   └── __init__.py                  (no longer exports EnsembleQualityResult)
├── cinema/                          ← Phase 5 + cinema_pipeline migration
│   ├── pipeline.py                  the simple driver (linear, non-interactive)
│   ├── context.py                   PipelineContext + .lifecycle field
│   ├── lifecycle.py                 LifecycleService protocol + Null + Threaded
│   ├── core.py                      PipelineCore dataclass + build_pipeline_core factory
│   ├── services.py                  state_snapshot + checkpoint_info (Phase 7 helpers)
│   ├── checkpoint.py                CheckpointStoreMixin
│   ├── shots/
│   │   ├── controller.py            ShotControllerMixin (12 methods)
│   │   └── __init__.py
│   ├── review/
│   │   ├── controller.py            ReviewControllerMixin (11 methods)
│   │   └── __init__.py
│   └── phases/                      10 Phase classes
│       ├── base.py                  Phase protocol + PhaseResult
│       ├── topic.py
│       ├── blueprint.py
│       ├── generation.py
│       ├── audio.py
│       ├── assembly.py
│       ├── vision.py
│       ├── upload.py
│       ├── learning.py
│       ├── keyframe_render.py       NEW — per-shot keyframe loop as Phase
│       ├── motion_render.py         NEW — per-shot motion loop as Phase
│       └── __init__.py
├── audio/                           ← Phase 6 — 7 focused submodules
│   ├── _client.py                   shared ElevenLabs singleton
│   ├── srt.py
│   ├── music.py
│   ├── effects.py
│   ├── voiceover.py
│   ├── dialogue.py
│   ├── foley.py
│   └── __init__.py
├── domain/                          ← Phase 8 — project/scene/character/location
│   ├── project_manager.py
│   ├── character_manager.py
│   ├── location_manager.py
│   ├── continuity_engine.py
│   ├── scene_decomposer.py
│   ├── dialogue_writer.py
│   └── __init__.py
├── data/                            runtime data (gitignored experiments.db)
├── docs/
│   ├── REFACTOR_HANDOFF.md          this file
│   └── CINEMA_PIPELINE_MIGRATION_DESIGN.md
├── tests/
│   ├── conftest.py                  pytest fixtures + sys.path bootstrap
│   ├── analyze_sweep_results.py     analysis utility (not a test)
│   ├── unit/                        12 files — pure logic + mocks
│   └── integration/                 3 files — exercise real APIs / e2e
└── (root)                           legacy + glue
    ├── cinema_pipeline.py           interactive orchestrator (now mixin-composed)
    ├── web_server.py                Flask app
    ├── web_services.py              make_progress_callback (Phase 7 partial)
    ├── main.py                      CLI entry
    ├── run_example.py
    ├── cleanup.py
    ├── project_manager.py           root re-export shim → domain.project_manager
    ├── character_manager.py         (and 5 more domain shims)
    ├── phase_a_generator.py         legacy module — not yet migrated
    ├── phase_c_assembly.py
    ├── phase_c_ffmpeg.py
    ├── phase_c_vision.py
    ├── phase_d_upload.py
    ├── phase_e_learning.py
    ├── phase_0_topic.py
    └── (per-shot loop deps not yet touched — lip_sync, workflow_selector,
         kling/sora/veo/ltx_native, comfyui_workflow_gen, cost_tracker,
         quality_tracker, vbench_evaluator, coherence_analyzer,
         research_engine, web_research, etc.)
```

**Notably gone:** `phase_b_audio.py` (deleted in commit `d8c1461`).

---

## 4. Invariants (MUST be preserved by every commit)

Each is verified by the §0 smoke block. The "why" tells you what the invariant protects.

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
- Old invariant #7 (`phase_b_audio.client` is an `ElevenLabs` instance) — retired with the file deletion. Successor is invariant #5 (audio._client.client).

**Verification limit on local 3.9 venv:**
- `cinema_pipeline.py`, `cinema/core.py`, `web_server.py`, `vbench_evaluator.py` py_compile in 3.9 but fail at runtime import (PEP 604 in function defaults). Production environment is 3.10+. AST + selective import are the verification strategies for those files until the venv upgrades (see §5 issue 1).

---

## 5. Open issues (flag for future work, not blocking)

Updated from the original handoff. ✅ = resolved this round, ✏️ = updated status, 🔲 = still open.

| # | Issue | Status | Notes |
|---|---|---|---|
| 1 | Python 3.9 vs PEP 604 syntax | 🔲 | User has instructions to upgrade to 3.11 via `brew install python@3.11`. `requirements-frozen-py39.txt` will be the migration snapshot. Until then, AST + selective imports are the verification ceiling for `cinema_pipeline.py` / `web_server.py` / `cinema/core.py` / `vbench_evaluator.py`. |
| 2 | `.env.example` incomplete | ✅ | Resolved in `11596db`. All 18 env vars documented. |
| 3 | `llm/router.py` dead | ✅ | Deleted in `188654f`. |
| 4 | `LLMEnsemble.ensemble_quality_vote` dead | ✅ | Deleted in `0a7f9b3` along with `EnsembleQualityResult`. |
| 5 | `cinema_pipeline.py` god module | ✏️ | Decomposed via Slices A-E + standalone-controllers slice 1. File now 803 lines (was 1,526). Split into ShotControllerMixin + ReviewControllerMixin + CheckpointStoreMixin + LifecycleService + PipelineCore. Slice 2 (standalone ShotController class) and Slice 3 (controller caching in web_server) remain — see §9. |
| 6 | `tests/` reorg into unit/integration | ✅ | Resolved in `96262ff`. |
| 7 | No structured logging | 🔲 | Multi-week, ~100-file `print()` → logger conversion. Still deferred. Phase 10's preamble portion landed in `4205077`. |
| 8 | Lazy imports in `audio/` | ✅ | Resolved in Slices 4-6. All audio submodules use eager top-level imports. `audio/_client.py` is the cycle-free shared dependency. |
| 9 | V2 plugin architecture (cinema_pipeline_v2 path) | N/A | Per user, that path is dead. The V2 source tree still exists at `~/cinema_pipeline_v2/` but is not integrated. |
| 10 | `vertex-ai-key.json` (empty) at repo root | 🔲 | Gitignored. Safe to delete if user confirms it's not used. |
| 11 | Cleanup `PipelineContext` dict-API methods | 🔲 | Still has `__getitem__`/`__setitem__`/`get`/`update`/`keys`/`items`/`values`/`as_dict` for legacy `ctx["foo"]` compat. Per §9.3 item 5 of the original handoff: removable once all callers migrate to `ctx.foo`. No urgency. |
| 12 | Per-test `sys.path.insert` lines now point at the wrong dir | 🔲 | After Phase 9 moved tests into `tests/unit/` and `tests/integration/`, each test's own `sys.path.insert(0, os.path.join(__file__, ".."))` points at `tests/` instead of project root. Harmless because `tests/conftest.py` does it at module-load time first. Polish opportunity. |
| 13 | `_wait_for_gate` doesn't use `lifecycle.wait_for_gate` | 🔲 | Slice E (scoped) adopted LifecycleService but `ReviewControllerMixin._wait_for_gate` still uses the old `self.pause()` + poll pattern. Small follow-on, low leverage, low risk. |

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
- **Remove** the old function definitions. For large blocks, use AST-based extraction via a Python script (this round used the pattern repeatedly — see §7 Pattern J).
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

# Run the §0 smoke block to confirm all 9 invariants still hold
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
- ✅ Per-shot loop becomes testable in isolation (build a fake `shot_generator`)
- ✅ The loop logic is reusable from main.py or scripts
- ❌ The two orchestrators (driver vs CinemaPipeline) don't fully unify
- ✅ Avoids the "gate-phase" hack (a "phase" that does nothing but wait)

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
- **Default value** (`= None`) — annotation expression evaluated at function definition time → `TypeError: unsupported operand type(s) for |`.

Files in this repo with PEP 604 in function defaults that fail to runtime-import on 3.9: `vbench_evaluator.py`, `cinema_pipeline.py`, `web_server.py`, `cinema/core.py` (transitively via vbench_evaluator import). py_compile passes for all of them — the bytecode is fine; only the import-time evaluation fails.

Don't conflate "compiles" with "imports". The §0 smoke test does both for the modules that CAN runtime-import on 3.9; for the others, py_compile + AST inspection are the verification ceiling.

### 8.9 Mixin pattern preserves identity (NEW)

When a method moves from a class body into a mixin: `LegacyClass.method is Mixin.method` evaluates True (the function object is reached via MRO; not copied). This means the identity-check pattern from §6 Step 4 still works on mixin moves.

But: gitnexus_detect_changes flags every moved method as "Modified" because it tracks symbols by **file location**, not Python identity. The "Modified" count after a mixin extraction is the count of moved methods — but `affected_processes` is correctly 0 because the call edges are preserved.

### 8.10 `gitnexus_impact "HIGH" risk` is often a false positive on extractions (NEW)

When extracting a method, gitnexus_impact computes the transitive reach (depth 1 → 2 → 3 callers) and reports the maximum reach as the risk label. For methods called transitively by `run_pipeline` → `generate` → ..., the label becomes HIGH even though only the d=1 callers (which are usually 1-2 internal methods) actually need to be updated.

**Mitigation:** focus on the d=1 list explicitly. If d=1 is all-internal-to-the-file-being-modified AND the slice preserves the import surface (re-export shim or mixin MRO), the HIGH risk label is benign.

### 8.11 Property accessors and mutable references (NEW)

`@property def x(self): return self._core.x` returns the **same object** that `self._core.x` holds, not a copy. So:

- ✅ `self.x.clear()` clears the underlying dict (works through the property)
- ✅ `self.x.append(...)` mutates the underlying list
- ✅ `self.x.frob = "y"` sets an attribute on the underlying instance
- ❌ `self.x = new_value` does NOT work — it tries to set an attribute on the host class, hitting the property's lack of a setter

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

---

## 9. Remaining work — concrete roadmap

### 9.1 Standalone controllers (continuing the post-Slice-E track)

Slice 1 (`42a290f`, PipelineCore extraction) introduced the architectural seam. Two more slices on this track:

**Slice 2 (medium effort):** Extract a standalone `ShotController(core, lifecycle)` class. Today the methods live as `ShotControllerMixin`, which requires `CinemaPipeline.__init__` to set up runtime state (shot_results, failed_shots, etc.). Slice 2 introduces a parallel class that takes core + lifecycle directly, with a thin local runtime-state holder. The mixin stays as a backward-compat shim OR gets deleted.

**Open question to resolve before starting Slice 2:** does the mixin survive as a shim, or does CinemaPipeline switch to composition (`self._shot_ctrl = ShotController(self._core, self.lifecycle)`)? Composition is cleaner but requires CinemaPipeline methods that delegate to the controller — adds ~12 delegate methods.

**Slice 3 (medium effort):** Web server caching. `_running_pipelines` → `_running_cores` keyed by project_id. Per-endpoint controllers are built per-request from a shared core. Real amortization of the heavy service construction.

After Slices 2 and 3, web_server.py's remaining 5 `CinemaPipeline(...)` construction sites can all be replaced with thinner controller construction.

### 9.2 Original workflow doc Phases 7-10 (post-Phase-6)

| Phase | Status |
|---|---|
| 7 — Web service layer | ✏️ Partial. `web_services.py` + `cinema/services.py` + 2 endpoints decoupled. 5 endpoints still need standalone controllers (track 9.1 above). |
| 8 — Domain reorg | ✅ Complete (`8f54eb2`). |
| 9 — Tests reorg | ✅ Complete (`96262ff`). |
| 10 — Structured logging + CLAUDE.md preamble | ✏️ Preamble done (`4205077`). Structured logging deferred — multi-week, ~100-file effort. |

### 9.3 Other follow-ups

| # | Item | Effort | Priority |
|---|---|---|---|
| 1 | Migrate `_wait_for_gate` to `lifecycle.wait_for_gate` | small | low |
| 2 | Python venv upgrade to 3.10+ (env, not code) | user-side | medium |
| 3 | Delete `vertex-ai-key.json` if confirmed unused | trivial | low |
| 4 | Polish: clean up the dead `sys.path.insert` lines in tests/unit/* and tests/integration/* | small | low |
| 5 | Cleanup `PipelineContext` dict-API methods (after all callers migrate to `ctx.X`) | medium | low |
| 6 | Structured logging conversion | weeks | medium |

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

# 4. All §0 invariants still hold (re-run that block)
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

1. **Read §6 (the playbook) before anything else.** Then §0 (smoke test). These two together are 80% of what you need to operate.

2. **Don't skip the identity check** (or its AST equivalent for class moves). It catches the subtle bug where you accidentally redefined a function with slightly different behavior. `assert a is b` >> `assert callable(b)`.

3. **The 3.9 venv constraint is real but not blocking.** py_compile + AST inspection cover ~80% of what runtime tests would. The remaining 20% (does `cinema_pipeline.py` actually start? does `web_server.py` serve requests?) requires the user to run on their production 3.10+ environment.

4. **`PipelineContext` field list is FIXED** from empirical ctx inventory. Adding new fields requires editing `cinema/context.py`. The `lifecycle` field is required for any phase that wants pause/progress capabilities.

5. **The simple driver in `cinema/pipeline.py` is *just* a phase iterator.** Don't add retry/skip/fallback logic to it. Those concerns belong to phases themselves (or to wrapper phases).

6. **The mixin pattern (Pattern G) is the established way to decompose god classes** in this codebase. Don't try to invent a "better" pattern unless you're prepared to defend it against the existing one.

7. **Open design questions in `docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md` §7 are still open.** Three questions about assembly ownership, checkpoint storage contract, and controller caching. If your slice touches any of those, resolve the relevant question first or document the deferral.

8. **The user said "do 1" / "go with b" / "proceed".** Match that energy. Brief options-with-recommendation; let them pick; execute. Don't over-explain.

9. **Update this handoff doc at the end of your session.** Replace the "**As of:**" line, add your new commits to §2, update §5 issues, update §9 roadmap. The next chat reads this doc cold.

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

# Run smoke (the canonical version is at §0)
PY=/Users/hyungkoookkim/Content/.venv/bin/python
cd /Users/hyungkoookkim/Content && $PY -c "...§0 block..."

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

## 15. End of handoff

If you're a chat picking this up: welcome.

1. Run §0's smoke test first. Confirm 9 invariants hold.
2. Read §6 (the playbook) and §10 (user prefs).
3. Pick a slice from §9. Standalone-controllers Slice 2 is the highest-leverage next step.
4. Brief the user on your scope before starting — present options + recommendation.
5. Make exactly one commit per slice. Verify with §6 step 4.
6. Update this doc at the end of your session.

If anything in this doc is unclear, the commit history (especially the verbose messages on `42a290f`, `362bed9`, `a10b653`, `e31e266`, `c21bbbb`, `8f54eb2`, `d8c1461`) is the next source of truth. Each commit message explains exactly what was done and why.

The architecture is in a sustainable place. None of the remaining items is BLOCKING. They're all incremental improvements. Don't rush.

Good luck.
