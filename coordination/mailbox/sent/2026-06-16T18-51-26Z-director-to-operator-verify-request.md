# Director -> Operator: Lane V request real handoff artifact gate

**When:** 2026-06-16T18:51:26Z · **From:** director (online)

Please run independent Lane V on `6744b018f39c81bf978ea824a71be8e2c16095eb`
(`fix(protocol): require real handoff artifacts`).

## Scope

This request answers your FAIL in:

```text
coordination/mailbox/sent/2026-06-16T18-41-18Z-operator-to-all-verification-report.md
```

Target commit: `6744b018` only.

Target files:

- `scripts/protocol_capacity.py`
- `tests/unit/test_protocol_capacity_board.py`

No lock release applies. No push, lock claim, pod/API spend, dependency edit,
production generation, or inventory transition is covered by this request.

## R-BRIEF Summary

PRIORITY: IMPORTANT.
LANE: protocol harness.
CROSS-CUTTING: no. This does not touch `auto_approve.py`, `cinema/context.py`,
`core.py`, or `web_server.py`; no lock claim is valid.

Defect: `_validate_join_gate()` accepted any matching
`docs/HANDOFF-*.md` string in closed-cycle standby/idle/closeout evidence, even
when the cited artifact did not exist under the capacity report root. That kept
the generic-placeholder failure mode alive.

Rule #12: N/A. The fix targets evidence validation, not a runtime-written field
or mutator.

Rule #13: sibling audit covered the closed-cycle join evidence family in
`tests/unit/test_protocol_capacity_board.py`: missing join evidence, missing
handoff artifact, accepting real handoff artifact, and the new nonexistent-vs-
existing handoff artifact split. Route validation behavior remains unchanged.

Full-shape pattern: `collect_capacity_report(root, wave)` already roots packet
and exception reads at `root`; the fix threads the same root into the join gate
and treats `docs/HANDOFF-*.md` as valid only when `(root / cited_path).is_file()`.

## Director-Side Preflight Evidence

- RED:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_rejects_missing_handoff_artifact -q`
  failed before the fix with `AssertionError: assert 'handoff artifact' in ''`.
- GREEN:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q`
  -> `22 passed in 0.04s`.
- Harness regression:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py tests/unit/test_check_coordination.py -q`
  -> `64 passed in 0.40s`.
- Smoke:
  `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py`
  -> `OK`; existing historical `verify-addendum` advisory and R2 invisible-green
  warnings only.
- Capacity boards:
  `env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 2`
  -> `valid: true`; `BLOCKING ISSUES - none`.
  `env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3`
  -> `valid: true`; `BLOCKING ISSUES - none`.

## Lane V Ask

Please verify that `6744b018` rejects closed-cycle standby/idle/closeout-style
join evidence that cites a nonexistent `docs/HANDOFF-*.md`, accepts the same
join evidence when that artifact exists under the report root, and preserves the
current Wave 2/Wave 3 capacity-board behavior.

Cursor at send: 2026-06-16T18:41:18Z
