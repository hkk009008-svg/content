# HANDOFF - coordinator - 2026-06-16 relay-plan route

READ FIRST AS coordinator or any live seat resuming the relay-plan cycle. Trust
git, mailbox events, and `docs/REMEDIATION-INVENTORY.md` over this prose if
they diverge.

## Correction

This artifact records the coordinator route and restart state only. It does not
claim that spawned Codex subagents are live protocol seats, and it does not
claim that the four live seats completed handoffs. Subagent notes produced
during this coordinator turn were advisory scratch only.

The real live-seat protocol work remains for `director`, `operator`,
`director2`, and `operator2` to read/consume their mailbox and publish their
own seat-owned status or handoff artifacts.

## Coordinator Baseline

Coordinator started the user-requested relay-plan cycle from live evidence at
HEAD:

```text
afdc2bb4 coord(status): operator relay ack
d6857582 coord(status): operator2 relay ack
5cdd902a docs(protocol): codify rotating planning relay
0e14f3ad coord(relay): director2 ack test drive
d19c7e72 coord(relay): director ack test drive
```

Fresh proof bundle before routing:

```text
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
HEAD afdc2bb4 coord(status): operator relay ack
vs origin/main: 2 ahead, 0 behind
ALL-SCOPE EVENTS: 202
Wave 2 gate: MET counts={'verified': 30}; selector tail: 71 passed

$ .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: MET counts={'verified': 30}; PRODUCT ORACLE: logs/product-oracle-wave2.json; selector tail: 71 passed

$ .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK

$ find coordination/locks -maxdepth 1 -type f -print
coordination/locks/.gitkeep
```

Coordinator sent the binding route:

- `coordination/mailbox/sent/2026-06-16T04-19-21Z-coordinator-to-all-coordination.md`

Coordinator did not consume any cursor. No production code, lock, push,
inventory transition, pod spend, or paid API spend happened in this relay-plan
cycle.

## Routed Unit

Wave 2 is closed by executable gate evidence. The next unit is a two-track
Wave-3 planning board:

1. Pair-A capability track: Wave-3 realism / dual-character binding, anchored in
   `docs/superpowers/plans/2026-06-15-dual-char-attn-mask-binding.md`.
2. Pair-B offline hardening track: deferred checkpoint rows outside Wave 2
   close scope: `ckpt-nan-json-token`, `ckpt-stage-notrestored`, and
   `ckpt-sceneclips-dead`.

Do not start implementation, pod work, paid APIs, lock claims, inventory
transitions, or push from this handoff alone.

## Live-Seat Work Still Owed

### director

Read/consume the coordinator route and any relay ack still unread. Own the
Pair-A Wave-3 realism planning decision. Produce a director-owned mailbox
status or handoff artifact that decides whether the next proposal is pure Route
A, Route B sooner, or a Route-A plus masked-man-LoRA hybrid.

The artifact must name prerequisites and blockers: pod started, ComfyUI gateway
up, explicit user authorization for pod/render spend, fresh seed to avoid cached
false-fail, 1344x768 masks, and no paid/pod burn without explicit user OK.

### operator

Read/consume the coordinator route. Cold-review Pair-A planning readiness, not
implementation. If `director` publishes a Wave-3 realism planning artifact,
review that artifact for evidence coverage, route clarity, explicit
prerequisites, and hard no-spend boundaries. Do not run Lane V on nonexistent
code.

### director2

Read/consume the coordinator route and any relay ack still unread. Own the
Pair-B offline checkpoint planning track. Publish a director2-owned status or
handoff artifact recommending whether to open these three rows as a small
offline Wave-3 hardening batch or keep them deferred:

1. `ckpt-nan-json-token`
2. `ckpt-stage-notrestored`
3. `ckpt-sceneclips-dead`

If opening them, propose row order and whether a small Wave-3 checkpoint-stub
addendum is required before implementation.

### operator2

Read/consume the coordinator route. Cold-review Pair-B deferred-row planning
readiness, not implementation. Stand by until `director2` publishes the
checkpoint mini-batch plan or sends a verify request for a landed diff.

## Coordinator Next Trigger

Coordinator should wait for the real live-seat artifacts to land, then
reconcile once. The next coordinator event should not claim live-seat completion
until the actual seats have produced mailbox/status/handoff artifacts.

Push remains user-gated. At the start of the next coordinator turn, rerun:

```text
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
env -u GIT_INDEX_FILE git log --oneline -5
.venv/bin/python scripts/wave_gate_check.py 2
.venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE git status --short
```
