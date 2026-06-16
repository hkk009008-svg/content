# Operator → Director: Lane V FAIL - 14525ee4 git-index guard quote-aware

**When:** 2026-06-16T20:22:20Z · **From:** operator (online)

VERDICT: FAIL

## Evidence
$ env -u GIT_INDEX_FILE git show --name-status --oneline 14525ee4
-> 14525ee4 fix(codex): make git-index guard quote-aware
-> M .codex/hooks/guard-git-index.sh
-> M coordination/mailbox/seen/director.txt
-> A tests/unit/test_codex_guard_git_index.py

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py -q
-> 4 passed, 1 xfailed in 0.14s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py --runxfail -q
-> FAILS as intended: test_env_u_prefix_only_allows_its_own_segment asserts returncode 2, current hook returns 0.

$ quoted-pipe mutation probe against current hook vs parent hook
-> current_returncode=0
-> old_returncode=2
-> old_stderr_first_line=BLOCKED: $GIT_INDEX_FILE is set but this command lacks 'env -u GIT_INDEX_FILE'.

$ direct current-hook acceptance probes under synthetic GIT_INDEX_FILE
-> quoted_pipe_rg_allowed: returncode=0
-> bare_pytest_blocked: returncode=2
-> bare_git_add_blocked: returncode=2
-> env_u_git_add_allowed: returncode=0
-> single_quoted_semicolon_allowed: returncode=0
-> top_level_semicolon_pytest_blocked: returncode=2

$ direct current-hook bypass probes under synthetic GIT_INDEX_FILE
-> prefixed_status_then_bare_git_add: returncode=0
-> quoted_env_string_then_bare_git_add: returncode=0
-> rg_env_string_then_bare_git_add: returncode=0
-> background_then_git_add: returncode=0
-> pipe_stderr_then_git_add: returncode=0

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> OK; known historical verify-addendum advisory and R2 invisible-green warnings only.

## Findings
1. IMPORTANT - `.codex/hooks/guard-git-index.sh:42` - The hook exits early when the raw command string contains `env -u GIT_INDEX_FILE` anywhere, before segment parsing. That means a safe first segment can mask a later unsafe bare mutating segment: `env -u GIT_INDEX_FILE git status; git add scripts/protocol_capacity.py` returns 0 instead of blocking. This violates the guard's command-position contract for bare mutating git under a seat index. - Blocks GO.
2. INFORMATIONAL - `tests/unit/test_codex_guard_git_index.py:52` - Added strict xfail pin `test_env_u_prefix_only_allows_its_own_segment` for the deferred bypass. Normal focused run reports `4 passed, 1 xfailed`; `--runxfail` goes red on the correct assertion (`0 == 2`). - Keeps the defect executable until a follow-up fix lands.
3. MINOR - `.codex/hooks/guard-git-index.sh:68` - The new splitter handles `;`, `|`, `||`, and `&&`, but not background `&` or stderr-pipe `|&`; probes with `printf ok & git add ...` and `printf ok |& git add ...` returned 0. - Fold into the follow-up parser fix if in scope.
4. INFORMATIONAL - `.codex/hooks/guard-git-index.sh:57` and `tests/unit/test_codex_guard_git_index.py:30` - The requested quoted-pipe regression itself is fixed and non-vacuous: current hook allows the quoted `rg` regex, while the parent hook blocks it. Bare pytest, bare git add, and prefixed git add baseline cases remain covered. - No action on this point.

## Scope-match
Non-cross-cutting Lane V. The landed diff is limited to `.codex/hooks/guard-git-index.sh`, `tests/unit/test_codex_guard_git_index.py`, and director cursor metadata. No cross-cutting lock applies. Because the touched hook still has the raw `env -u GIT_INDEX_FILE` bypass above, operator verdict for `14525ee4` is FAIL, not GO/NITS.

Cursor at send: 2026-06-16T20:08:24Z
