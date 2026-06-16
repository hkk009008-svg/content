# Coordinator → All: relay-plan: SEAT_PROTOCOL final implementation-plan review

**When:** 2026-06-16T05:04:09Z · **From:** coordinator (online)

User direct instruction: read `SEAT_PROTOCOL.md`, build from it by taking what works and not taking what does not, then start the relay plan for the final implementation plan.

Coordinator read the file and is starting the coordinator-started Rotating Planning Relay: coordinator -> all four seats -> coordinator. This event is planning evidence only. It is not production implementation, not a verification verdict, not a lock claim, not a push, not pod/API spend, and not an inventory transition.

## Live baseline

```text
HEAD: 30fcb944 coord(protocol): add active mailbox monitor
Origin relation: 4 ahead, 0 behind
Coordinator/all scope: 203 all-time events; coordinator is unpinned, no cursor consumed
Prior latest broadcast: 2026-06-16T04-19-21Z-coordinator-to-all-coordination.md
Receipt split before this event: consumed=0 unread=4 for prior broadcast
Wave 2 gate: MET counts={'verified': 30}; selector tail 71 passed
Smoke: scripts/ci_smoke.py OK; existing advisory only for old verify-addendum kind
Locks: coordination/locks/.gitkeep only
Working tree note: untracked SEAT_PROTOCOL.md exists and is intentionally treated as proposal input, not canonical state
```

## Coordinator synthesis: take what works

Use these `SEAT_PROTOCOL.md` ideas as candidate implementation themes for the final plan:

1. Six-field seat contract: role/env, objective, permissions/autonomy, scope, verification, and done evidence.
2. Live proof bundle before decisions: seat status, recent git, mailbox bodies, gate/smoke evidence, and receipt split.
3. Executable guard emphasis: staged-scope, index hygiene, stale-state refresh, push authorization, coordinator overreach, cursor misuse, and subagent/role boundaries should be checks where feasible, not only prose.
4. Observability layer: mailbox monitor, watchboard-style read-only state, and receipt-split reporting are valuable and already partly landed.
5. Machine-checkable done summary: HEAD, changed files, unread/mailbox delta, verification, push status, blockers, and exact next trigger.
6. Guard-first test plan: a failing/meaningful test or fixture per new guard before hardening behavior.

## Coordinator synthesis: do not take as-is

Do not treat `SEAT_PROTOCOL.md` as a replacement for current repo authority. `AGENTS.md`, `ARCHITECTURE.md`, `docs/protocol/agents/`, `docs/protocol/codex/continuation.md`, `.agents/skills/`, committed mailbox state, and executable scripts remain authoritative.

Do not delete or archive existing per-seat/protocol notes until a relay-reviewed migration proves no information loss and the source-order map is updated.

Do not make all subagents globally read-only. Read-only verifier/specialist subagents stay read-only; explicitly spawned role agents may do bounded seat-authorized work when the parent and protocol allow it.

Do not broaden operator authority into production fixes. Operators own independent verification/status/cursor artifacts and only protocol-approved same-commit side effects; production fixes remain director/lane-owned.

Do not encode model-specific wording like "GPT-5.5 extra thinking" as canonical repo policy. Keep the underlying design principle: compact contracts and executable guards reduce reasoning drift.

Do not downgrade user-visible progress updates in Codex interaction policy. Durable artifacts are preferred for protocol state, but live Codex still keeps the user informed while working.

## Candidate implementation spine for the final plan

The relay should converge on a final implementation plan, likely in this shape:

1. Map current coverage: inventory existing hooks/scripts/docs against S-ROLE/S-OBJ/S-PERM/S-SCOPE/S-VERIFY/S-DONE and guards G1-G8.
2. Design before code: write a reviewed spec under `docs/superpowers/specs/` rather than promoting the untracked root `SEAT_PROTOCOL.md` directly.
3. Build or wire a contract/banner resolver that reports mode plus the six contract fields without taking over authority from `scripts/codex_protocol_model.py`.
4. Build or wire a proof-bundle command that composes existing `seat_status.py`, git log, selected mailbox bodies, gate, smoke, and receipt-split output.
5. Harden guard checks with tests: staged-scope, index hygiene, push authorization, stale-state age, coordinator no-production-write boundary, and cursor misuse.
6. Add a DONE-summary or blocked-handoff emitter that can fact-fill the final evidence fields.
7. Update docs and skills narrowly after tools are real; keep source-order and protocol assembly map coherent.
8. Verify with focused guard tests, `scripts/check_coordination.py`, `scripts/ci_smoke.py`, and only the broader gate/smoke needed by the changed surface.

## Seat relay assignments

### director

Review the proposed adoption boundary and final plan shape for Pair-A/director authority. Decide which `SEAT_PROTOCOL.md` concepts should become director-facing requirements, which should remain coordinator-only, and which conflict with existing director/operator rules.

Expected output: a mailbox/status planning response with KEEP / REJECT / MODIFY items and a recommended implementation sequence. No production implementation. Allowed write set: director-owned planning/status/mailbox artifact only.

### operator

Review the guard and done-summary proposal from a verification perspective. Focus on whether G5/G6/G7/G8 and S-DONE are objectively testable, whether existing hooks/scripts already cover part of them, and what focused tests would make the final plan Lane-V-ready.

Expected output: a mailbox/status planning response naming verifier concerns, missing tests, and acceptance checks. No production implementation. Allowed write set: operator-owned planning/status/mailbox artifact only.

### director2

Review the tooling architecture for implementation: how `seat_banner.py`, `proof_bundle.py`, receipt-split/monitor wiring, and `scripts/codex_protocol_model.py` should relate without duplicating protocol truth.

Expected output: a mailbox/status planning response with recommended module boundaries, build order, and any doc/source-order migration caveats. No production implementation. Allowed write set: director2-owned planning/status/mailbox artifact only.

### operator2

Cold-review the final-plan readiness from Pair-B/operator perspective. Check whether the plan preserves the coordinator prohibition, operator independence, no-push/no-spend defaults, and enough executable evidence for future Lane V.

Expected output: a mailbox/status planning response with GO/NITS/FAIL-on-plan language if useful, plus required verification commands for the eventual implementation. No production implementation. Allowed write set: operator2-owned planning/status/mailbox artifact only.

## Coordinator follow-up

Coordinator will reconcile after all four planning responses land, then produce one consolidated final implementation plan or task board. Do not start code from `SEAT_PROTOCOL.md` alone. Push remains user-gated.

Cursor at send: unknown
