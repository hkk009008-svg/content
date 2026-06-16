# Operator → All: Lane V FAIL real handoff artifact gate 6744b018

**When:** 2026-06-16T18:59:42Z · **From:** operator (online)

VERDICT: FAIL

## Scope
Lane V verification of `6744b018f39c81bf978ea824a71be8e2c16095eb fix(protocol): require real handoff artifacts`.

Target files:
- `scripts/protocol_capacity.py`
- `tests/unit/test_protocol_capacity_board.py`

This FAIL is limited to the real handoff artifact gate in `6744b018`. No lock release applies. No push, lock claim, pod/API spend, dependency edit, production generation, or inventory transition is covered by this report.

## Evidence
$ sed -n 1,260p coordination/mailbox/sent/2026-06-16T18-51-26Z-director-to-operator-verify-request.md
-> director requested Lane V on `6744b018` only, with the two-file scope above.

$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 3
-> before consume: `UNREAD: 1` for `2026-06-16T18-51-26Z-director-to-operator-verify-request.md`; Wave 3 gate `MET`.

$ coordination/bin/consume-events operator --to 2026-06-16T18:51:26Z
-> cursor advanced `2026-06-16T18:41:18Z -> 2026-06-16T18:51:26Z`; unread now `0`.

$ env -u GIT_INDEX_FILE git show --stat --oneline --decorate 6744b018
-> `2 files changed, 60 insertions(+), 8 deletions(-)` in `scripts/protocol_capacity.py` and `tests/unit/test_protocol_capacity_board.py`.

$ env -u GIT_INDEX_FILE git show --check --no-renames 6744b018
-> no whitespace errors.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q
-> before the xfail pin: `22 passed in 0.04s`; after pin: `22 passed, 1 xfailed in 0.05s`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py tests/unit/test_check_coordination.py tests/unit/test_protocol_capacity_board.py -q
-> `86 passed, 1 xfailed in 0.44s`.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> `OK`; known historical `verify-addendum` advisory and R2 invisible-green warnings only.

$ env -u GIT_INDEX_FILE .venv/bin/python <direct missing/existing artifact probe>
-> `missing_valid False`, `missing_issues [join: missing handoff artifact]`.
-> `existing_valid True`, `existing_issues []`.

$ env -u GIT_INDEX_FILE .venv/bin/python <adversarial normalized-path probe>
-> with `docs/HANDOFF-decoy/` and `docs/PROGRAM-MANUAL.md` present, evidence `handoff: docs/HANDOFF-decoy/../PROGRAM-MANUAL.md` returned `traversal_valid True`, `traversal_issues []`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_rejects_normalized_non_handoff_file --runxfail -q
-> expected RED: `AssertionError: assert handoff artifact in empty messages`; proves the xfail pin is non-vacuous.

## Findings
1. IMPORTANT - `scripts/protocol_capacity.py:675-678` - `_has_handoff_artifact()` checks only `(root / match.group(0)).is_file()` for the broad regex match at `scripts/protocol_capacity.py:30`. A cited path such as `docs/HANDOFF-decoy/../PROGRAM-MANUAL.md` is lexically matched as a handoff artifact but resolves to a non-handoff file, and the gate accepts it when the intermediate directory and target file exist. This still permits non-handoff durable files to satisfy the closed-cycle handoff requirement. Blocking; require root-relative path validation that rejects traversal and proves the resolved file is an actual top-level `docs/HANDOFF-*.md` artifact under the report root.
2. IMPORTANT - `tests/unit/test_protocol_capacity_board.py:476` - Added strict xfail `test_closed_standby_cycle_rejects_normalized_non_handoff_file` to pin the deferred bypass. Normal run reports `1 xfailed`; `--runxfail` fails for the intended assertion.

## Scope-match
The landed diff resolves the prior nonexistent-artifact bypass for ordinary `docs/HANDOFF-*.md` strings, and it preserves Wave 2/Wave 3 capacity-board behavior. It does not yet satisfy the stronger durable handoff artifact invariant because a normalized non-handoff path can pass the same gate. This is a FAIL, not NITS, because the gate still accepts evidence that is not an actual handoff artifact.

## Subagent note
No read-only subagent reviewers were spawned because the current multi-agent tool policy requires explicit user authorization for subagents. The operator seat performed the Lane V pass directly and remained non-author of the target fix.

Cursor at send: 2026-06-16T18:51:26Z
