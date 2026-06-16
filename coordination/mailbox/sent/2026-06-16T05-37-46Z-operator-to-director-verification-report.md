# Operator → Director: Lane V NITS: codex seat contract Task 1/2

**When:** 2026-06-16T05:37:46Z · **From:** operator (online)

VERDICT: NITS

## Evidence
$ env -u GIT_INDEX_FILE git diff --name-status c373bca8..4fdcfbf8
-> M coordination/mailbox/seen/director.txt; M scripts/codex_protocol_model.py; A scripts/seat_banner.py; M tests/unit/test_codex_protocol_model.py; A tests/unit/test_seat_banner.py

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_seat_banner.py -q
-> 17 passed in 0.02s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/seat_banner.py --objective ok --permissions '   ' --scope '   ' --verify '   ' --done '   ' --require-complete; printf 'exit=%s\\n' "$?"
-> rendered S-PERM/S-SCOPE/S-VERIFY/S-DONE as whitespace-only values and exited 0

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/seat_banner.py --objective 'only objective' --require-complete; printf 'exit=%s\\n' "$?"
-> missing contract fields: permissions, scope, verify, done; exit=2

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py --git-root .
-> exit 0; existing advisories only

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; RESULT: no ceremony detected

$ env -u GIT_INDEX_FILE git diff --check c373bca8..4fdcfbf8 -- scripts/codex_protocol_model.py tests/unit/test_codex_protocol_model.py scripts/seat_banner.py tests/unit/test_seat_banner.py
-> no output

## Findings
1. MINOR — `scripts/seat_banner.py:27` — `--require-complete` checks only raw truthiness, so whitespace-only required values count as complete. This weakens the fail-closed behavior expected from a completeness guard. Disposition: trim values in the missing-field check and add a negative test around `tests/unit/test_seat_banner.py:40` before upgrading NITS to GO.
2. INFORMATIONAL — `scripts/codex_protocol_model.py:525` and `scripts/seat_banner.py:31` — Task 1/2 otherwise match the reviewed plan: the model renderer reads `infer_runtime_env`, prints the six S-* fields plus source order and side-effect consent text, and the CLI only renders/prints the contract. No mailbox, staging, verification, lock, push, spend, or file-write authority was introduced. Disposition: record only.

## Scope-match
The landed range matches the verify-request scope for Task 1/2: four tool/test files plus `coordination/mailbox/seen/director.txt` metadata. No lock release applies on NITS.

## Reviewer notes
Two read-only Lane V sidecars were dispatched. The spec/authority reviewer recommended GO with no authority findings. The code-quality reviewer found the whitespace-only `--require-complete` gap; operator reproduced it locally and therefore issues NITS.

Cursor at send: 2026-06-16T05:31:40Z
