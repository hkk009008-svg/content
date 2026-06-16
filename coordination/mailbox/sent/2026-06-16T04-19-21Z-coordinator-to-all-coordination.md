# Coordinator → All: relay-plan: Wave 3 planning board and all-seat handoff

**When:** 2026-06-16T04:19:21Z · **From:** coordinator (online)

Coordinator starts the user-requested relay-plan cycle from live evidence at HEAD `afdc2bb4 coord(status): operator relay ack`.

Coordinator is unpinned; no coordinator cursor was consumed. This event is a planning/task-board route, not a production change, verification verdict, lock claim, push, pod spend, paid-API spend, or inventory status transition.

## Baseline

```text
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2
HEAD afdc2bb4 coord(status): operator relay ack
vs origin/main: 2 ahead, 0 behind
ALL-SCOPE EVENTS: 202
Wave 2 gate: MET counts={'verified': 30}; selector tail: 71 passed
peer heartbeats: director/director2 stale at 5cdd902a; operator online at afdc2bb4; operator2 online at d6857582

$ env -u GIT_INDEX_FILE git log --oneline -5
afdc2bb4 coord(status): operator relay ack
d6857582 coord(status): operator2 relay ack
5cdd902a docs(protocol): codify rotating planning relay
0e14f3ad coord(relay): director2 ack test drive
d19c7e72 coord(relay): director ack test drive

$ .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: MET counts={'verified': 30}; PRODUCT ORACLE: logs/product-oracle-wave2.json; selector tail: 71 passed

$ .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK

$ find coordination/locks -maxdepth 1 -type f -print
coordination/locks/.gitkeep
```

## Why this route

Wave 2 is closed by executable gate evidence. The next unit is not another Wave 2 fix. It is a unit-planning relay for what to do next:

1. Capability track: Wave-3 realism / dual-character binding, anchored in `docs/superpowers/plans/2026-06-15-dual-char-attn-mask-binding.md`.
2. Offline hardening track: deferred rows currently outside Wave 2 close scope:
   `ckpt-nan-json-token`, `ckpt-sceneclips-dead`, `ckpt-stage-notrestored`, and `identity-arcface-embselect`.

Do not start implementation, pod work, paid APIs, or lock-claim side effects from this event alone. The user asked for a plan and all-seat handoff. The output owed by each seat is a handoff-ready plan/status artifact or mailbox status, not a production fix.

## Seat assignments

### director (Pair-A director)

Task: own the Pair-A capability planning decision for Wave-3 realism.

Read:
- `docs/superpowers/plans/2026-06-15-dual-char-attn-mask-binding.md`
- `docs/HANDOFF-operator-2026-06-15-pairA-wave2-open-idle-pod-up-adr024-done.md` lines about pod state and Route A
- `.agents/skills/ai-video-gen/SKILL.md`
- `.agents/skills/comfyui-mastery/SKILL.md` before judging ComfyUI graph route shape

Expected output:
- consume/read this event and the remaining relay ack if unread;
- produce a handoff/status artifact that answers: Route A first, Route B sooner, or Route-A+masked-man-LoRA hybrid?
- name prerequisites and blockers: pod STARTED, ComfyUI UP, user spend authorization, no paid burn without explicit user OK;
- if proposing code/driver work, make it an R-BRIEF or pre-brief only; no production implementation in this planning relay.

Allowed write set for this relay: director-owned handoff/status/mailbox docs only. No locks, no push, no pod/API spend.

### operator (Pair-A operator)

Task: cold review Pair-A planning readiness, not implementation.

Expected output:
- consume/read this event and any relay ack still unread;
- produce a handoff/status artifact stating whether Pair-A has a concrete verify target yet;
- if director posts a Wave-3 realism planning artifact in this relay, review it for evidence coverage and no-spend boundary; otherwise no-op evidence is sufficient;
- do not run pod, paid APIs, or Lane V on nonexistent code.

Allowed write set for this relay: operator-owned handoff/status/mailbox docs only.

### director2 (Pair-B director)

Task: own the offline hardening planning track for deferred Pair-B checkpoint rows.

Rows to triage from `docs/REMEDIATION-INVENTORY.md`:
- `ckpt-nan-json-token` (Pair-B, defer/open, MINOR)
- `ckpt-sceneclips-dead` (Pair-B, defer/open, MINOR)
- `ckpt-stage-notrestored` (Pair-B, defer/open, MINOR)

Expected output:
- consume/read this event;
- produce a handoff/status artifact recommending whether to open these as a small offline Wave-3 hardening batch or keep deferred;
- if opening, propose row order and whether a Wave-3 stub-contract addendum is needed before implementation;
- no implementation in this planning relay.

Allowed write set for this relay: director2-owned handoff/status/mailbox docs only. No locks, no push, no pod/API spend.

### operator2 (Pair-B operator)

Task: cold review Pair-B deferred-row planning readiness, not implementation.

Expected output:
- consume/read this event;
- produce a handoff/status artifact stating whether director2's proposed checkpoint mini-batch has enough evidence for later Lane V;
- if director2 has not posted the plan yet, no-op/standby evidence is sufficient;
- do not verify nonexistent code.

Allowed write set for this relay: operator2-owned handoff/status/mailbox docs only.

## Coordinator follow-up

Coordinator will reconcile after all four seat handoffs/status artifacts land or after the user directs a narrower path. Coordinator should not duplicate this route unless new evidence changes the board.

Push remains user-gated. Current branch is ahead of origin by local relay/status commits; do not push without explicit user authorization.

Cursor at send: unknown
