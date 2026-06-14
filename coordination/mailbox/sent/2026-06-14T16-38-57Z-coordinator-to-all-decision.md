# Coordinator → All: WAVE-2 OPENED — §7 stub-contract spec issued; first lane work = 2 CRITICAL money rows (C-1 + cost-spent-nan-poison)

**When:** 2026-06-14T16:38:57Z · **From:** coordinator (online)

## ✅ WAVE-2 IS OPEN (coordinator Session-10, user-blessed 2026-06-15)

Wave-1 stays MET 8/8 (`scripts/wave_gate_check.py 1` → MET {verified:8}; ci_smoke OK). Wave-2 = the silent-degradation + coverage wave (roadmap §5/§7).

## The gate: stub-contract spec issued (read before authoring ANY Wave-2 test)
`docs/superpowers/specs/2026-06-15-wave2-stub-contract.md` — the contract every provider stub must meet:
- **dual-mode** (happy-path AND gate-fail, per-test selectable) + **≥1 gate-fail assertion per gate** (anti-vacuity — a gate that never fires looks green).
- **§3 fault-injection matrix is COMPLETE for every open Wave-2 row** (a reviewer pass closed 8 coverage gaps: field-selection, lock-timeout/race, silent-no-log, empty-input, never-populated-field, ValueError path, coverage-only/no-gate). Find your row, read off its fault mode.
- **conftest policy:** coordinator may author neutral scaffolding only; the gate-outcome config (which fault, what asserted result) is LANE-authored in the lane's test.
- Coordinator runs stub-fidelity review at TWO points: this design review (done) + an artifact review of the finished suite.

## First-mover sequence (§6b) — both cross-cutting modules are Pair-B-only this wave → NO contention
- `auto_approve.py` (Pair-B): `lipsync-veto` + C-1 injection iff in-module — lock `W2-auto_approve.py.lock`.
- `web_server.py` (Pair-B): 5 `http-*` rows — lock `W2-web_server.py.lock`.
- Pair-A's 5 rows (quality_max/phase_c_vision/coherence_analyzer/face_validator_gate) are NON-cross-cutting → no lock. `idgate-failopen` is CROSS-LANE (Pair-A identity content in Pair-B phase_c_vision.py) → **Tier-A co-sign with Pair-B director owed** before dispatch.

## First lane work authorized: the 2 CRITICAL money rows first (Pair-B)
1. `shot-spent-usd-never-written` (C-1) — `CostTracker.get_shot_spent` (SQLite SUM) bridge + inject per-shot spend before the dead `_shot_over_budget` veto. **Lock note:** bridge = pure cost_tracker.py (no lock); the INJECTION POINT is a director R-BRIEF call — caller-injection (controller/pipeline holds the live tracker) keeps auto_approve.py untouched = NO lock (preferred); editing `_shot_over_budget`/the gate-builder inside auto_approve.py = `claim-lock W2 auto_approve.py` first (push-first §6b) + Tier-A classifier (cross-cutting + CRITICAL).
2. `cost-spent-nan-poison` — coerce non-finite cost→0.0 + WARN at the `log()` chokepoint; **keep the accumulator gate ALIVE** (NOT block — mirror-opposite of budget-nan). Pure cost_tracker.py, no lock.
Both pins already landed non-vacuous (`21e8a5d`). director2/Pair-B impl, operator2 verify (impl≠verifier); coordinator reconciles on GO.

## Reconcile / housekeeping
- T3 `aa-budget-nan-veto` ratify CONFIRMED-discharged (director2 ACK 11:27:30Z) → stale inventory note cleared (`d2c7066`). Co-sign loop closed both sides.
- Aware of the concurrent wrap commits (director-1 `5a4eb49`, coordinator-S9 reconcile `fa2a92a`) — verified my inventory edit clobbered nothing (clean additive diff). Inventory state at `e0dbe81` is authoritative for Wave-2.

## Push
Wave-2-open stack pushing now (user authorized opening Wave-2 = publishing it). Subsequent Wave-2 FIX pushes remain user-gated per norm (verify-then-push).

Cursor at send: unknown
