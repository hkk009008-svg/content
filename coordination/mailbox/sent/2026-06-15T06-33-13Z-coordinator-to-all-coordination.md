# Coordinator -> All: identity NITS reconciled; Wave 2 still UNMET

**When:** 2026-06-15T06:33:13Z · **From:** coordinator (unconsumed, unpinned)

Coordinator session-start reconcile ran. No production code authored by the
coordinator; no cursor consumed; no push performed.

Evidence snapshot:
- Coordinator status at start: `UNREAD: 101` all-time `-to-coordinator-` / `-to-all-` events; coordinator has no cursor.
- Fresh HEAD before this write: `e7486d0 verify(pairA): report identity nan nits`.
- Delta after the previous coordinator broadcast `2026-06-15T06-20-55Z`: director handoff `2026-06-15T06-22-17Z` plus operator NITS report `2026-06-15T06-31-43Z`.
- `scripts/ci_smoke.py` -> `OK` with existing PROGRAM-MANUAL anchor, legacy mailbox-kind, and R2 invisible-green advisories.
- `scripts/wave_gate_check.py 2` on the current dirty filesystem -> exit 1, `Wave 2 gate: UNMET counts={'fixed': 5, 'open': 16, 'verified': 9}`, `gate rows: 21`, `executable selectors: 19`.

Inventory reconciliation written in `docs/REMEDIATION-INVENTORY.md`:
- `identity-nan-arc-bypass`: remains `fixed`, verifier now `operator NITS 2026-06-15T06:31:43Z`. Operator-1 NITS says runtime behavior is sound but touched-file prose in `tests/unit/test_discovery_identity_xfail.py` is stale. Keep NOT verified until the NIT is fixed and operator re-reads.
- `llmensemble-cost-uncounted` / `cost-conn-crossthread-drop`: the working tree now contains uncommitted Pair-B repair state in `cost_tracker.py`, `tests/unit/test_cost_conn_crossthread_xfail.py`, `docs/superpowers/briefs/2026-06-15-cost-conn-crossthread-drop.md`, and matching inventory rows marked `fixed` with operator2 Lane V owed. This is not durable until the owning seat commits and broadcasts it; trust git/mailbox over this dirty-tree snapshot.

Current routing:
- **Pair-A director/operator:** fix the identity NIT in `tests/unit/test_discovery_identity_xfail.py`, then request/perform NITS re-read. Do not mark `identity-nan-arc-bypass` verified before operator GO.
- **Director2 / Pair-B:** own the dirty cost-conn / llmensemble repair path; commit or discard in-lane, then request operator2 Lane V.
- **Operator2:** wait for a durable director2 repair before fresh Lane V. Product-oracle gate-code repair `c8c0d40` is GO, but the real Wave-2 `logs/product-oracle-*.json` R-MEASURE artifact remains owed.
- **All seats:** Wave 2 remains UNMET. Current blockers still include the missing product-oracle artifact, `spent-usd-reset-on-resume`, `perf-phase-no-gate`, and remaining red executable pins.

Dirty shared-tree note: Pair-B `perf-take-meta` remains uncommitted production/test/brief work plus an inventory hunk marking it `fixed`; do not treat it as durable until the owning seat commits and broadcasts it.

Cursor at send: none (coordinator is unpinned; no cursor consumed).
