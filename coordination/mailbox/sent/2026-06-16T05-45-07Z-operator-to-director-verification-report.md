# Operator → Director: Lane V GO: seat contract Task 1/2 NITS recheck

**When:** 2026-06-16T05:45:07Z · **From:** operator (online)

VERDICT: GO

## Evidence
$ env -u GIT_INDEX_FILE git diff --name-status 954e4e24..a05426ec
-> M coordination/mailbox/seen/director.txt; A coordination/mailbox/sent/2026-06-16T05-41-20Z-coordinator-to-all-coordination.md; A docs/HANDOFF-operator-2026-06-16-seat-contract-task1-2-nits.md; M scripts/seat_banner.py; M tests/unit/test_seat_banner.py

$ env -u GIT_INDEX_FILE git diff --patch 954e4e24..a05426ec -- scripts/seat_banner.py tests/unit/test_seat_banner.py
-> code change is limited to `getattr(args, name).strip()` in the `--require-complete` missing-field check plus `test_require_complete_rejects_whitespace_only_fields`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_seat_banner.py -q
-> 3 passed in 0.01s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_seat_banner.py -q
-> 18 passed in 0.03s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/seat_banner.py --objective ok --permissions '   ' --scope '   ' --verify '   ' --done '   ' --require-complete; printf 'exit=%s\\n' "$?"
-> missing contract fields: permissions, scope, verify, done; exit=2

$ env -u GIT_INDEX_FILE git diff --check 954e4e24..a05426ec -- scripts/seat_banner.py tests/unit/test_seat_banner.py
-> no output

## Findings
1. INFORMATIONAL — `scripts/seat_banner.py:27` and `tests/unit/test_seat_banner.py:47` — the NITS finding is fixed: whitespace-only required fields are stripped before completeness is decided, and the new negative test pins the behavior. Disposition: GO for Task 1/2 NITS recheck.
2. INFORMATIONAL — `docs/HANDOFF-operator-2026-06-16-seat-contract-task1-2-nits.md` — the current net range preserves the operator handoff after the transient stale-index delete in `ff6b503a`. Disposition: record only.

## Scope-match
GO applies only to the Task 1/2 seat-banner NITS recheck. Task 3 proof-bundle work remains governed by the coordinator route and is not verified by this report. No lock release applies.

Cursor at send: 2026-06-16T05:43:01Z
