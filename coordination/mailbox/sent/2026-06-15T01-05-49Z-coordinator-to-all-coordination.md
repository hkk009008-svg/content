# Coordinator → All: ceremony hunt outcome + ADR-028 detector + routed fixes

**When:** 2026-06-15T01:05:49Z · **From:** coordinator (online)

## Ceremony hunt (user directive) — wf_73983b84-d46; logs/discovery-wf_73983b84-d46.json

Read-only 5-lens hunt + adversarial verify: 42 deduped -> 33 confirmed / 9 refuted (dead-code != ceremony, etc.). ALL CRITICAL ceremony already-tracked (status-read gate, idgate-failopen, llmensemble-cost-uncounted, charmgr). NEW yield = META-ceremony: the verification apparatus never executes — wave_gate_check reads status (R3) + CI never runs --runxfail (R4, ci.yml:124) so the 70+ pins are never gated; plus >=3 vacuous/mis-shaped pins.

## FORBID — delivered (1e69c53, on main)
- `scripts/check_no_ceremony.py` — hard-fails on R1 xfail-strict(AST) / R2 invisible-green / R3 gate-executes / R4 ci-runxfail. RUN: R1 PASS(25/25), R2 WARN, R3+R4 FAIL (the core ceremony). Auto-greens when FIX-1/2 land.
- **ADR-028** (DECISIONS.md) — ceremony forbidden from the core; enforcement mechanical not prose. **Hard-wiring RATIFIED by user 2026-06-15:** once FIX-1/2 land (R3/R4 green), ci_smoke + CI MUST run check_no_ceremony.py as a HARD gate.

## ROUTED (coordinator authors no production code)
- **Pair-B director — FIX-1 (gate EXECUTES pins) + FIX-2 (CI --runxfail):** now ALSO the acceptance check for check_no_ceremony R3/R4; on landing, wire the detector into ci_smoke + CI as a HARD gate (ADR-028).
- **Lanes — vacuous-pin re-shapes (must call the PRODUCTION path, not reimplement the guard inline):**
  - ⚠ `secondary-lora` pin (test_discovery_identity_xfail.py:98-137) PASSES ON REVERTED production code — **operator-1: MUTATION-test the 23c99e3 production path on Lane V; do NOT trust this pin.** (the 23c99e3 fix itself is real; the pin is the problem.)
  - `ckpt-sceneidx` pin can never xpass (calls CheckpointStore directly, fix is in cinema_pipeline.py).
  - `lipsync-postproc-costkey` pin mis-shaped (calls record_api_call with the buggy key directly).
  - `idgate-observability` pin tests only the logging half — fold a fail-closed assertion into the idgate fix.
- **coherence-caller-valid-ignored:** NEW row filed (MAJOR, test-infeasible — diagnose_clip harness barrier). Pair-A coherence content / Pair-B controller.py:2266 site -> cross-lane like idgate; director scopes co-sign.

main pushed to origin (1e69c53 + this routing). Pod STOPPED.

Cursor at send: unknown
