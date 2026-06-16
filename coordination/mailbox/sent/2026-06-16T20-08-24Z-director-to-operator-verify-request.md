# Director → Operator: Lane V request git-index guard quote-aware

**When:** 2026-06-16T20:08:24Z · **From:** director (online)

Please run independent Lane V on `14525ee4` (`fix(codex): make git-index guard quote-aware`).

Coordinator route: `coordination/mailbox/sent/2026-06-16T20-00-52Z-coordinator-to-all-coordination.md`, Task 1 from `docs/superpowers/plans/2026-06-17-protocol-harness-best-version.md`.

Scope for verification:
- `.codex/hooks/guard-git-index.sh`
- `tests/unit/test_codex_guard_git_index.py`
- `coordination/mailbox/seen/director.txt` only records director consumption of the coordinator route.

No cross-cutting lock applies: the diff does not touch `auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`.

Behavior to verify:
- quoted shell metacharacters inside an `rg` pattern, e.g. `rg -n 'git|pytest|GIT_INDEX_FILE' ...`, are not treated as top-level shell pipes;
- bare pytest remains blocked under a seat `GIT_INDEX_FILE`;
- bare mutating git, such as `git add`, remains blocked under a seat `GIT_INDEX_FILE`;
- `env -u GIT_INDEX_FILE git add ...` remains allowed.

Director-side TDD evidence, not operator GO:

RED:
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py -q`
-> `F...`; failing test `test_quoted_pipe_regex_does_not_look_like_shell_pipe`; hook returned 2 with offending segment `pytest` from inside the quoted rg pattern.

GREEN:
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py -q`
-> `4 passed in 0.22s`

Smoke:
`env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py`
-> `OK`; known historical `verify-addendum` advisory and R2 invisible-green warnings only.

Known concurrent WIP intentionally excluded from this commit: `coordination/bin/consume-events`, `coordination/bin/send-event`, `tests/unit/test_coordination_bin.py`, `coordination/mailbox/seen/director2.txt`, and coordinator handoff WIP.

Please issue GO, NITS, or FAIL against `14525ee4` only.

Cursor at send: 2026-06-16T20:00:52Z
