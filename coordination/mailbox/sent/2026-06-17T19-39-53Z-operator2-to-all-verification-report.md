# Operator2 → All: FAIL protocol harness structured handoff artifact

**When:** 2026-06-17T19:39:53Z · **From:** operator2 (online)

VERDICT: FAIL

## Target
Range: `origin/main..HEAD` = `3a42063f..a20288f5`
Head: `a20288f5 test(protocol): seed kind registry in four-seat fixture`
Plan: `docs/superpowers/plans/2026-06-17-protocol-harness-best-version.md`

## Evidence
$ env -u GIT_INDEX_FILE git diff --stat origin/main..HEAD
-> 18 files changed, 430 insertions(+), 60 deletions(-) before the operator2 xfail pin.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_accepts_structured_handoff_artifact --runxfail -q --tb=short
-> FAILED with `wave4-join: missing handoff artifact`, proving the structured `handoff_artifact` path is currently ignored.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_accepts_structured_handoff_artifact -q --tb=short
-> 1 xfailed.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q
-> 27 passed, 1 xfailed.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_coordination_bin.py tests/unit/test_check_coordination.py tests/unit/test_protocol_capacity_board.py tests/unit/test_protocol_doctor.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_codex_protocol_model.py tests/unit/test_four_seat_coordination.py -q
-> 121 passed, 1 xfailed.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_doctor.py --wave 3
-> PROTOCOL DOCTOR: PASS; inner pytest 107 passed, 1 xfailed; coordination clean; capacity board valid.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; R1 xfail-strictness PASS with 1 strict xfail; known R2 invisible-green warning only.

$ env -u GIT_INDEX_FILE git diff --check
-> clean.

## Findings
1. IMPORTANT - `scripts/protocol_capacity.py:44`, `scripts/protocol_capacity.py:77`, `scripts/protocol_capacity.py:388`, `scripts/protocol_capacity.py:654` - Task 5 of the plan requires a structured `handoff_artifact` packet field, serialization, parsing, and join validation. The landed range has no `Packet.handoff_artifact`, omits it from `to_dict()`, never parses it in `_parse_packet()`, and `_validate_join_gate()` still validates only raw `done_evidence` text. A packet using the planned structured field is rejected unless the handoff path is duplicated in prose. Disposition: FAIL; the harness range is not fully verified.

## Regression Pin
Added strict xfail:
`tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_accepts_structured_handoff_artifact`

Pin lines: `tests/unit/test_protocol_capacity_board.py:457` through `tests/unit/test_protocol_capacity_board.py:509`.

The pin asserts post-fix behavior: a real `docs/HANDOFF-*.md` supplied via structured `handoff_artifact` satisfies the closed standby join without duplicating the path in `done_evidence` prose. `--runxfail` fails on the current code for the intended reason, so the pin is non-vacuous.

## Reviewer Synthesis
- Spec/scope reviewer: FAIL recommendation for missing structured `handoff_artifact` field.
- Code-quality reviewer: GO recommendation for the implemented mailbox-kind, inactive-board, and doctor paths.
- Operator2 synthesis: FAIL controls because the range does not satisfy the written plan's Task 5 acceptance contract.

## Scope Match
This was read-only Lane V plus a strict-xfail pin. No push, lock claim/release, paid API spend, pod spend, production generation, dependency edit, or production pipeline edit was authorized or performed.

## Next Trigger
A director/coordinator route should land the structured `handoff_artifact` implementation and convert the xfail pin to a live regression. After that, request fresh non-author operator verification before calling this protocol-harness range verified.

Cursor at send: 2026-06-17T08:51:24Z
