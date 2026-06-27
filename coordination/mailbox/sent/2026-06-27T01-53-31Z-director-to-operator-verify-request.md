# Director → Operator: Pair-A Tier-1 web test coverage batch -> Lane V

**When:** 2026-06-27T01:53:31Z · **From:** director (online)

Independent Lane-V requested on the Pair-A Tier-1 test-coverage batch from the coordinator route.

Directive: `coordination/mailbox/sent/2026-06-26T23-10-00Z-coordinator-to-all-coordination.md` (`98e9a3a6`).
Standalone Pair-A R-BRIEF: none found in `docs/superpowers/briefs/` or June 26/27 mailbox grep; use the coordinator route plus this verify-request as the review spec and mark NITS/FAIL if that protocol gap matters for acceptance.

Scope is test-only, lane-only, no network/spend. Please verify each component independently and issue GO/NITS/FAIL per component.

1. `api_serve_file` guard containment — `a3e067d3` — `tests/unit/test_api_serve_file.py`.
2. Destructive/state endpoints — `5148f020` — `tests/unit/test_api_state_and_destructive.py` — covers `api_delete_project`, `api_pause`, `api_resume`, `api_restart_shot`-family state mutation behavior.
3. Generation/approval gate endpoints — `5bba97ff` — `tests/unit/test_api_gate_endpoints.py` — covers keyframe generation and final-take approval gate behavior.

Director preflight:
`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_api_serve_file.py tests/unit/test_api_state_and_destructive.py tests/unit/test_api_gate_endpoints.py -q`
Result: `31 passed in 1.59s`.

Known excluded workspace state at request time: unrelated Pair-B Tier-2 dirty/shared-index artifacts in `tests/unit/test_auto_approve.py`, `tests/unit/test_coherence_analyzer.py`, `tests/unit/test_face_validator_gate.py`, `tests/unit/test_kling_native.py`, `tests/unit/test_ltx_native.py`, Pair-B mailbox/brief artifacts, `.coverage`, and `coverage.xml`. Do not treat those as Pair-A Tier-1 scope.

Expected verdict: GO if the three committed test modules match the coordinator route and pass independently; NITS/FAIL for any route mismatch, test fragility, unintended fixture coupling, or the missing standalone brief if it blocks protocol acceptance.

Cursor at send: 768
