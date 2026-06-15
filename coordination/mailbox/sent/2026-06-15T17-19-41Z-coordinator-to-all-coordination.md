# Coordinator -> All: seat assignments after spent-resume verification

**When:** 2026-06-15T17:19:41Z - **From:** coordinator (online)

Coordinator assignment pass requested by user after `main` was pushed and aligned
with `origin/main`.

Baseline evidence:

- `seat_status.py coordinator --wave 2` -> coordinator/all-scope events `144`,
  HEAD `1c3a454e`, `main` `0 ahead / 0 behind`, all peer heartbeats stale.
- `seat_status.py <seat> --wave 2` unread counts before this notice:
  director `4`, director2 `2`, operator `4`, operator2 `2`.
- `git log --oneline -5` before this assignment -> `1c3a454e`, `c6c6350c`,
  `f7b99d9e`, `2c2e1026`, `58063bf7`.
- `scripts/wave_gate_check.py 2` -> UNMET, counts `{'verified': 19, 'open': 11}`,
  `20` executable selectors, remaining no-selector blocker
  `perf-phase-no-gate`, missing Wave 2 product-oracle artifact, and `15 failed,
  48 passed` in the open-row pin suite.
- `scripts/ci_smoke.py` -> OK with existing advisory doc-anchor /
  invisible-green warnings only.
- `coordination/locks/` -> only `.gitkeep`.
- `find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print` -> no
  output.

Assignments:

- `director`: consume unread all-scope updates, then stay idle for implementation.
  Pair-A has no active Wave 2 implementation row in this snapshot. Be available
  for product-oracle identity/ArcFace review, Tier-A co-signs, or a new Pair-A
  request; do not take Pair-B rows.

- `operator`: consume unread all-scope updates, then return no-op evidence unless
  a Pair-A verify request or coordinator-routed product-oracle identity review
  lands. Do not verify Pair-B diffs by default.

- `director2`: consume unread updates, then own the next active Pair-B lane task:
  `perf-phase-no-gate` (`cinema/shots/controller.py:1076`). Start with an
  R-BRIEF that re-checks the no-selector/test-feasibility problem, Rule #12 write
  evidence for the performance paid-call path, and Rule #13 sibling audit against
  the existing motion-path pre-spend gate. Prefer an executable regression if it
  can be made honest; if it truly remains test-infeasible, surface the exact
  reason and the user-exemption need before relying on prose. After a landed fix
  or truthful selector artifact, request operator2 Lane V.

- `operator2`: consume unread updates, then wait for director2's
  `perf-phase-no-gate` verify request. When it lands, verify the actual diff and
  the selector/non-vacuity story; send one GO/NITS/FAIL report with executed
  evidence.

Queue after `perf-phase-no-gate`:

- Product-oracle artifact remains mandatory for Wave 2 close. Do not spend pod or
  paid API budget for product-oracle generation/measurement without user
  authorization.
- `lipsync-veto` and the `web_server.py` HTTP batch are lock-gated
  (`W2-auto_approve.py.lock`, `W2-web_server.py.lock`). Stop before
  `coordination/bin/claim-lock`; lock claiming/push remains user-gated.
- Non-lock checkpoint rows (`ckpt-sceneidx-dead`, `ckpt-shotaudio-loss`,
  `ckpt-projectid-nocrosscheck`) are available after the gate-blocking
  no-selector row is addressed, unless a newer coordinator route supersedes this.

Cursor at send: coordinator is unpinned; no cursor consumed.
