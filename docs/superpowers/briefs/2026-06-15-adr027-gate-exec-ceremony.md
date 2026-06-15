# R-BRIEF: adr027-gate-exec - make wave verification execute pins, then hard-wire no-ceremony

PRIORITY: CRITICAL process integrity. LANE: B campaign infrastructure.
CROSS-CUTTING: no (touches `scripts/`, `.github/workflows/`, tests/docs only; not
`auto_approve.py`, `cinema/context.py`, `core.py`, or `web_server.py`) -> no lock.
CO-SIGN: none. This is routed to Pair-B director by ADR-027/ADR-028; operator2
Lane V verifies the landed diff.

## The Defect

`scripts/wave_gate_check.py` reports a wave as MET by reading the inventory
`status` column. It executes zero oracle tests, so a coordinator status edit can
produce a green gate without the gate itself proving the pins still pass.

Current evidence:

```
$ .venv/bin/python scripts/wave_gate_check.py 1
Wave 1 gate: MET  counts={'verified': 8}

$ .venv/bin/python scripts/check_no_ceremony.py
R1 xfail-strictness ....... PASS  26 xfail markers; all strict=True+reason
R2 invisible-green ........ WARN
R3 gate-executes-pins ..... FAIL  scripts/wave_gate_check.py reads the inventory `status` string and executes ZERO tests (ADR-027). 'GATE MET' is not a correctness claim. [FIX-1: rewrite to run the pins via --runxfail]
R4 ci-runs-runxfail ....... FAIL  .github/workflows/* never runs pytest with --runxfail, so the 70+ strict-xfail pins are never executed as a gate - they are CI-ceremony. [FIX-2: add a --runxfail pin-execution step]
```

`.github/workflows/ci.yml` currently runs only the normal unit suite:

```
$ env -u GIT_INDEX_FILE rg -n -- "--runxfail|pytest tests/unit|pytest" .github/workflows/ci.yml scripts/wave_gate_check.py scripts/check_no_ceremony.py
.github/workflows/ci.yml:124:        run: pytest tests/unit/ --tb=short -q
scripts/check_no_ceremony.py:135:    markers = ("--runxfail", "subprocess", "pytest.main", "runpy", "import_module")
```

## Rule #12 - Runtime Source Evidence

TARGET SYMBOLS: inventory `xfail-pin`, `wave`, `status`, and `severity` columns.

Command:

```
$ sed -n '1,90p' docs/REMEDIATION-INVENTORY.md
```

Relevant output:

```
Status one of: open | fixing | fixed | verified | provisional.
Schema: | id | subsystem | file:line | severity | priority | fail-mode | repro | xfail-pin | lane-owner | shared-lock | wave | status | verifier | notes |
Wave-close conditions AMENDED - ADR-027 ... the gate's authority is the EXECUTED pin suite (`pytest --runxfail` XPASS-clean) + an independent operator GO - NOT this `status` column.
```

The current gate reads those columns but only treats `status` as authoritative:

```
$ sed -n '1,90p' scripts/wave_gate_check.py
_COLS = (... "xfail-pin", ... "wave", "status", ...)
blockers = [
    r for r in rows
    if r["status"] == "provisional"
    or (r["severity"].upper() in _BLOCK_SEV and r["status"] != "verified")
]
```

Runtime pin source exists in inventory rows, but many cells are file-only and
shared across rows/waves:

```
$ rg -n "\\| .*\\| .*\\| .*\\| .*\\| .*\\| .*\\| yes \\| (tests/unit/.*xfail\\.py|test-infeasible)" docs/REMEDIATION-INVENTORY.md
docs/REMEDIATION-INVENTORY.md:36:| aa-nan-rules | ... | tests/unit/test_auto_approve_nangate_xfail.py | ... | 1 | verified | ...
docs/REMEDIATION-INVENTORY.md:42:| idgate-failopen | ... | tests/unit/test_lane_silent_gate_siblings_xfail.py | ... | 2 | open | ...
docs/REMEDIATION-INVENTORY.md:52:| lipsync-postproc-costkey | ... | tests/unit/test_discovery_cost_xfail.py | ... | 2 | open | ...
docs/REMEDIATION-INVENTORY.md:58:| ws-reorder-deletes | ... | tests/unit/test_discovery_web_server_xfail.py | ... | 1 | verified | ...
```

This means FIX-1 must treat the `xfail-pin` cell as an executable pytest selector
and report selector quality. A broad file selector that contains unrelated open
pins may legitimately make the gate fail, but the report must show that the
selector is too broad rather than laundering the result as a row-specific proof.

## Rule #13 - Sibling Audit

Shared enforcement surface:

- `scripts/wave_gate_check.py` is the wave verdict entrypoint.
- `scripts/check_no_ceremony.py` R3/R4 detects whether the gate and CI execute pins.
- `.github/workflows/ci.yml` is the current CI enforcement surface.
- `scripts/ci_smoke.py` is the local session-start smoke gate.
- `scripts/continuation_readiness.py` reports wave-gate state, but explicitly says
  ADR-027 makes it process state, not correctness proof.
- `tests/unit/test_wave_gate_check.py` currently encodes status-reader semantics and
  must be rewritten with the gate, not left as a ceremony-preserving test.

Fold now:

- FIX-1: make `wave_gate_check.py` execute the selected pins with `--runxfail`
  and derive the verdict from executed results plus explicit no-oracle blockers.
- FIX-2: add CI coverage that runs the same executable gate/pin path with
  `--runxfail` present.
- ADR-028 follow-through: once R3/R4 are green, wire `check_no_ceremony.py` into
  `scripts/ci_smoke.py` and CI as a hard gate.

Defer / document, do not silently solve:

- FIX-4 `pin_reconciler.py` can land in the same batch, but it must not become a
  second status-reader. It should execute verified-row selectors and flag stale
  xfail state from pytest output.
- FIX-5 product-oracle enforcement is out of this brief except for preserving the
  inventory language that Wave 2 cannot close without a committed `logs/` oracle.
- Operator-GO impl!=verifier remains a known gap from ADR-027; do not pretend
  FIX-1 enforces it unless the implementation actually does.
- Unregistered defects still escape any row-based gate; do not claim otherwise.

## Full-Shape Pattern Reference

Mirror `scripts/check_no_ceremony.py`:

- read-only script;
- deterministic stdout report with named rules/blockers;
- non-zero exit when hard blockers exist;
- never mutates inventory, tests, or source;
- failure messages name the mechanical check that failed.

The CI/smoke hard-wiring should mirror `scripts/ci_smoke.py`'s existing gate
style: call a committed checker, print useful diagnostics, and hard-fail locally
once the known ADR-027 R3/R4 violations have been fixed.

## The Fix

### FIX-1 - executable wave gate

Rewrite `scripts/wave_gate_check.py` so `gate_report()` and CLI output distinguish
process status from executed proof.

Required behavior:

1. Parse inventory rows as today, preserving counts for display.
2. For CRITICAL/MAJOR rows in the requested wave, build executable pytest selectors
   from `xfail-pin`.
3. Treat non-executable or missing selectors (`test-infeasible`, `design-open`,
   blank, prose-only cells) as hard blockers unless a future explicit
   user-principal exemption/`attested` contract is implemented and cited.
4. Execute selectors with `env -u GIT_INDEX_FILE <python> -m pytest <selectors> --runxfail -q`
   via a subprocess or equivalent committed execution path.
5. Gate verdict is MET only when the executable pin run exits 0, no XPASS/failure
   signal exists, and no no-oracle/provisional blocker exists.
6. The inventory `status` column is display-only for the verdict. It may appear in
   counts and blocker context; it must not be the reason a row passes.
7. Report broad selector failures clearly. If a selector names a whole file that
   contains unrelated open pins, the honest result is UNMET with enough pytest
   output to show the selector must be narrowed to a row-specific node id.
8. Keep `scripts/wave_gate_check.py 2` useful during an open wave: it should fail
   because open pins/no-oracle blockers execute or are missing, not because the
   `status` column says open.

### FIX-4 - verified-row pin reconciler

Add `scripts/pin_reconciler.py`.

Required behavior:

1. Read verified rows with executable selectors.
2. Run each selector normally, without `--runxfail`.
3. Flag any selector whose pytest output still reports xfailed/xpassed state for
   the row; a verified row should have been converted into a live regression.
4. Report non-executable selectors separately from test failures.
5. Start as a warning/reporting tool unless the implementing commit explicitly
   wires it as a hard gate with evidence that current verified rows are clean.

### FIX-2 + ADR-028 hard wiring

After FIX-1 makes `check_no_ceremony.py` R3 pass and CI includes a real
`--runxfail` execution path for R4:

1. Add a CI step that runs the executable pin/gate path with `--runxfail` present.
2. Add `scripts/check_no_ceremony.py` to CI as a hard gate.
3. Add `scripts/check_no_ceremony.py` to `scripts/ci_smoke.py` as a hard local
   gate only after R3/R4 are green.
4. Do not hard-wire `check_no_ceremony.py` before FIX-1/FIX-2; ADR-028 explicitly
   says that would red-light known tracked work before the fixes land.

## Verification

Before implementation:

```
.venv/bin/python scripts/check_no_ceremony.py
# expected today: R3 FAIL and R4 FAIL

.venv/bin/python scripts/wave_gate_check.py 1
# expected today: MET from status only; this is the ceremony being removed
```

After implementation:

```
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_wave_gate_check.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 1
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Expected post-fix shape:

- `test_wave_gate_check.py` asserts execution/no-oracle behavior, not status-only MET.
- `check_no_ceremony.py` R3 passes after FIX-1.
- `check_no_ceremony.py` R4 passes after FIX-2.
- Once both pass, `ci_smoke.py` includes the detector as a hard gate and remains OK.
- If Wave 1 flips from MET to UNMET, surface it as the intended honest re-grade,
  not a regression to hide.

## Dispatch Decision

Implementation spans multiple enforcement surfaces (`wave_gate_check.py`, tests,
new `pin_reconciler.py`, CI, smoke). Use R-ORCH if dispatching implementation:
one fresh implementer for FIX-1, then sequential FIX-2/ADR-028 wiring, then FIX-4
or a separate follow-up if scope grows. Operator2 performs Lane V; director2 does
not verify their own implementation.
