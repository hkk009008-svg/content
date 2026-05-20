# V1 Pipeline Contracts

Behavioral contracts that aren't enforced by code but ARE relied on by
the surrounding orchestration. Documented here so the next session
inherits explicit invariants instead of having to derive them by
reading commit history.

Three contracts:

1. **Phase Protocol** -- what `phase.run(ctx)` promises and what callers
   can assume about `PhaseResult.ok`.
2. **Approval State Model** -- the implicit state machine encoded in
   `shot["plan_status"]` + `shot["approved_*_take_id"]`.
3. **Take Versioning Lineage** -- how `take_id` + `source_take_id`
   reference structures the take graph, and what's invariant about
   traversal.

The relevant code is in `cinema/phases/base.py`, `cinema/review/controller.py`,
`domain/project_manager.py`, and `cinema/shots/controller.py`.

---

## 1. Phase Protocol behavioral contracts

The structural contract is `cinema/phases/base.py`:

```python
@runtime_checkable
class Phase(Protocol):
    name: str
    def run(self, ctx: "PipelineContext") -> PhaseResult: ...

@dataclass
class PhaseResult:
    ok: bool
    message: str = ""
    elapsed_s: float = 0.0
```

The behavioral contract is everything that's NOT in the structural
contract but is relied on by callers.

### 1.1 `ok` semantics

`PhaseResult.ok` is the SOLE gate-keeping signal for the orchestrator
(per `cinema/phases/base.py` module docstring). The orchestrator
decides whether to continue, skip, retry, or abort based on `ok`.

- `ok=True` means: the phase advanced the pipeline successfully. The
  next phase MAY run with the mutated ctx.
- `ok=False` means: the phase did not advance the pipeline. The
  orchestrator MAY surface this to the operator and MAY retry.

### 1.2 Monotonicity (NOT monotonic in general)

`ok=True` is NOT monotonic. Re-running the same phase on the same ctx
can return `ok=False` if external state changed (a file got deleted,
an API quota was hit, a project mutation invalidated a precondition).

Phases are not required to be idempotent. Some are; some aren't.

Examples of non-idempotency in the current codebase:

- `KeyframeRenderPhase.run` skips shots that already have an
  `approved_keyframe_take_id`, but generates fresh takes for the rest.
  Two consecutive runs produce DIFFERENT take_ids in the kept-takes
  collection.
- `AudioPhase.run` writes to `audio_path`. Re-running overwrites the
  file.
- `AssemblyPhase.run` writes the final video. Re-running overwrites.

Callers MUST NOT assume that two runs with the same ctx produce
identical effects. They MAY assume that two runs with the same ctx
produce results in the same equivalence class (e.g., a valid keyframe
for the shot).

### 1.3 Partial-failure convention (KeyframeRenderPhase, MotionRenderPhase)

`KeyframeRenderPhase.run` returns `ok=True` even when some individual
shots failed -- it reports per-shot failures via the `on_failure`
callback but does not gate the overall result on them. The deliberate
semantics: operator can rework failed shots from the review UI; the
pipeline shouldn't abort the run because one shot didn't generate.

The `message` field encodes the per-shot count:

```
"keyframes: 12 new, 3 pre-approved, 2 failed"
```

`ok=False` for these phases is reserved for cancellation OR catastrophic
failures (shot_generator is None, project is None, etc.) -- conditions
where NO progress is possible.

`MotionRenderPhase.run` follows the same convention.

Other phases (`AudioPhase`, `AssemblyPhase`, etc.) treat ANY failure as
`ok=False`. The convention is per-phase, not protocol-wide.

### 1.4 Cancellation contract

Phases MUST poll `ctx.lifecycle.is_cancelled()` at safe points and
return `ok=False` with a "cancelled" message if cancellation is
observed.

"Safe points" = boundaries between sub-units of work that can be
discarded without leaving partial state on disk. For the render phases,
that's between shots (not in the middle of a single shot's API call).

The orchestrator does NOT force cancellation between phases. Phases
cooperate.

`ctx.lifecycle.check_pause()` is the dual: at a pause-safe point, the
phase calls check_pause to block if paused. It returns when unpaused
or cancelled; the phase then re-checks `is_cancelled()` to decide
whether to proceed.

### 1.5 Progress contract

Phases MAY call `ctx.lifecycle.report_progress(stage, detail, percent, **kwargs)`
zero or more times during `run`. The contract:

- `stage` is the phase's `name` attribute (or a sub-stage name like
  "KEYFRAME_READY" within a render phase).
- `percent` ∈ [0, 100] or -1 (meaning "indeterminate / streaming").
- `kwargs` carry phase-specific event data (scene_id, shot_id, take_id,
  etc.).
- The callback may block briefly (SSE delivery, file write); phases
  must not assume it's instant.

The orchestrator does NOT inject progress events -- if a phase wants
to be visible to operators, it has to emit. Silent phases appear in
the SSE stream only via the orchestrator's start/end events.

### 1.6 Ctx mutation contract

Phases mutate `ctx` (a `PipelineContext` dataclass with declared fields
+ a dict-compat layer). Writes are persisted to subsequent phases.

Rules:

- A phase MAY write any field. There is no enforced read-only set.
- A phase SHOULD NOT delete fields (no `del ctx.X`). The dataclass
  supports it but downstream phases assume fields exist.
- A phase MAY add new ad-hoc fields via `ctx["foo"] = ...` (the
  setattr fallback). These won't round-trip through `as_dict()` but
  are accessible to subsequent phases. Avoid this -- declare new
  fields in `cinema/context.py` instead.
- Phases MUST NOT swap `ctx` for a different instance (no `ctx = new_ctx`)
  -- that's a local-variable rebinding that doesn't propagate. Mutate
  in place.

### 1.7 What the protocol explicitly DOES NOT include

The base.py module docstring is explicit: "Resist adding optional
methods (`validate()`, `cleanup()`, ...) until a second phase needs
them. Two callers makes an abstraction; one is speculative."

So far, no phase needs validate() or cleanup(). If one does, add it
to the Protocol and document the semantics here.

---

## 2. Approval state model

The pipeline has three operator-driven approval gates:

| Gate | Predicate | Driver |
|------|-----------|--------|
| `PLAN_REVIEW` | All shots have `plan_status == "approved"` | `approve_shot_plan` endpoint |
| `KEYFRAME_REVIEW` | All shots have `approved_keyframe_take_id != ""` | `approve_take(kind="keyframe")` endpoint |
| `REVIEW` | All shots have `approved_final_take_id != ""` | `approve_take(kind="final")` endpoint |

The state lives in the shot dict. There is no separate "approval log."
The current state IS the approval log -- you can reconstruct who-
approved-what only by inspecting project file history (git, if the
project is versioned; otherwise unrecoverable).

### 2.1 Shot fields that encode approval

```python
{
    "id": "shot_...",
    "plan_status": "pending" | "approved" | "rejected",
    "plan_rejection_reason": "<text>",  # set only when rejected
    "approved_keyframe_take_id": "" | "take_...",
    "approved_motion_take_id": "" | "take_...",  # derived from approved_final
    "approved_final_take_id": "" | "take_...",
    # ... plus the takes themselves under keyframe_takes / motion_takes / postprocess_variants
}
```

### 2.2 State transitions

```
                                    pending
                                       |
                                       | approve_shot_plan(approved=True)
                                       v
                                    approved        <----+
                                       |                 |
                                       | (sets           | approve_shot_plan(approved=True) again
                                       |  plan_status)   | (re-approves after fixing)
                                       v                 |
                                    rejected ------------+
                                       |
                                       ^
                                       | approve_shot_plan(approved=False, reason=...)
```

There is NO un-approve transition for keyframe or final. Once
`approved_keyframe_take_id` is set, the only way to "change" the
approved keyframe is to call `approve_take(another_take_id, "keyframe")`
which overwrites the field.

The plan_status DOES support re-approval (a rejected plan can be
approved again).

### 2.3 Approval authority

The only callers of `approve_shot_plan` and `approve_take` are the
web_server endpoints. No machine-driven approval. No bulk-approve
helper.

Hypothetically: an LLM could call these endpoints to auto-approve --
but no code currently does.

### 2.4 Persistence

All approval writes go through `mutate_project(project_id, mutator)`
which:

1. Acquires the project file lock (`ProjectLockError` if held).
2. Re-reads the project from disk (`load_project`).
3. Applies the mutator function.
4. Atomically writes the result back (temp file + os.replace).
5. Releases the lock.

So approval is durable across server restarts -- the next run reads
the same project file and sees the approval.

There is no in-memory-only approval state; everything goes to disk.

### 2.5 What the model does NOT encode

- **Who approved**: no operator identity. If multiple users have
  access to the same project, you can't tell who clicked which
  button.
- **When approved**: no timestamp. The mutation's modification time
  on the project file is the only proxy.
- **Approval rationale**: only rejection has a `plan_rejection_reason`
  field. Approvals don't capture why.
- **Approval history**: no log of previous approvals/rejections.
  If a shot is rejected then approved, the rejection_reason is
  cleared and there's no record.

These would be useful for audit + multi-user scenarios but aren't
currently in scope. Filed as a V2-critique-aligned future enhancement.

---

## 3. Take versioning lineage

Every generated artifact (keyframe image, motion video, postprocess
variant) is a "take" stored in the shot dict. Takes have stable IDs
and a parent reference, forming a lineage tree per shot.

### 3.1 Take shape

From `domain/project_manager.py:make_take`:

```python
{
    "id": "take_<random>",
    "kind": "keyframe" | "motion" | "postprocess",
    "path": "<filesystem path>",
    "source_take_id": "" | "take_<parent>",
    "status": "generated",
    "created_at": "<ISO timestamp>",
    "metadata": { ... kind-specific ... },
}
```

### 3.2 Where takes live

Each shot has three take collections:

```python
shot = {
    "id": "shot_X",
    "keyframe_takes": [take, take, ...],
    "motion_takes": [take, ...],
    "postprocess_variants": [take, ...],
    "approved_keyframe_take_id": "",
    "approved_motion_take_id": "",
    "approved_final_take_id": "",
}
```

Takes are appended in generation order. There's no explicit
versioning beyond the array index.

### 3.3 Lineage edges

`source_take_id` is the only inter-take reference. It's a UNIDIRECTIONAL
parent pointer:

- Root takes (no parent): empty `source_take_id` ("").
- Derived takes: `source_take_id` references the take that this one
  was generated from.

Typical lineages:

```
keyframe_take_1 (root)              -- raw generation
   |
   v
motion_take_1 (source=kf_1)         -- motion from approved keyframe
   |
   v
postprocess_variants[0] (source=m_1)   -- e.g., color_grade applied
   |
   v
postprocess_variants[1] (source=pp[0])   -- e.g., upscale applied to that
```

Multiple derived takes can share a parent (operator generates 3
postprocess variants from the same motion take).

### 3.4 Traversal invariants

These are invariants of the current codebase, not constraints enforced
by the project schema:

- **Same-shot only**: `source_take_id` always references a take WITHIN
  the same shot. There's no cross-shot lineage. Verified in
  `ShotController._find_take` -- searches only the current shot's
  collections.
- **Acyclic**: take A's `source_take_id` points to take B which was
  created BEFORE A. The generation timestamp (created_at) gives the
  ordering. No code generates cycles, but nothing enforces this beyond
  convention.
- **Dangling references possible**: if a take is deleted (manually or
  by cleanup), descendants' `source_take_id` becomes a dangling pointer.
  `_find_take` returns `None` for missing parents; callers handle it.
- **Lineage tree, not DAG**: each take has at most one parent. There's
  no merge operation.

### 3.5 Approved-take indirection

The shot's `approved_*_take_id` fields reference takes in the
appropriate collection:

- `approved_keyframe_take_id` -> must be in `keyframe_takes`
- `approved_final_take_id` -> can be in `motion_takes` OR
  `postprocess_variants`
- `approved_motion_take_id` -> the closest `motion_takes` ancestor
  of `approved_final_take_id`, resolved by `_resolve_motion_source`
  in `ReviewController.approve_take`

The resolution algorithm walks the lineage backwards from the approved
final take, looking for the first ancestor that lives in
`motion_takes`. Used during assembly to find the underlying motion
asset.

### 3.6 What lineage DOESN'T capture

- **Generation cost**: each take is a separate API call (Kling, Sora,
  etc.), but the cost isn't recorded on the take itself. CostTracker
  records per-call costs but isn't linked to take_id.
- **Quality scores**: identity_score is in `metadata`, but other
  scores (motion smoothness, coherence, vbench) aren't. They live in
  `diagnostics` (added by `diagnose_clip`) which is per-shot, not
  per-take.
- **User intent**: the metadata captures generation params but not
  WHY the operator generated this particular variant. No comment
  field on takes.

These would inform a future "show me why this final take was approved"
audit feature.

---

## Document maintenance

When any of these contracts changes, update both this doc AND the
relevant module docstring. REFACTOR_HANDOFF.md §4 (invariants) is the
mechanical-verification list; this doc is the prose contract that
explains the semantics behind those invariants.
