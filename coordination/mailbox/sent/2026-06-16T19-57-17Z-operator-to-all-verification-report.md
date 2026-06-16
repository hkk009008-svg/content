# Operator → All: Lane V GO handoff traversal root-relative fix

**When:** 2026-06-16T19:57:17Z · **From:** operator (online)

VERDICT: GO

## Scope
Target commit: `0c047755` (`fix(protocol): require root-relative handoff artifact evidence`).
Target files reviewed: `scripts/protocol_capacity.py`, `tests/unit/test_protocol_capacity_board.py`.
Mail read first: `2026-06-16T19-46-40Z-coordinator-to-all-coordination.md` and `2026-06-16T19-51-26Z-director-to-operator-verify-request.md`.

No cross-cutting lock applies: the diff does not touch `auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`.

## Evidence
$ env -u GIT_INDEX_FILE git show --no-ext-diff --unified=80 0c047755 -- scripts/protocol_capacity.py tests/unit/test_protocol_capacity_board.py
-> read actual target diff: `HANDOFF_ARTIFACT_RE` now full-matches stripped evidence lines; `_has_handoff_artifact()` captures only a root-relative `docs/HANDOFF-*.md` path and still resolves `root/docs` plus the artifact with `strict=True`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_rejects_absolute_prefixed_handoff_path -q --tb=short
-> `1 passed in 0.02s`

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q --tb=short
-> `24 passed in 0.05s`

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py tests/unit/test_check_coordination.py tests/unit/test_protocol_capacity_board.py -q --tb=short
-> `88 passed in 0.39s`

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3 --validate-route coordination/mailbox/sent/2026-06-16T19-46-40Z-coordinator-to-all-coordination.md
-> `route valid: true`; `BLOCKING ISSUES - none`

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 3
-> `valid: true`; `BLOCKING ISSUES - none`

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 2
-> `valid: true`; `BLOCKING ISSUES - none`

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> `OK`; known historical `verify-addendum` advisory and R2 invisible-green warnings only.

$ env -u GIT_INDEX_FILE /Users/hyungkoookkim/Content/.venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py::test_closed_standby_cycle_rejects_absolute_prefixed_handoff_path --runxfail -q --tb=short  # in temp copy of `0c047755^`
-> expected RED: `FAILED ... AssertionError: assert 'handoff artifact' in ''`.

Cold-context helper checks:
- Spec helper advisory verdict: GO; no findings; adversarial probe accepted real root-relative handoff evidence and rejected absolute/prefixed embedded evidence.
- Quality helper advisory verdict: NITS; no FAIL; residual risk that unsupported labels such as `handoff doc:` or bullet-only paths are rejected. The verify-request explicitly specified only exact path, optional backticks, `handoff:`, or `handoff artifact:`, and current capacity packet `done_evidence` does not use `handoff doc:`.

## Findings
1. INFORMATIONAL - `scripts/protocol_capacity.py:30` and `scripts/protocol_capacity.py:681` - The fix intentionally narrows accepted evidence lines to exact root-relative handoff paths with optional `handoff:` / `handoff artifact:` labels and backticks. This closes the embedded-substring bypass from the prior FAIL. - No action for this verdict.
2. INFORMATIONAL - `tests/unit/test_protocol_capacity_board.py:524` - The former strict xfail is now a normal passing regression, and the parent revision still fails it under `--runxfail`, proving the guard is non-vacuous. - No action for this verdict.
3. INFORMATIONAL - `0c047755` also includes `coordination/mailbox/seen/director.txt`; the verify-request explicitly identified it as director cursor consumption through the coordinator route, and no behavior or lock scope rides on it. - No action for this verdict.

## Scope-match
Non-cross-cutting Lane V. Landed behavior matches the coordinator route and director verify-request: reject absolute-prefixed `/tmp/outside/docs/HANDOFF-valid.md`, still accept real top-level `docs/HANDOFF-*.md`, preserve normalized non-handoff traversal rejection, and keep Wave 2/Wave 3 capacity-board behavior green.

Cursor at send: 2026-06-16T19:21:27Z
