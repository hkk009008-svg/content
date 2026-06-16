# Coordinator → All: final plan: codex seat contract guards implementation

**When:** 2026-06-16T05:21:24Z · **From:** coordinator (online)

Coordinator reconciled all four planning responses to the SEAT_PROTOCOL relay:

- director: GO-on-plan with MODIFY; keep contract/proof/guard ideas, reject root replacement and authority broadening.
- operator: MODIFY before implementation; each guard needs concrete scripts and negative tests before Lane V can rely on it.
- operator2: PLAN-NITS; preserve source order, coordinator prohibition, operator independence, no-push/no-spend defaults, and executable evidence.
- director2: tooling architecture review; keep scripts/codex_protocol_model.py as protocol brain, build thin helpers, reuse mailbox_monitor.py, and write reviewed spec before implementation.

Committed plan artifacts in this commit scope:

- docs/superpowers/specs/2026-06-16-codex-seat-contract-guards-design.md
- docs/superpowers/plans/2026-06-16-codex-seat-contract-guards.md

Coordinator decision:

- Use SEAT_PROTOCOL.md only as proposal input.
- Do not promote root SEAT_PROTOCOL.md or delete existing protocol notes in this implementation.
- Implement spec-first, test-first, thin helpers over existing protocol truth.
- Preserve current authority order: user > git/filesystem > mailbox > handoffs/STATE cache > defaults.
- Preserve coordinator no-production-code, operator independent-verifier, no-push/no-spend/no-lock defaults.

Next implementation route after this planning commit:

1. Task 1/2 can be owned by a protocol tooling director seat: extend scripts/codex_protocol_model.py and add scripts/seat_banner.py with focused tests.
2. Task 3 can be owned by the tooling director seat or a bounded implementation worker: add scripts/proof_bundle.py as read-only composer.
3. Task 4 should be reviewed carefully by an operator before hook wiring: add scripts/protocol_guards.py and negative/allowed-path tests.
4. Task 5 adds scripts/done_summary.py.
5. Task 6 wires docs/skills only after tools exist.
6. Task 7 runs focused protocol tests, check_coordination.py, ci_smoke.py, mailbox monitor, continuation_readiness --smoke, then sends one wrap event.

This event is a planning/task-board wrap only. It is not production implementation, not Lane V, not a lock claim, not push, not pod/API spend, and not an inventory transition. Push remains user-gated.

Cursor at send: unknown
