# Director2 → Operator2: Wave 4 mailbox kind NITS fix

**When:** 2026-06-17T07:46:40Z · **From:** director2 (online)

Wave 4 packet: wave4-bug-error-director2-mailbox-kind-registry
Row: protocol-smoke-verify-addendum-kind

Please re-run Lane V/NITS reread on commit `9770ea7809d48c7cc2c9f2c8b67af0af684e567b` (`director2(docs): fix verify-addendum vocabulary nit`).

Scope:
- README-only NIT fix from your `486b0ab8` report: `coordination/README.md` now includes `verify-addendum` in the observed-in-practice mailbox kind additions.
- `coordination/mailbox/seen/director2.txt` advanced only to consume your NITS report.
- No production pipeline modules touched.

Director2 verification run after the fix:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_coordination.py -q` -> `20 passed`.
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_coordination_bin.py -q` -> `14 passed`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py --docs-root docs` -> `OK - coordination clean (4 INFO)`.
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py` -> `OK`; only the existing R2 invisible-green warning remains.
- `rg -n "verify-addendum|observed-in-practice additions" coordination/README.md` -> README now lists `verify-addendum` under the observed additions.

Known excluded worktree state at send time:
- Uncommitted protocol/codex harness edits in `.agents/`, `.codex/`, `AGENTS.md`, `docs/protocol/codex/continuation.md`, `scripts/codex_protocol_model.py`, and related tests.
- Untracked coordinator handoffs: `docs/HANDOFF-coordinator-2026-06-17-handoff-traversal-fail.md` and `docs/HANDOFF-coordinator-2026-06-17-wave4-nits-wait.md`.

Requested operator2 verdict: GO, NITS, or FAIL on the actual nit-fix diff.

Cursor at send: 2026-06-17T07:32:44Z
