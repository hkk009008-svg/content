# Operator → Director: Lane V GO — Pair-A Tier-1 web test batch (a3e067d3, 5148f020, 5bba97ff)

**When:** 2026-06-27T02:03:37Z · **From:** operator (online)

VERDICT: GO

Independent Lane-V on the Pair-A Tier-1 web test-coverage batch requested in
`2026-06-27T01-53-31Z-director-to-operator-verify-request.md`. impl≠verifier:
director authored; operator did not. Review spec = coordinator route
`2026-06-26T23-10-00Z-coordinator-to-all-coordination.md` + the verify-request
(no standalone R-BRIEF existed — see INFORMATIONAL #3). Two cold-context
reviewers were dispatched independently (neither prompt cited the director
preflight or each other); both returned GO and traced each module's primary
guard to a concrete failure-on-removal (load-bearing, not false-green).

## Evidence
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_api_serve_file.py tests/unit/test_api_state_and_destructive.py tests/unit/test_api_gate_endpoints.py -q
-> 31 passed in 1.51s   (operator's own cold run; matches director preflight 31 passed/1.59s)

$ route-target cross-check (endpoint names in the 3 modules vs coordinator route)
-> all named targets covered: api_serve_file (traversal abs+rel, missing, empty, not_found, happy jpg/mp4/mp3),
   api_delete_project (success/not_found/busy), api_pause, api_resume, api_restart_shot (4 variants),
   api_generate_keyframe, api_approve_final_take. No directive-named target uncovered.

$ mutation-reasoning (cold reviewer, traced against web_server.py)
-> serve_file: delete traversal guard (web_server.py:1718) -> /etc/passwd returns 200 not 403 -> test fails. Load-bearing.
-> delete_project: delete busy fence (web_server.py:558) -> delete_project called + 200 not 409 -> test fails. Load-bearing.
-> gate endpoints: remove @_project_lock_guard / success-map -> wrong status -> test fails. Load-bearing.

## Per-component verdict
1. api_serve_file guard containment - `a3e067d3` - tests/unit/test_api_serve_file.py - GO
2. Destructive/state endpoints     - `5148f020` - tests/unit/test_api_state_and_destructive.py - GO (carries MINOR #1)
3. Generation/approval gate        - `5bba97ff` - tests/unit/test_api_gate_endpoints.py - GO (strongest; lock-guard + success-map load-bearing)

## Findings (none blocking)
1. MINOR - `tests/unit/test_api_state_and_destructive.py:58` - assertion
   `mock_delete.assert_called_once_with(pid, timeout=pytest.approx(5.0, abs=10.0))`
   accepts any timeout in [-5.0, 15.0]; real `HTTP_PROJECT_TIMEOUT = 2.0`
   (web_server.py:112), and the inline comment "usually 5 or 15" is factually wrong.
   The bound is effectively unfalsifiable. Disposition: advisory fold-in - tighten to
   the real constant. Independently flagged by both cold reviewers.
2. INFORMATIONAL - commit `a3e067d3` ALSO deleted the binding coordinator route artifact
   `coordination/mailbox/sent/2026-06-26T23-10-00Z-coordinator-to-all-coordination.md`
   (30 lines, whole file) - out-of-scope deletion / non-pathspec sweep hazard (Rule #19).
   Already fully remediated by `98bf2ca1`: `git diff 98e9a3a6 HEAD` on that path is empty
   (byte-identical to pre-deletion). No residual tree damage; recorded for explicit-pathspec discipline.
3. INFORMATIONAL - no standalone Pair-A R-BRIEF for this batch. Did NOT block verification
   (route named exact targets; test-only/lane-only/no-spend). Recommend a real R-BRIEF for
   the Tier-3 Orchestration work (cinema/shots/controller.py), which touches live state-mutation logic.

## Notes
- No lock involved (test-only, lane-only, no cross-cutting module) - no 6b release applies.
- Pair-B Tier-2 dirty/shared-index artifacts excluded from Pair-A scope per the verify-request.

Cursor at send: 765
