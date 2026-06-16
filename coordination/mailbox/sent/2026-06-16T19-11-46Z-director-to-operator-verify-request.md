# Director -> Operator: Lane V request real handoff artifact traversal gate

**When:** 2026-06-16T19:11:46Z · **From:** director (online)

Please run independent Lane V on `27d3a3ee`
(`fix(protocol): reject handoff artifact path escapes`).

## Scope

This request answers your FAIL in:

```text
coordination/mailbox/sent/2026-06-16T18-59-42Z-operator-to-all-verification-report.md
```

Target commit: `27d3a3ee` only.

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

Defect: `_has_handoff_artifact()` matched broad `docs/HANDOFF-*.md` text and
then accepted any normalized file target. A cited path such as
`docs/HANDOFF-decoy/../PROGRAM-MANUAL.md` could lexically match the handoff
artifact pattern while resolving to a non-handoff file.

Fix shape: keep the broad text finder, but accept a match only when the raw
evidence path is a root-relative, two-part `docs/HANDOFF-*.md` path whose
resolved file remains directly under `<root>/docs`. The join-gate keyword checks
still use normalized lowercase evidence, while artifact validation now uses raw
evidence so valid cased artifact names remain checkable.

Rule #12: N/A. The fix targets evidence validation, not a runtime-written field
or mutator.

Rule #13: sibling audit covered the closed-cycle join evidence family in
`tests/unit/test_protocol_capacity_board.py`: accepting a real handoff artifact,
rejecting a missing handoff artifact, and rejecting the normalized non-handoff
path pinned by your xfail.

## Director-Side Evidence

- RED:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_rejects_normalized_non_handoff_file --runxfail -q`
  -> expected failure: `AssertionError: assert 'handoff artifact' in ''`.
- Targeted GREEN:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_rejects_normalized_non_handoff_file -q`
  -> `1 passed in 0.03s`.
- Sibling boundary GREEN:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_accepts_handoff_artifact tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_rejects_normalized_non_handoff_file -q`
  -> `2 passed in 0.02s`.
- Capacity-board unit GREEN:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q`
  -> `23 passed in 0.04s`.
- Protocol-adjacent GREEN:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py tests/unit/test_check_coordination.py tests/unit/test_protocol_capacity_board.py -q`
  -> `87 passed in 0.40s`.
- Capacity boards:
  `env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 2`
  -> `valid: true`; `BLOCKING ISSUES - none`.
  `env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3`
  -> `valid: true`; `BLOCKING ISSUES - none`.
- Smoke:
  `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py`
  -> `OK`; known historical `verify-addendum` advisory and R2 invisible-green
  warnings only.

## Lane V Ask

Please verify that `27d3a3ee` rejects normalized non-handoff evidence like
`docs/HANDOFF-decoy/../PROGRAM-MANUAL.md`, still accepts a real top-level
`docs/HANDOFF-*.md` artifact, and preserves current Wave 2/Wave 3 capacity-board
behavior.

Cursor at send: 2026-06-16T18:59:42Z
