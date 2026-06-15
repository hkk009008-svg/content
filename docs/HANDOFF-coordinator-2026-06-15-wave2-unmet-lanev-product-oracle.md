# HANDOFF - Coordinator, 2026-06-15 - Wave 2 unmet; Lane V and product oracle owed

READ FIRST AS COORDINATOR. This is a cross-seat handoff after reconciling the
latest Wave-2 mailbox and gate state. Trust git and mailbox over this prose if
they diverge.

## State At Wrap

- Write-start timestamp: `2026-06-15T05:54:45Z`.
- HEAD at write-start: `f104e03 coord(director): restore director2 unread handoff`.
- Branch state from coordinator seat status: `main`, `14 ahead`, `0 behind`.
- Coordinator is unpinned: no `seen/coordinator.txt`, no cursor consumed.
- Coordinator/all-seat mailbox count from
  `.agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2`:
  `UNREAD: 91` all-time `-to-coordinator-` / `-to-all-` events.
- Peer heartbeat snapshot from the same command: `director` and `director2`
  online; `operator` last 13m old; `operator2` last 12m old.
- Shared tree is dirty from other seats/protocol transplant work. Use explicit
  pathspecs and `env -u GIT_INDEX_FILE` for git/pytest commands.
- No push performed. Push remains user-gated.

Recent git evidence:

```text
$ env -u GIT_INDEX_FILE git log --oneline -20
f104e03 coord(director): restore director2 unread handoff
cb9d433 coord(director): hand off Pair-A wave2 state
412369a coord(cursor): director2 consume Pair-A handoff
311c78a coord(cursor): director2 consume latest handoff
3e2fc8b coord(verify): request llmensemble and product-oracle Lane V
54d0713 coord(inventory): reconcile coherence gate state
c8c0d40 fix(campaign): read product oracle artifacts from HEAD
4b81b31 fix(money): thread llm ensemble costs
3b21d74 verify(campaign): FAIL product oracle gate
1322fc5 verify(coherence): GO analyzer warning
b5af885 coord(inventory): verify secondary lora hole
fe3be8b docs(handoff): director2 product oracle gate wrap
66ed480 coord(director): hand off Pair-A wave2 state
88ab00d verify(identity): GO secondary lora reachability
4a36383 coord(cursor): director2 consume product oracle updates
0427470 coord(status): product oracle gate awaiting Lane V
38169c6 coord(verify): request product oracle gate Lane V
4300e4e fix(campaign): enforce product oracle wave gate
6de2f6a coord(cursor): director consume coherence broadcast
849b385 coord(verify): request coherence-silent Lane V
```

## Gate Proof

`scripts/ci_smoke.py` is clean:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
OK
```

Known advisories remain: 123 `docs/PROGRAM-MANUAL.md` doc-anchor drifts,
legacy mailbox kinds `verify-readiness` / `verify-readiness-converged`, and
two R2 invisible-green warnings in pin files.

Wave 2 is still red:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'fixed': 2, 'open': 19, 'verified': 9}
BLOCKER [MAJOR/open] spent-usd-reset-on-resume ... no executable xfail-pin selector
BLOCKER [MAJOR/open] perf-phase-no-gate ... no executable xfail-pin selector
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact ...
21 failed, 38 passed, 1 warning
```

Interpretation: `wave_gate_check.py` is process-state plus executed pin suite
evidence. It is not a correctness proof for any individual row; verified rows
still require operator `verification-report` GO.

## Binding Mailbox / Commits Since Last Coordinator Reconcile

- `54d0713 coord(inventory): reconcile coherence gate state` - coordinator
  event `2026-06-15T05-43-18Z` records `coherence-silent` verified and Wave 2
  still unmet.
- `4b81b31 fix(money): thread llm ensemble costs` - `llmensemble-cost-uncounted`
  is `fixed`; operator2 Lane V owed.
- `c8c0d40 fix(campaign): read product oracle artifacts from HEAD` - repairs
  the prior product-oracle gate FAIL findings; operator2 Lane V owed.
- `3e2fc8b coord(verify): request llmensemble and product-oracle Lane V` -
  director2-to-operator2 verify request for both `4b81b31` and `c8c0d40`.
- `cb9d433 coord(director): hand off Pair-A wave2 state` plus `f104e03` cursor
  restore - latest Pair-A director handoff is durable.

Read-first handoff for Pair-A:
`docs/HANDOFF-director-2026-06-15-pairA-wave2-coherence-go-product-oracle-fail.md`.

## Inventory State To Preserve

- `coherence-silent`: `verified` on operator GO `2026-06-15T05:38:18Z`.
- `secondary-lora-hole`: `verified` on operator GO `2026-06-15T05:20:49Z`.
- `has-char-lora-hole`: remains `fixed`; no formal per-row GO after the older
  combined verification FAIL.
- `llmensemble-cost-uncounted`: `fixed`; operator2 Lane V owed.
- ADR-027 product-oracle gate implementation: repaired at `c8c0d40`; operator2
  Lane V owed. The real Wave-2 product-oracle measurement artifact is still
  separately owed.
- `identity-nan-arc-bypass`: remaining Pair-A lane-only row; director handoff
  has pre-scope.
- Pair-B open rows remain per inventory, including `spent-usd-reset-on-resume`,
  `perf-phase-no-gate`, `charmgr-cost-fresh-instance`,
  `cost-conn-crossthread-drop`, `lipsync-veto`, `perf-take-meta`,
  `audioflag-inherit`, and web/checkpoint rows.

## Next Coordinator Actions

1. Wait for operator2 Lane V on `4b81b31` and `c8c0d40`. On GO, reconcile only
   the rows actually covered by the report; on FAIL, route back to director2.
2. Do not mark product-oracle close condition satisfied until the actual
   committed `logs/product-oracle-*.json` artifact exists and passes the gate.
3. Keep Wave 2 open until `scripts/wave_gate_check.py 2` exits 0 and the
   operator GO evidence is present.
4. Do not author production fixes as coordinator.
5. Do not push without explicit user authorization.
