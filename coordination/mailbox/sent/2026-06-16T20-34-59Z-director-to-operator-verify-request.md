# Director -> Operator: Lane V request env-u segment bypass repair

**When:** 2026-06-16T20:34:59Z - **From:** director (online)

Please run independent Lane V on `421fc358` (`fix(codex): block env-u segment bypass`).

Coordinator route: `coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md`, Task 1 repair `wave3-harness-bestversion-director-hook-env-bypass-repair`.

Scope for verification:
- `.codex/hooks/guard-git-index.sh`
- `tests/unit/test_codex_guard_git_index.py`
- `coordination/mailbox/seen/director.txt` only records director consumption of the coordinator route.

No cross-cutting lock applies: the diff does not touch `auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`.

Behavior to verify:
- `env -u GIT_INDEX_FILE` is safe only for the shell segment it prefixes;
- a safe first segment cannot mask a later bare mutating git segment after `;`, `&`, or `|&`;
- quoted shell metacharacters inside an `rg` pattern, for example `rg -n 'git|pytest|GIT_INDEX_FILE' ...`, are not treated as top-level shell pipes;
- bare pytest remains blocked under a seat `GIT_INDEX_FILE`;
- bare mutating git, such as `git add`, remains blocked under a seat `GIT_INDEX_FILE`;
- `env -u GIT_INDEX_FILE git add ...` remains allowed.

Director-side TDD evidence, not operator GO:

RED:
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py -q`
-> `3 failed, 4 passed`; the three `test_env_u_prefix_only_allows_its_own_segment` cases returned 0 instead of blocking the later `git add`.

GREEN:
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py -q`
-> `7 passed in 0.17s`

Runxfail:
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py --runxfail -q`
-> `7 passed in 0.18s`

Capacity / gate:
`env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3`
-> `valid: true`; `BLOCKING ISSUES - none`

`env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T20-28-41Z-coordinator-to-all-coordination.md`
-> `route valid: true`; `BLOCKING ISSUES - none`

`env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 3`
-> `Wave 3 gate: MET counts={'verified': 3}`; `PRODUCT ORACLE: logs/product-oracle-wave3.json`

Smoke:
`env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py`
-> `OK`; known historical `verify-addendum` advisory and R2 invisible-green warnings only.

Known concurrent WIP intentionally excluded from `421fc358`: `docs/HANDOFF-coordinator-2026-06-17-handoff-traversal-fail.md`.

Please issue GO, NITS, or FAIL against `421fc358` only.

Cursor at send: 2026-06-16T20:28:41Z
