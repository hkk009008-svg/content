# Operator2 → All: protocol harness audit for coordinator awareness

**When:** 2026-06-16T18:26:02Z · **From:** operator2 (online)

Coordinator/all-scope awareness note. User asked to mail the protocol/harness/guardrail audit to coordinator; direct `to-coordinator` events are invalid in the current mailbox vocabulary because coordinator is send-only/unpinned, so this is addressed to `all` for coordinator-readable all-scope review.

## Audit Summary

Bottom line: the Codex protocol harness is mostly working as intended at the executable-model level, but not airtight. The core model, readiness bridge, role-boundary tests, Codex artifact tests, capacity-board tests, and smoke checks are green. The remaining risks are operational guardrails and adoption details, not a total protocol failure.

## Evidence Checked

- `scripts/codex_protocol_model.py` centralizes mailbox-first, same-seat handoff, explicit modes, user-gated side effects, coordinator no-production-fix, operator GO, and capacity-route validation.
- `scripts/continuation_readiness.py` renders readiness bridge correctly when role env is cleared, and role inference works when explicit env mappings are passed.
- Focused tests passed: `tests/unit/test_codex_protocol_model.py`, `tests/unit/test_continuation_readiness.py`, `tests/unit/test_codex_protocol_artifacts.py`, and `tests/unit/test_protocol_capacity_board.py` -> `66 passed in 0.25s`.
- `scripts/ci_smoke.py` passed with known advisories only.
- `scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T17-26-44Z-coordinator-to-all-coordination.md` correctly rejected the old closeout as not a task-board route and as having no capacity packets.

## Findings

1. IMPORTANT — `.codex/hooks/guard-git-index.sh` has a real false positive. During the audit it blocked a harmless `rg` search because the quoted regex contained `|pytest|`; the parser splits on `|` without respecting shell quoting. Recommended fix: add a Codex-hook regression for quoted metacharacters and split only on top-level shell control operators.
2. IMPORTANT — `protocol_capacity_board.py --wave 2/3/4` prints `valid: true` when there are zero capacity packets. Route validation catches unpacketed routes, but the standalone board can look too reassuring. Recommended fix: mark this as `valid: true (inactive, no packets)` or add a `--require-packets` mode for coordinator route workflows.
3. NITS — `ci_smoke.py` still warns that mailbox kind `verify-addendum` is unknown. `protocol_effectiveness_report.py` already knows that kind, while `scripts/check_coordination.py` does not. Recommended fix: align the kind enum or migrate the historical event name so known warnings do not dull smoke signal.
4. NITS — The current handoff-artifact gate in dirty WIP is directionally right but stringly. It infers closeout/standby transfer from free-form evidence text. Recommended fix: add a structured packet field like `handoff_artifact`, keeping regex as backward-compatible fallback.
5. SCOPE — Current dirty protocol WIP is not covered by the operator GO at `5d64e516`; that GO explicitly covered only `010b24d5`. Fresh Lane V is needed before claiming the newer WIP is verified.

## Current Local State At Audit

- HEAD observed: `0d923449 coord(cursor): director consume protocol capacity GO`.
- Dirty files observed: `.agents/skills/four-seat-protocol/SKILL.md`, `.agents/skills/seat-coordinator/SKILL.md`, `docs/protocol/codex/continuation.md`, `scripts/protocol_capacity.py`, `tests/unit/test_protocol_capacity_board.py`.
- No production code edit was made by this audit.

## Requested Coordinator Action

Treat this as an audit/status FYI, not a route or verified transition. If coordinator chooses to act, recommended first route is a narrow protocol-fix task for the guard false positive plus capacity-board no-packet UX, followed by operator Lane V on the protocol diff.

Cursor at send: 2026-06-16T17:26:44Z
