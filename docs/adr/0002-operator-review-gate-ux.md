# ADR-0002: Operator Review Gate UX

**Status:** Proposed
**Date:** 2026-05-23
**Deciders:** repo owner
**Related:** `docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md` §3.2,
`cinema_pipeline.py` (legacy gate methods), `web_server.py` (REST + SSE),
`cinema/lifecycle.py`, planned `ReviewController` extraction

---

## 1. Context

The pipeline pauses four times during a normal run for operator review:

| Gate | Where | Phase % | What the operator does |
|---|---|---|---|
| `PLAN_REVIEW` | `cinema_pipeline.py:703` | 25 | Approve / reject each shot's plan (camera, prompt, character) |
| `KEYFRAME_REVIEW` | `cinema_pipeline.py:735` | 55 | Pick the best keyframe take per shot, regenerate alternates |
| `PERFORMANCE_REVIEW` | `cinema_pipeline.py:776` | 76 | Review performance-capture takes; can be skipped → `PERFORMANCE_SKIPPED_GATE` |
| `REVIEW` (final takes) | `cinema_pipeline.py:815` | 82 | Pick / approve the final video take per shot before assembly |

Today's implementation:

- **Server-side blocking**: `_wait_for_gate(name, message, target_percent)`
  loops on `_gate_satisfied(name)` polling project state. The generation
  thread blocks until satisfied.
- **State storage**: each shot has approval fields
  (`approved_shot_plan`, `approved_keyframe_take_id`,
  `approved_final_take_id`) persisted in `project.json`.
- **Operator API**: REST routes in `web_server.py:1278-1393`
  (`/shots/<id>/approve`, `/shots/<id>/keyframes/<take>/approve`, etc.).
- **Notification**: a single SSE stream per project
  (`web_server.py:1227`) broadcasts `{stage, detail, percent}` events
  including `HEARTBEAT` keepalives every 30s.
- **CLI mode**: `main.py:run_autonomous_pipeline` does **not** hit
  gates today — the legacy CLI path bypasses the god module entirely.
  The migration design plans CLI gates to auto-approve via a no-op
  lifecycle service.

### 1.1 What the migration design has already settled

`docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md` §3.2 chose **Option B**:
gates are a **service-layer concern**, accessed via
`lifecycle.wait_for_gate(name)`. The Phase protocol stays gate-unaware;
the lifecycle service per environment (web vs CLI) decides what
"wait" means. **This ADR does not re-litigate that.** This ADR is
about everything §3.2 did *not* decide: the operator-facing UX and
the wire protocol between the running pipeline and the dashboard.

### 1.2 Forces

| Force | Detail |
|---|---|
| **Long blocks** | A gate can block for hours (operator reviewing 30 shots). The HTTP server, the SSE stream, and the worker thread must all survive that. |
| **Partial approval** | An operator may approve 27/30 shots and stop for the day. The state must be durable and resumable. |
| **Regenerate-and-review** | At `KEYFRAME_REVIEW`, the operator can request a new take. The gate must support **re-entry**: not "approve once and move on" but "stay open until all takes are approved or rejected". |
| **Cancel mid-gate** | The operator can cancel the entire pipeline from inside a gate (`/cancel` route). Cleanup must not corrupt project state. |
| **Multi-tab dashboard** | Two browser tabs both subscribed to SSE may issue conflicting approvals. (Today this is partially handled by `_project_lock_guard`.) |
| **Headless / CLI** | The CLI path must skip gates without code branches in phase logic. |
| **Test ergonomics** | Integration tests should be able to drive gates without spinning a Flask server. |

---

## 2. Decision

Model gates as an **explicit finite-state machine** owned by a
`ReviewController` (already extracted at `cinema_pipeline.py:304-311`,
to be hardened in this ADR). Each gate has these states:

```
              [reject reason]
                   ▲
   ┌──── CLOSED ──┴── PENDING_INPUT ──[approve all]──> SATISFIED
   │                       │
   │                       └──[regenerate request]──> WORKING ──> PENDING_INPUT
   │
   └── CANCELLED  (from operator /cancel)
```

- **State lives in `project.json`** under `gates.<name>` with
  `{state, opened_at, satisfied_at, last_action, blocked_items: [...]}`.
- **The pipeline thread is the only writer** of `state` transitions to
  `WORKING` and `SATISFIED`. The REST layer writes `last_action` and
  per-item approval fields; the pipeline observes those and decides if
  the gate is satisfied.
- **`lifecycle.wait_for_gate(name)`** subscribes to a per-project
  `threading.Event` (set by the REST layer on state-changing actions)
  and re-checks satisfaction. No more polling-sleep loops.
- **SSE emits gate events** as a typed event:
  `{type: "gate", name, state, blocked_items, percent}`.
  Existing `{stage, detail, percent}` events stay untouched for
  backward compatibility.
- **CLI uses an `AutoApprovingLifecycle`** that satisfies any gate
  immediately. No phase code changes.

The granularity stays **per-shot** (today's model) — not per-batch and
not per-phase. Coarser granularity would force re-review of work the
operator already approved.

---

## 3. Options Considered

### Option A: Keep today's polling-flag-in-project-state model

Pipeline thread loops `while not _gate_satisfied(): sleep(2)`. Operator
sets flags via REST.

| Dimension | Assessment |
|---|---|
| Complexity | **Low** — already implemented |
| Latency | Bad — 2s polling interval between approval and pipeline progression |
| Resource use | Wakes the thread every 2s for hours |
| Cancel behavior | Works but feels sluggish |
| Multi-tab consistency | Hand-rolled via `_project_lock_guard` |
| Test ergonomics | Tests must inject project state and wait for the polling tick |

**Pros:** No new code. **Cons:** Polling latency is operator-visible.
Burns thread time. No clean abstraction for CLI.

### Option B: Event-driven callbacks (operator action invokes pipeline directly)

Pipeline registers a callback for each gate. REST route triggers the
callback, which advances the pipeline.

| Dimension | Assessment |
|---|---|
| Complexity | **High** — callbacks live in the Flask thread, race the pipeline thread |
| Latency | Near-zero |
| Resource use | Minimal |
| Cancel behavior | Requires explicit teardown of registered callbacks |
| Multi-tab consistency | Hard — concurrent callbacks need locking the pipeline thread doesn't see |
| Test ergonomics | Tests must simulate the Flask request lifecycle |

**Pros:** Reactive. **Cons:** Mixes web-thread and pipeline-thread
concerns. Hard to reason about when an operator cancels mid-callback.

### Option C: Promise/Future-based (`asyncio.Event` semantics)

`wait_for_gate` returns an awaitable that the pipeline `await`s.

| Dimension | Assessment |
|---|---|
| Complexity | **Medium** — but requires converting the pipeline to async |
| Latency | Near-zero |
| Resource use | Minimal |
| Cancel behavior | Native via `Future.cancel()` |
| Multi-tab consistency | Same as B — needs explicit locks |
| Test ergonomics | Strong if the codebase is async; weak if it isn't |

**Pros:** Best primitive for "wait until something else finishes."
**Cons:** Pipeline is sync today; converting Phase contracts to
async is a multi-month effort. Not commensurate with the problem.

### Option D (recommended): Explicit FSM in `ReviewController` with `threading.Event` wakeup

The model in §2. Each gate is a typed state object. Pipeline thread
waits on a `threading.Event`. REST handlers set the event after
mutating per-item state. The pipeline thread checks the FSM, decides
satisfaction, and either transitions or re-waits.

| Dimension | Assessment |
|---|---|
| Complexity | **Medium** — ~250 LOC of FSM code + tests |
| Latency | Near-zero (event wakeup is microseconds) |
| Resource use | Minimal — thread is parked on `Event.wait()` |
| Cancel behavior | Cancellation sets a separate event; gate states transition to `CANCELLED` cleanly |
| Multi-tab consistency | FSM is the single source of truth; concurrent approvals are serialized by the controller's lock |
| Test ergonomics | Tests instantiate `ReviewController` directly, fire mutations, assert FSM states |

---

## 4. Trade-off Analysis

The choice is really between **A (status quo)** and **D (FSM)**. B is a
worse implementation of the same end goal; C requires async rewrite the
project hasn't committed to.

A is good enough if the user base stays at 1–2 operators and the
pipeline isn't expected to be production-grade. The 2s polling latency
is annoying but not broken.

D is the right answer if:
- multiple operators will eventually use the dashboard simultaneously,
- the test suite needs to cover gate behavior without Flask, or
- the gate semantics need to grow (e.g., conditional gates: "skip
  PERFORMANCE_REVIEW if all shots are landscape").

Given the project is already extracting `ReviewController` in the
migration (see `cinema_pipeline.py:304-311`), D requires only modest
incremental work on top of work that has to happen anyway. Choosing A
means deferring this work indefinitely; choosing D means landing the
FSM as part of the §3.2 service-layer extraction.

### 4.1 What about replacing SSE entirely?

WebSockets are a natural fit for bidirectional gate UX. But SSE is
already in production, works fine for the "server pushes, client never
pushes" shape, and the gate UX described here doesn't need
bidirectional. **Out of scope.** Revisit only if collaborative editing
becomes a feature.

### 4.2 What about gate timeout?

An operator may abandon a session mid-gate. Today's behavior: the
pipeline thread blocks indefinitely until the server restarts.

Decision: **no automatic timeout in v1.** A gate that's been
`PENDING_INPUT` for N minutes is not necessarily abandoned — operators
take breaks. Surface a "gate has been open for 42 minutes" indicator
in the UI; let the human cancel. Auto-timeout adds nuance (was the
work lost? can it resume?) that's better solved with explicit
operator cancel than with a clock.

---

## 5. Consequences

### What becomes easier

- **Testing gate behavior**: integration tests construct a
  `ReviewController` with a mock pipeline thread, fire approvals, and
  assert FSM transitions. No Flask, no SSE, no project file I/O.
- **Adding new gates**: register a new gate name in the FSM, add a REST
  route, done. No new wait-loop code per gate.
- **CLI gate handling**: `AutoApprovingLifecycle` injects a controller
  whose `wait_for_gate` returns immediately with state `SATISFIED`.
  CLI phases don't branch on `is_cli`.
- **Observability**: each FSM transition is a log event. "How long was
  gate X open?" becomes queryable.

### What becomes harder

- **Migration**: the existing polling code (`cinema_pipeline.py:703,
  735, 776, 815`) must be converted to FSM transitions. Risk is real —
  this is the operator-critical path. Land behind a feature flag with
  parallel comparison on a staging project before flipping.
- **Multi-tab approval conflicts** become **explicit** rather than
  invisible. Two tabs approving the same shot will now produce a
  "shot already approved by other tab" UI message instead of a silent
  double-write. That's the right behavior but it surfaces a UX edge
  case operators may not have hit before.

### What we'll need to revisit

- **Gate dependencies.** Today gates are sequential by phase percent.
  If a future feature ("approve sets first, characters second") needs
  cross-gate dependencies, the FSM should model them explicitly rather
  than encoding ordering in phase progress numbers. The percent-based
  ordering is a historical artifact that this ADR consciously preserves
  but flags as fragile.
- **Persistence format.** `project.json` is fine for now. If gate
  history grows large (lots of regenerate cycles), consider moving
  gate event logs to SQLite. Not a v1 concern.
- **Operator notifications.** When a gate opens, the operator may be
  away. Email/Slack/desktop-notification integration is a follow-up;
  the FSM event stream is the natural source.

---

## 6. Action Items

1. [ ] In `cinema/lifecycle.py`, add `LifecycleService.wait_for_gate(name)`
   protocol method and concrete implementations:
   `BlockingLifecycle` (wraps `threading.Event`, used by web),
   `AutoApprovingLifecycle` (used by CLI).
2. [ ] In `cinema/review.py` (new), define the FSM:
   `GateState`, `Gate`, `ReviewController`. Move the existing
   `_review_ctrl` body into this module. Add `transition()` and
   `is_satisfied(gate_name, project_state)` methods.
3. [ ] Replace `cinema_pipeline.py:703,735,776,815` polling calls with
   `lifecycle.wait_for_gate(name)`. Verify by running the existing web
   workflow end-to-end on a staging project.
4. [ ] In `web_server.py`, mutate REST approve/reject routes to call
   `ReviewController.record_approval(...)` which sets the
   `threading.Event` instead of relying on the polling thread to notice.
5. [ ] Emit a new SSE event type `{type: "gate", name, state, blocked_items}`
   on every FSM transition. Keep the existing `{stage, detail, percent}`
   events for backward compatibility.
6. [ ] Add `tests/unit/test_review_controller.py` covering FSM
   transitions: open → pending → satisfied; pending → working → pending;
   any → cancelled.
7. [ ] Add `tests/integration/test_gate_e2e.py` driving the full
   web stack against a staging project (one operator approves all
   shots; verify pipeline advances within 100ms of last approval).
8. [ ] Surface "gate open for N minutes" in the dashboard UI. No
   auto-timeout; operator must cancel explicitly.
9. [ ] Update `docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md` §3.2 to
   reference this ADR as the operational detail behind its
   structural choice.
