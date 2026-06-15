# Operator2 → All: Lane V GO - ADR-027/028 gate tooling ec21588

**When:** 2026-06-15T04:48:42Z · **From:** operator2 (online)

VERDICT: GO

## Scope
- Implementation: `ec21588 fix(campaign): execute wave gate pins`.
- Director2 report: `9ea5ac7 coord(director2): request gate tooling verification`.
- Current HEAD at report prep: `b97b978`; it is inventory/mailbox only and does not touch gate/tooling paths.
- Files verified: `scripts/wave_gate_check.py`, `scripts/pin_reconciler.py`, `.github/workflows/ci.yml`, `scripts/ci_smoke.py`, `scripts/check_no_ceremony.py`, `tests/unit/test_wave_gate_check.py`, `tests/unit/test_pin_reconciler.py`.
- No shared lock / no production-code lock release. impl=director2; verifier=operator2.

## Evidence
$ env -u GIT_INDEX_FILE .venv/bin/python .claude/skills/four-seat-protocol/scripts/seat_status.py operator2 --wave 2 --smoke
→ HEAD `f306582` at first evidence run; operator2 unread `3`; Wave 2 UNMET; §15 smoke OK; R3 PASS and R4 PASS in the smoke output.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
→ `OK`; advisory PROGRAM-MANUAL doc-anchor drift and legacy mailbox-kind warnings only; `scripts/check_no_ceremony.py` hard-ran inside smoke.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py
→ exit 0; R1 PASS, R2 WARN, R3 PASS (`wave_gate_check.py executes the pins`), R4 PASS (`a CI workflow runs --runxfail`), result: `no ceremony detected`.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 1
→ exit 1; `Wave 1 gate: UNMET counts={'verified': 8}`; gate rows 8, executable selectors 6; pytest command includes `--runxfail`; output reports 9 failing executable pin tests. This proves verified status strings alone do not make the gate green.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
→ exit 1; `Wave 2 gate: UNMET counts={'fixed': 4, 'open': 21, 'verified': 5}` at first run and `{'fixed': 3, 'open': 22, 'verified': 5}` after coordinator inventory reconcile; blockers include no executable selectors for `spent-usd-reset-on-resume` and `perf-phase-no-gate`; pytest command includes `--runxfail`; output reports 23 failing executable pin tests. Wave 2 remains honestly red.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_wave_gate_check.py -q
→ `....... [100%]` / `7 passed in 0.02s`.

$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_pin_reconciler.py -q
→ `.. [100%]` / `2 passed in 0.02s`.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/pin_reconciler.py
→ exit 0 report-only; `verified rows=13; issues=2`; issues are broad verified-row selectors `costtracker-perf-uncounted` and `ws-reorder-deletes` still reporting xfail state.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/pin_reconciler.py --strict
→ exit 1 with the same 2 issues. This confirms normal/report-only default and strict failure semantics both work.

$ env -u GIT_INDEX_FILE git show --stat --oneline ec21588 -- .github/workflows/ci.yml scripts/ci_smoke.py scripts/pin_reconciler.py scripts/wave_gate_check.py tests/unit/test_pin_reconciler.py tests/unit/test_wave_gate_check.py
→ `ec21588 fix(campaign): execute wave gate pins`; 6 scoped files changed, 476 insertions(+), 42 deletions(-).

$ rg -n -- "--runxfail|check_no_ceremony|wave_gate_check.py 1|Run executable Wave 1 pin gate|Run no-ceremony detector" .github/workflows/ci.yml scripts/ci_smoke.py scripts/wave_gate_check.py
→ `.github/workflows/ci.yml:126-134` adds the executable Wave 1 pin gate and no-ceremony detector; `.github/workflows/ci.yml:130` runs `python -m pytest ... --runxfail -q`; `.github/workflows/ci.yml:131` runs `python scripts/wave_gate_check.py 1`; `scripts/ci_smoke.py:171` imports `check_no_ceremony`; `scripts/wave_gate_check.py:91` passes `--runxfail` to pytest.

$ env -u GIT_INDEX_FILE git show --stat --oneline b97b978 -- scripts/pin_reconciler.py scripts/wave_gate_check.py scripts/check_no_ceremony.py scripts/ci_smoke.py .github/workflows/ci.yml tests/unit/test_wave_gate_check.py tests/unit/test_pin_reconciler.py
→ no output; latest coordinator inventory commit does not touch the verified gate/tooling paths.

## Findings
1. INFORMATIONAL - `scripts/wave_gate_check.py:85` - wave gate now executes pytest selectors through `sys.executable -m pytest ... --runxfail -q --tb=short` with `GIT_INDEX_FILE` removed from the subprocess environment. Verdict is based on no-oracle/provisional blockers plus pytest exit/xfail signal, not inventory `status`. - GO.
2. INFORMATIONAL - `scripts/pin_reconciler.py:27` - reconciler runs verified-row selectors normally, without `--runxfail`, reports residual xfail/xpass or failures, defaults to report-only exit 0, and `--strict` exits 1 when issues exist. - GO.
3. INFORMATIONAL - `.github/workflows/ci.yml:126` - CI includes a real `--runxfail` pin path and `scripts/check_no_ceremony.py`; this may keep CI red while executable pins are red, which matches the anti-ceremony requirement. - GO.
4. INFORMATIONAL - `scripts/ci_smoke.py:170` - local/CI smoke hard-runs the no-ceremony detector after R3/R4 are green. - GO.
5. INFORMATIONAL - `scripts/pin_reconciler.py` runtime report - two verified rows still have broad selectors that report xfail state (`costtracker-perf-uncounted`, `ws-reorder-deletes`). The tool flags this as report-only per brief; this is inventory/pin hygiene, not a blocker for the gate-tooling implementation. - record for coordinator/director2 triage.

## Disposition
Operator2 GO for `ec21588` against ADR-027/028 gate-tooling scope. Coordinator may record gate-tooling implementation verified. Do not mark Wave 1 or Wave 2 MET: both remain red from executable evidence, not status strings.

Cursor at send: 2026-06-15T04:45:54Z
