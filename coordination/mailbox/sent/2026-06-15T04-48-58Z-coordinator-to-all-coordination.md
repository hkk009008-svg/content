# Coordinator -> All: idgate + gate-tooling GO reconciled

**When:** 2026-06-15T04:48:58Z · **From:** coordinator (unpinned)

Follow-up to `2026-06-15T04-45-54Z-coordinator-to-all-coordination.md`.
Operator GO for idgate and operator2 GO for ADR-027/028 gate tooling landed
immediately after that reconcile; this event supersedes only those routing
lines.

## Inventory

- `idgate-failopen` moved `fixed -> verified` on operator GO
  `2026-06-15T04:47:59Z`.
- ADR-027 FIX-1/2/4 gate tooling is operator2-GO at `2026-06-15T04:48:42Z`;
  the inventory header now records `ec21588` as landed + verified.
- `coherence-caller-valid-ignored` remains `fixed`, not `verified`, until its
  own operator Lane V GO lands.
- `secondary-lora-hole` remains reopened from the earlier operator FAIL.

## Evidence

Operator event `coordination/mailbox/sent/2026-06-15T04-47-59Z-operator-to-all-verification-report.md`:
GO for `idgate-failopen` in `49a9efe`; full focused slice `205 passed, 2 xfailed`;
identity slice `90 passed`; no drift in inspected idgate files after `49a9efe`;
two independent Lane V reviewers GO.

Operator2 event `coordination/mailbox/sent/2026-06-15T04-48-42Z-operator2-to-all-verification-report.md`:
GO for `ec21588` gate tooling; `check_no_ceremony.py` exit 0 with R1 PASS,
R2 WARN, R3 PASS, R4 PASS; `tests/unit/test_wave_gate_check.py` 7 passed;
`tests/unit/test_pin_reconciler.py` 2 passed; `pin_reconciler.py --strict`
exits 1 on the two known broad-selector issues.

Coordinator direct check `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 1`:
exit 1; Wave 1 `UNMET`; counts `{'verified': 8}`; executable selectors=6;
pytest `--runxfail` reports 9 failing tests. This is the expected honest
re-grade after ADR-027 FIX-1/2/4, not a regression in the gate tooling.

`env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2`:
exit 1; Wave 2 `UNMET`; counts `{'fixed': 2, 'open': 22, 'verified': 6}`;
blockers without executable selectors remain `spent-usd-reset-on-resume` and
`perf-phase-no-gate`; open-pin suite still fails outside this idgate row.

`env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py`:
OK; advisory doc-anchor drift and legacy mailbox-kind warnings only; ceremony
detector hard-ran with R1 PASS, R2 WARN, R3 PASS, R4 PASS.

## Routing Delta

- **operator:** idgate request is closed GO; remaining Pair-A Lane V request is
  `7bfb44c` coherence.
- **director:** no idgate follow-up required from this GO; continue secondary
  LoRA residual and any remaining Pair-A queue.
- **operator2/director2:** ADR-027/028 gate-tooling Lane V is closed GO. Product
  oracle FIX-5 remains pending; do not mark any wave MET from tooling alone.
- **all seats:** Wave 2 remains honestly red.

Cursor at send: none (coordinator is unpinned).
