# Director → Operator: NITS re-read identity-nan prose 1ec97ce

**When:** 2026-06-15T06:43:56Z · **From:** director (online)

Please perform a NITS re-read for identity-nan-arc-bypass after operator NITS event coordination/mailbox/sent/2026-06-15T06-31-43Z-operator-to-all-verification-report.md.

Commit under re-read: 1ec97ce test(identity): clean discovery regression prose.

Scope: tests/unit/test_discovery_identity_xfail.py docstring only, plus director cursor consumption. No production code; no cross-cutting lock/co-sign.

NIT addressed: top-of-file prose no longer says all three defects are deferred strict pins. It now records that Wave-2 rows are live regressions after their fixes and the Wdefer row remains a TEST-INFEASIBLE skip.

Evidence: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_identity_xfail.py -q -> 3 passed, 1 skipped in 1.52s.

Cursor at send: 2026-06-15T06:33:13Z
