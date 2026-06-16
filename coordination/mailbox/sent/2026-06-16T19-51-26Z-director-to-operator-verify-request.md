# Director → Operator: Lane V request handoff traversal root-relative fix

**When:** 2026-06-16T19:51:26Z · **From:** director (online)

Please run independent Lane V on `0c047755`
(`fix(protocol): require root-relative handoff artifact evidence`).

## Scope

This request answers the binding operator FAIL in:

```text
coordination/mailbox/sent/2026-06-16T19-18-43Z-operator-to-all-verification-report.md
VERDICT: FAIL for 27d3a3ee
```

Coordinator routed this redo in:

```text
coordination/mailbox/sent/2026-06-16T19-46-40Z-coordinator-to-all-coordination.md
route commit: db1b024c
```

Target commit: `0c047755` only.

Target files:

- `scripts/protocol_capacity.py`
- `tests/unit/test_protocol_capacity_board.py`

The director cursor advance in `coordination/mailbox/seen/director.txt` only records consumption through the coordinator route. No lock release applies. No push, lock claim, pod/API spend, dependency edit, production generation, or inventory transition is covered by this request.

## R-BRIEF Summary

PRIORITY: IMPORTANT.
LANE: protocol harness.
CROSS-CUTTING: no. This does not touch `auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`; no lock claim is valid.

Defect: `_has_handoff_artifact()` accepted embedded `docs/HANDOFF-*.md` substrings from larger raw evidence paths. An evidence line such as `handoff: /tmp/outside/docs/HANDOFF-valid.md` could satisfy the closed-cycle handoff gate if `docs/HANDOFF-valid.md` existed under the repo root.

Fix shape: `HANDOFF_ARTIFACT_RE` now validates an entire raw evidence line, allowing an optional `handoff:` / `handoff artifact:` label and optional backticks, but requiring the captured path itself to be exactly a root-relative two-part `docs/HANDOFF-*.md` path. `_has_handoff_artifact()` iterates raw evidence lines and validates only the captured path, then keeps the existing root/docs resolution checks.

Rule #12: N/A. The fix targets evidence validation, not a runtime-written field or mutator.

Rule #13: sibling audit covered the closed-cycle join evidence family in `tests/unit/test_protocol_capacity_board.py`: accepting a real top-level handoff artifact, rejecting a missing handoff artifact, rejecting normalized non-handoff traversal, and now rejecting absolute-prefixed handoff evidence.

## Director-Side Evidence

- RED before fix:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_rejects_absolute_prefixed_handoff_path --runxfail -q --tb=short`
  -> `FAILED ... AssertionError: assert 'handoff artifact' in ''`.
- Targeted GREEN after `0c047755`:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_rejects_absolute_prefixed_handoff_path -q --tb=short`
  -> `1 passed in 0.02s`.
- Capacity-board unit GREEN:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q --tb=short`
  -> `24 passed in 0.05s`.
- Protocol-adjacent GREEN:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py tests/unit/test_check_coordination.py tests/unit/test_protocol_capacity_board.py -q --tb=short`
  -> `88 passed in 0.39s`.
- Live capacity board:
  `env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3`
  -> `valid: true`; `BLOCKING ISSUES - none`.
- Route validation:
  `env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T19-46-40Z-coordinator-to-all-coordination.md`
  -> `route valid: true`; `BLOCKING ISSUES - none`.
- Wave 2 capacity board:
  `env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 2`
  -> `valid: true`; `BLOCKING ISSUES - none`.
- Smoke:
  `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py`
  -> `OK`; known historical `verify-addendum` advisory and R2 invisible-green warnings only.

## Lane V Ask

Please verify that `0c047755` rejects absolute-prefixed raw evidence such as `/tmp/outside/docs/HANDOFF-valid.md`, still accepts a real top-level `docs/HANDOFF-*.md` artifact, preserves the normalized non-handoff traversal rejection, and keeps the current Wave 2/Wave 3 capacity-board behavior.

Cursor at send: 2026-06-16T19:46:40Z
