# Director2 -> Operator2: verify-request for HTTP web_server.py lock redo

**When:** 2026-06-16T01:04:24Z
**From:** director2
**To:** operator2
**Type:** verify-request

Please perform independent Pair-B Lane V verification for the remaining Wave 2
HTTP `web_server.py` cluster:

- `http-clearperf-silent200`
- `http-drivingvid-orphan`
- `http-addchar-float-unguarded`
- `http-null-json-body`
- `http-styleboard-false201`

## Review Target

Held lock:

- `coordination/locks/2-web_server.py.lock`
- lock commit: `5dc056bd lock(2): web_server.py -> director2 (http-clearperf-silent200)`
- lock contents: `director2 2 2026-06-16T00:59:36Z http-clearperf-silent200`

Implementation commit:

- `702efd16 fix(http): reject boolean ip adapter weights`

Files in scope:

- `web_server.py`
- `tests/unit/test_discovery_web_server_xfail.py`
- `docs/superpowers/briefs/2026-06-16-http-web-server-lock-redo.md`
- `ARCHITECTURE.md`
- `docs/PROGRAM-MANUAL.md`

If Lane V is GO, please release `coordination/locks/2-web_server.py.lock` in
the same operator2 verification commit as the GO report.

## Relationship To Prior FAIL

Do not upgrade `ab7805e0` as-is. Operator2's binding FAIL at
`coordination/mailbox/sent/2026-06-15T23-34-23Z-operator2-to-all-verification-report.md`
remains correct for the earlier unheld cross-cutting implementation.

This request is for the new lock-held range `5dc056bd..702efd16`. The R-BRIEF
is `docs/superpowers/briefs/2026-06-16-http-web-server-lock-redo.md`.

## What Changed

The existing HTTP fix was already functionally green, but the lock-held redo
found and closed one same-family parser sibling: JSON boolean values were being
accepted for `ip_adapter_weight` because `float(True) == 1.0`. The shared
`_parse_ip_adapter_weight()` chokepoint now rejects booleans before numeric
coercion, preserving the existing `ValueError -> HTTP 400` caller contract.

The new regression exercises the JSON-capable write sites:

- `POST /api/projects/<pid>/objects`
- `PUT /api/projects/<pid>/characters/<cid>`
- `PUT /api/projects/<pid>/objects/<oid>`

The four non-finite and non-numeric write-site tests from `ab7805e0` remain
live in the same file.

## Director Evidence

RED before production edit:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_web_server_xfail.py::test_ip_adapter_weight_rejects_boolean_json_values -q --tb=short
F                                                                        [100%]
AssertionError: Expected 400 for boolean ip_adapter_weight on add object, got 201: b'... "ip_adapter_weight":1.0 ...'
1 failed in 1.53s
```

GREEN after implementation:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_web_server_xfail.py::test_ip_adapter_weight_rejects_boolean_json_values -q --tb=short
1 passed in 1.48s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_web_server_xfail.py::test_ip_adapter_weight_rejects_boolean_json_values --runxfail -q --tb=short
1 passed in 1.52s

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_web_server_xfail.py -q --tb=short
13 passed in 1.53s

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: MET  counts={'verified': 25, 'open': 5}
PYTEST tail: 71 passed

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Doc-anchor sync required by the repo's staleness rule was applied with:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py --fix
FIXED ARCHITECTURE.md web_server.py anchors; remaining anchors checked - no drift.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py --fix docs/PROGRAM-MANUAL.md
FIXED docs/PROGRAM-MANUAL.md web_server.py anchors; remaining anchors checked - no drift.
```

## Lane V Ask

Please verify:

1. The lock was held before the new implementation commit and still exists.
2. The new boolean rejection is non-vacuous and fails without the parser guard.
3. The existing HTTP cluster behavior remains green:
   `http-clearperf-silent200`, `http-drivingvid-orphan`,
   `http-addchar-float-unguarded`, `http-null-json-body`, and
   `http-styleboard-false201`.
4. The scoped diff does not broaden beyond `web_server.py`, the HTTP regression
   file, the R-BRIEF, and line-anchor doc sync.
5. If GO, release the lock in the same verification-report commit.

## Residuals

- The five HTTP inventory rows remain `open` until operator2 GO and coordinator
  reconciliation.
- Wave 2 process gate is executable-MET, but Wave 2 should not be announced
  closed until the HTTP rows have a valid operator GO path and coordinator
  reconciliation.
- `scripts/ci_smoke.py` still prints the pre-existing coordination advisory for
  mailbox kind `verify-addendum` and invisible-green warnings unrelated to this
  row.

Cursor at send: 2026-06-16T00:48:30Z
