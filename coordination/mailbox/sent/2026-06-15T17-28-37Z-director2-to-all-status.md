# Director2 → All: handoff: perf-phase route queued

**When:** 2026-06-15T17:28:37Z · **From:** director2 (online)

Director2 handoff written: `docs/HANDOFF-director2-2026-06-16-perf-phase-route.md`.

State:
- Consumed unread events through `2026-06-15T17:19:41Z`.
- `spent-usd-reset-on-resume` is verified by operator2 GO and coordinator reconciliation.
- `download-urllib-notimeout` is verified and reconciled.
- Wave 2 remains UNMET: `verified=19`, `open=11`.
- Remaining no-selector blocker: `perf-phase-no-gate` (`cinema/shots/controller.py:1076`).
- Product-oracle artifact is still missing.
- `scripts/ci_smoke.py` returned OK with existing advisories only.

Routing:
- Next director2 should start `perf-phase-no-gate` with an R-BRIEF: re-check test feasibility, Rule #12 the performance paid-call path, and Rule #13 against the motion-path pre-spend gate.
- Prefer an executable regression; if truly test-infeasible, surface exact reason and user-exemption need before relying on prose.
- Stop before any lock claim for `lipsync-veto` or `web_server.py` HTTP rows; lock claiming/push remains user-gated.
- Do not spend pod or paid API budget for product-oracle work without user authorization.

Dirty-tree warning: other-seat cursor dirt and an untracked coordinator handoff existed before this handoff; the director2 handoff commit should use explicit pathspecs.

Cursor at send: 2026-06-15T17:19:41Z
