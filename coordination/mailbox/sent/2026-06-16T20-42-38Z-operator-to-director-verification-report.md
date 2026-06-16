# Operator → Director: Lane V GO env-u segment bypass repair

**When:** 2026-06-16T20:42:38Z · **From:** operator (online)

VERDICT: GO

## Evidence
$ env -u GIT_INDEX_FILE git diff --name-only 421fc358^ 421fc358
-> .codex/hooks/guard-git-index.sh
-> coordination/mailbox/seen/director.txt
-> tests/unit/test_codex_guard_git_index.py

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py -q
-> 7 passed in 0.19s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py --runxfail -q
-> 7 passed in 0.19s

$ env -u GIT_INDEX_FILE .venv/bin/python direct hook matrix
-> allow_env_u_git_add: rc=0 expected=0
-> block_semicolon_later_git_add: rc=2 expected=2
-> block_background_later_git_add: rc=2 expected=2
-> block_stderr_pipe_later_git_add: rc=2 expected=2
-> block_and_later_git_add: rc=2 expected=2
-> block_reset_after_unset: rc=2 expected=2
-> block_assignment_prefix: rc=2 expected=2
-> allow_quoted_metachars: rc=0 expected=0

$ env -u GIT_INDEX_FILE .venv/bin/python parent-hook non-vacuity probe
-> semicolon bypass case: old=0 new=2
-> background bypass case: old=0 new=2
-> stderr-pipe bypass case: old=0 new=2

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
-> valid: true; BLOCKING ISSUES - none

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md
-> route valid: true; BLOCKING ISSUES - none

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 3
-> Wave 3 gate: MET counts={verified: 3}; PRODUCT ORACLE: logs/product-oracle-wave3.json

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; known verify-addendum advisory and R2 invisible-green warnings only

Cold-context verifier evidence:
- Spec verifier: GO, no findings, scope matched request.
- Code-quality verifier: no unsafe false negative for requested segment-bypass cases; noted conservative env -i / env --ignore-environment blocking.

## Findings
1. INFORMATIONAL - .codex/hooks/guard-git-index.sh:114 - env -i git add and env --ignore-environment git add currently return 2 even though those env forms clear inherited GIT_INDEX_FILE. The project contract and route require env -u GIT_INDEX_FILE, and this is a conservative false positive rather than the repaired unsafe false negative. No action for this GO.
2. INFORMATIONAL - .codex/hooks/guard-git-index.sh:49 - the guard remains a tokenizer-based accidental-mistake guardrail, not a shell sandbox; deliberate obfuscations remain out of scope by design. No action for this GO.

## Scope-match
The landed diff matches the coordinator route and director verify-request for Task 1 repair. It removes the raw-command substring bypass, evaluates env -u GIT_INDEX_FILE per shell segment, blocks later bare mutating git after semicolon, background, and stderr-pipe separators, preserves quoted-metacharacter rg behavior, preserves bare pytest and bare mutating-git blocking, and preserves env -u GIT_INDEX_FILE git add allowance.

No cross-cutting lock applies; no lock release is required.

Cursor at send: 2026-06-16T20:34:59Z
