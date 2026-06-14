# Coordinator → All (route → Pair-B director): ADR-027 adopted — make the wave gate EXECUTE the oracle (FIX-1/2/4)

**When:** 2026-06-14T19:52:48Z · **From:** coordinator (Session-12, online) · **Kind:** coordination

User-principal critique → coordinator RCA (`wf_26a5abf2-3bb`, `logs/discovery-wf_26a5abf2-3bb.json`, adversarially stressed) → **ADR-027** (committed `ededed1`). User has **ratified** the prevention plan and authorized routing. Coordinator authored NO production code.

## Doctrine ADOPTED now (all seats)
**A status-tally "GATE MET" is NOT evidence of correctness.** `wave_gate_check.py` reads the inventory `status` string and runs ZERO tests. Cite what was mechanically EXECUTED (the operator GO's `--runxfail` RED→GREEN), never the status column, as a correctness claim. (seat-coordinator skill updated.)

## ROUTED to the Pair-B director — you OWN the R-BRIEF (this is a skeleton, not the brief)
Three campaign-infra changes (gate/CI scripts). impl≠verifier (Rule #9): a Pair-B operator runs Lane V on each.

- **FIX-1 (S, highest leverage):** rewrite `scripts/wave_gate_check.py` to **execute** the wave-tagged pins (`env -u GIT_INDEX_FILE python -m pytest <wave pins> --runxfail -q`) and derive MET from exit-0 / XPASS-clean. The `status` column becomes display-only. ⚠ **This will re-grade the current Wave-1 "MET 8/8" — it will likely flip to UNMET** for any test-infeasible or non-XPASS-clean row (e.g. `shot-spent-usd-never-written`). **That flip is the intended, user-ratified outcome** (the gate can finally disagree with the inventory) — not a regression to paper over.
- **FIX-4 (M):** new `scripts/pin_reconciler.py` — re-run every `verified` row's pin WITHOUT `--runxfail`; flag any that still XFAIL (fix absent/regressed). Non-blocking CI warning first, then hard-gate.
- **FIX-2 (S, after FIX-1):** wire `wave_gate_check.py` into CI on every push to main.

**Critic flags to honor in the brief:** (a) FIX-7 (nightly `face_validator` on fixtures) is DEFERRED until the `_ARC_AVAILABLE=False` CI-vacuity is fixed — wiring it first = a vacuous green; (b) FIX-1 does NOT close two gaps, recorded in ADR-027: operator-GO impl≠verifier is still not gate-enforced, and unregistered defects (e.g. `coherence-silent` caller-side half) escape any row-reading gate.

## Coordinator-authored (docs, this session)
- **FIX-5 spec amendment (user-ratified):** from Wave-2 onward a wave does NOT close without ≥1 committed product-oracle artifact in `logs/` (ArcFace arc + lip-sync offset, R-MEASURE). Recorded in the spec §5 amendment + inventory header. Enforcement depends on FIX-1.
- Test-infeasible rows are **`attested`**, not `verified` (need explicit user exemption to pass a gate).

## Still live (unchanged)
Wave-2 in progress; `web_research-uncounted` fixed (`f5a95ec`), operator2 Lane V pending; 2 provisional CRITICALs (`idgate-failopen`, `charmgr-cost-fresh-instance`) await lane ratification; `idgate` Tier-A co-sign routed. Pod 07ed667 STOPPED.

Cursor at send: read through 2026-06-14T19:52:48Z.
