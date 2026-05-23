# Cinema Pipeline — Interactive Orchestrator Migration Design

> **⚠️ SUPERSEDED — the "two orchestrators" problem this doc was designed
> to solve was resolved by the 2026-05-23 pivot via deletion, not
> migration.** The CLI orchestrator (`main.py:run_autonomous_pipeline`)
> and its phase wrappers (`cinema/phases/{blueprint,generation,audio,assembly,vision}.py`)
> were deleted entirely. The interactive `cinema_pipeline.py:CinemaPipeline`
> is now the sole entry point. There is no longer a migration to do.
>
> **Canonical current architecture lives in `/ARCHITECTURE.md` at repo root**
> (the prior `HANDOFF.md` pointer was archived to `docs/archive/` on
> 2026-05-24). Read this doc only for historical context on the design
> alternatives considered before the pivot.

---

**Status:** design only. No code changes in this commit.
**Predecessor:** REFACTOR_HANDOFF.md §13 tip 1 and §9.3 item 1 explicitly require a
design doc before any migration of `cinema_pipeline.py` begins.
**Audience:** the next chat session that picks up Phase 7.

This doc fixes the architecture decisions so an executor can do the work
slice-by-slice without re-deriving the design under time pressure.

---

## 1. What this is about

The repo has **two** pipeline orchestrators today, occupying opposite
ends of the abstraction spectrum:

| Orchestrator | File | LOC | Concerns |
|---|---|---|---|
| `cinema.pipeline.CinemaPipeline` (the driver) | `cinema/pipeline.py` | 130 | linear `for phase in phases: phase.run(ctx)` |
| `cinema_pipeline.CinemaPipeline` (the god module) | `cinema_pipeline.py` | 1,526 | linear flow + pause/resume + operator review gates + per-shot/per-take state machine + SSE progress + checkpoint-to-disk + correction workflow |

The driver covers 8 phases and is fully wired into `main.py:run_autonomous_pipeline`
(non-interactive CLI). The god module is what `web_server.py` instantiates 7
times for the interactive dashboard. Both need to exist; the question is
how to reorganize the god module's 1,526 lines so its concerns are
addressable in isolation, not entangled in one class.

---

## 2. What the god module actually contains

Method inventory (line numbers as of `d8c1461`):

**Lifecycle / control plane** (~80 LOC)
- `__init__`, `_default_progress` — construction + default progress sink
- `cancel`, `pause`, `resume`, `_check_pause` — operator-initiated lifecycle control
- `get_state` — JSON-serializable snapshot for the web UI

**Checkpoint persistence** (~80 LOC)
- `_checkpoint_path`, `_save_checkpoint`, `_load_checkpoint`, `_clear_checkpoint`
- `has_checkpoint`, `resume_info`, `_restore_from_checkpoint`

**Per-shot helpers** (~120 LOC)
- `_all_shots`, `_find_shot`, `_find_take`, `_latest_take`, `_resolve_take_path`,
  `_candidate_take`, `_take_output_path`, `_mutate_shot`, `_record_diagnostic`,
  `_rebuild_review_clips`

**Operator review gates** (~150 LOC)
- `_project_gate_status`, `_gate_satisfied`, `_wait_for_gate`
- `approve_shot_plan(shot_id, approved, reason)`
- `approve_take(shot_id, take_id, approval_kind)`
- `proceed_to_assembly()`

**Per-shot generation + correction state machine** (~600 LOC — the bulk)
- `generate_keyframe_take(scene_id, shot_id)`
- `generate_motion_take(scene_id, shot_id)`
- `regenerate_shot(scene_id, shot_id)`
- `diagnose_clip(shot_id, take_id)`
- `apply_correction(shot_id, action, params, take_id)`
- `generate_scene_preview(scene_id)`

**Audio + assembly** (~250 LOC)
- `_ensure_scene_audio`, `_ensure_bgm`, `_build_scene_packages`
- `assemble_approved_takes`, `_assemble_final`, `_frame_interpolate`, `_upscale_video`

**Top-level workflow** (~150 LOC)
- `generate(resume=False)` — the main entry that ties everything together

**Module-level**
- `run_cinema_pipeline(project_id)` — CLI entry that constructs + calls `.generate()`
- `_build_transition_prompt(from_mood, to_mood)` — pure helper

That's the surface area to decompose.

---

## 3. The four hard architectural questions

The driver was designed for non-interactive sequential flow. The god
module needs four things the driver doesn't model. Each is a design
decision that has to land before any code moves.

### 3.1 Pause/resume — where does the flag live?

Today: `self._paused: bool` flag, polled inside long-running operations
via `_check_pause()`, which blocks on a condition variable.

The driver has no concept of pause. Options:

| Option | Pros | Cons |
|---|---|---|
| **A.** Each Phase polls a cancel/pause token passed via `ctx` | Phases stay protocol-conformant; the driver doesn't need to know about pause | Every long-running phase has to remember to poll |
| **B.** Driver coordinates pause at phase boundaries | Driver stays small; no per-phase polling | Pause can't interrupt mid-phase work (e.g., 3-minute video generation) |
| **C.** Inject a `LifecycleService` interface that phases use voluntarily | Clean separation; phases that don't need pause don't pay for it | One more thing for phase authors to know about |

**Recommendation: C.** Add a `LifecycleService` protocol with `is_cancelled()`,
`check_pause()`, `report_progress(stage, detail, percent)`. The existing
`progress_callback` parameter becomes one method on this service. Inject
it via `PipelineContext.lifecycle: LifecycleService | None`. Non-interactive
callers (main.py) get a no-op default that never blocks; the web server
provides a real implementation backed by `threading.Event`.

### 3.2 Operator review gates — driver-level or phase-level?

Today: `_wait_for_gate(gate_name)` polls a project state flag until the
operator sets it (via `approve_shot_plan` / `approve_take`).

| Option | Pros | Cons |
|---|---|---|
| **A.** Phases return `PhaseResult(ok=False, requires_gate=...)` and the driver loops them | Gates are first-class in the Phase protocol; driver is the source of truth | Phases that need fine-grained gates (per-shot) become awkward |
| **B.** Phases call `lifecycle.wait_for_gate(name)` directly | No protocol changes; per-shot gates work naturally | The driver loses visibility into gate state |
| **C.** Split into pre-gate / generate / post-gate phases | Maps cleanly to the existing 8-phase shape | Adds 3 more phases per gated stage; doubles the phase count |

**Recommendation: B.** Gates are control-plane, not data-plane. Extending
the Phase protocol to model them would force every non-interactive caller
(main.py) to also handle them. Keep `wait_for_gate` as a service-layer
concern. Web-server phases call it; CLI phases inject a service that auto-approves.

### 3.3 Per-shot/per-take state machine — phase or sub-phase?

Today: `generate_keyframe_take` and `generate_motion_take` are operator-callable
methods that work on **one shot at a time**. The web UI lets the operator
iterate: pick a shot, generate a take, review, approve or regenerate.

This isn't a phase — it's an operator-driven loop with no fixed exit.
The driver's "iterate phases sequentially" model doesn't fit.

**Recommendation: extract a separate `ShotController`.** It's not a Phase.
It's a peer abstraction:

```
class ShotController:
    """Per-shot generation + correction state machine.

    Stateless w.r.t. the driver. The web server invokes ShotController
    methods in response to operator clicks; the driver invokes them
    in batch during GenerationPhase for non-interactive runs.
    """
    def generate_keyframe(self, scene_id, shot_id) -> Take: ...
    def generate_motion(self, scene_id, shot_id) -> Take: ...
    def regenerate(self, scene_id, shot_id) -> Take: ...
    def diagnose(self, shot_id, take_id) -> Diagnosis: ...
    def apply_correction(self, shot_id, action, params, take_id) -> Take: ...
```

`GenerationPhase` (the existing one in `cinema/phases/generation.py`)
becomes a thin wrapper: for each scene/shot, call `ShotController.generate_keyframe`
then `.generate_motion`, then auto-approve. Same outcome as the legacy
non-interactive path. Web server uses the same `ShotController` but
calls methods on-demand.

### 3.4 SSE progress streaming — where do events originate?

Today: `progress_callback(stage, detail, percent, scene_idx)` is passed
into `__init__` and called throughout the class. The web server attaches
a callback that pushes to a per-project SSE queue.

This is already factored well — it's just a callable. The migration
preserves it via the `LifecycleService.report_progress` method (from §3.1).
The web server's SSE queue is upstream of LifecycleService; no
architectural change needed.

---

## 4. Migration plan — 5 slices

Each slice is one commit. Verify with the §0 smoke block from
REFACTOR_HANDOFF.md after each.

### Slice A — Extract `LifecycleService` (smallest, do first)

- New `cinema/lifecycle.py`: `LifecycleService` protocol + `NullLifecycle`
  (no-op) + `ThreadedLifecycle` (Event-backed for the web path).
- Add `PipelineContext.lifecycle: LifecycleService = NullLifecycle()`.
- Update the 8 existing Phase classes to call `ctx.lifecycle.check_pause()`
  before their heavy work (optional; safe to skip on no-op).
- Driver stays unchanged.

Verification: existing smoke test still passes. New: `NullLifecycle()`
can survive a JSON round-trip (it has no state) so checkpoint-restore
keeps working.

### Slice B — Extract `ShotController` from `cinema_pipeline.CinemaPipeline`

- New `cinema/shots/controller.py`: `ShotController` class.
- Move the 6 per-shot/per-take methods (`generate_keyframe_take`,
  `generate_motion_take`, `regenerate_shot`, `diagnose_clip`,
  `apply_correction`, `generate_scene_preview`) + their helpers
  (`_find_shot`, `_find_take`, `_take_output_path`, `_mutate_shot`,
  `_record_diagnostic`).
- The legacy `CinemaPipeline` methods become thin delegates:
  `def generate_keyframe_take(self, ...): return self._shot.generate_keyframe(...)`.
  This preserves the web-server's existing call sites.

Verification: identity-check the 6 method bindings on a `CinemaPipeline`
instance match the `ShotController` methods.

### Slice C — Extract `ReviewController` (operator gates)

- New `cinema/review/controller.py`: `ReviewController` class.
- Move `approve_shot_plan`, `approve_take`, `proceed_to_assembly`,
  `_project_gate_status`, `_gate_satisfied`, `_wait_for_gate`,
  `_rebuild_review_clips`.
- Same delegate pattern as Slice B.

### Slice D — Extract `CheckpointStore` (persistence)

- New `cinema/checkpoint.py`: `CheckpointStore` class.
- Move the 7 checkpoint methods (`_checkpoint_path`, `_save_checkpoint`,
  `_load_checkpoint`, `_clear_checkpoint`, `has_checkpoint`,
  `resume_info`, `_restore_from_checkpoint`).
- The store takes the project_id in its constructor; previously these
  methods read `self.project_id` directly.

### Slice E — Rewrite `CinemaPipeline.generate()` on top of the driver

- The 200-line `generate(resume=False)` method becomes a composition:

```
def generate(self, resume=False):
    ctx = self._build_context(resume)
    driver = cinema.pipeline.CinemaPipeline()
    driver.add_phase(TopicPhase())
    driver.add_phase(BlueprintPhase())
    driver.add_phase(GenerationPhase(shot_controller=self._shots))
    driver.add_phase(AudioPhase())
    driver.add_phase(AssemblyPhase(review_controller=self._review))
    driver.add_phase(UploadPhase())
    driver.add_phase(LearningPhase())
    return driver.run(ctx)
```

- `GenerationPhase` and `AssemblyPhase` accept their controllers via
  constructor; everything else uses the defaults.
- The legacy `_assemble_final`, `_frame_interpolate`, `_upscale_video`
  helpers either move into `AssemblyPhase` or stay as private helpers
  on `CinemaPipeline` (TBD per how cohesive they are).

After Slice E, `cinema_pipeline.py` is mostly a façade — its job is to
construct the right controllers + driver + context for the interactive
flow. Anticipated final size: ~200–300 lines.

---

## 5. Phase 7 dependency map (web_server.py decoupling)

`web_server.py` references `CinemaPipeline` at 7 sites
(all `from cinema_pipeline import CinemaPipeline` followed by either
construction or attribute access). The migration above is a precondition
for the deep web-server decoupling, because today web_server gets a
single class that owns every concern (lifecycle + shots + review +
checkpoint + driver).

After Slices A–E, web_server.py can be rewritten to construct only
what each endpoint needs:

```
# Before
CinemaPipeline(pid).get_state()

# After
StateView(pid).snapshot()  # just reads the project file; no controllers

# Before
CinemaPipeline(pid, progress_callback=cb).generate_keyframe_take(scene_id, shot_id)

# After
controller = ShotController(pid, lifecycle=lifecycle)
controller.generate_keyframe(scene_id, shot_id)
```

This is **Phase 7 proper** and is a follow-on after Slice E lands.

A small, safe **partial** Phase 7 piece that can land before Slices A–E:
extract the `_get_stage_pipeline` and `_make_progress_cb` helpers from
`web_server.py` into a `web/services.py` module so they're reusable and
testable. That is a low-risk move; it can land in this branch as the
companion slice to this design doc.

---

## 6. What this doc is **not**

- Not a deadline. No estimate is given for when Slices A–E land.
- Not a guarantee the partition above is final. The first slice that
  exposes a hidden coupling is allowed to revise this doc.
- Not blocking on Phase 7 to start. Slice A is independent of the web server.

---

## 7. Open questions for the next session

1. Are the `_frame_interpolate` and `_upscale_video` helpers truly
   assembly concerns, or post-generation concerns? If post-generation,
   they belong on `ShotController`, not in AssemblyPhase.
2. Should `CheckpointStore` be storage-agnostic (file system today,
   could be S3 / DB tomorrow), or is filesystem the contract?
3. The web server constructs a fresh `CinemaPipeline` for every API
   call (no sharing). After migration, should controllers be cached
   per project_id? If yes, where?

These are real questions, not rhetorical — the executor of Slice E
should answer them before that slice starts.

---

## 8. Verification expectations per slice

Every slice in this migration must satisfy:

- All existing invariants from REFACTOR_HANDOFF.md §4 still hold.
- For each method moved into a new controller: identity check that
  `LegacyClass.method` and `NewController.method` resolve to the same
  function object via the delegate.
- `web_server.py` imports cleanly after each slice (compile only — the
  local venv is Python 3.9 and web_server uses PEP 604 syntax, so a
  full import requires 3.10+).
- `main.py:run_autonomous_pipeline` continues to work (smoke import).
