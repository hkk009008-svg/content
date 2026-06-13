# Director → All: director PM3 WRAP (Pair-A, OFFLINE after this) — handoff 7f798fe; production PuLID SDXL->FLUX fix Chunk-1 EXECUTED (a1103bd/f05c83b/c5199de, TDD-green, scoped 152/0, ci_smoke OK); ONLY Task 4 pod acceptance gate remains (pod DOWN); experiment graft still audited-GO+banked

**When:** 2026-06-13T09:03:11Z · **From:** director (online)

**Director PM3 wrap — Pair-A (image-gen + identity/realism). OFFLINE after this.**

**Handoff:** `docs/HANDOFF-director-2026-06-13-PM3-pulid-flux-chunk1-executed-pod-gate-pending-4seat-pairA.md` (7f798fe).

**Shipped this session (Pair-A lane):** the production PuLID SDXL→FLUX no-op fix, full brainstorm→spec→plan→execute. **Chunk-1 offline code is committed + TDD-green:** `a1103bd` (Pulid.json 99/100/101 FLUX swap + regression test), `f05c83b` (workflow_selector pulid_start_at=0.0 + docstring), `c5199de` (test_workflow_selector align). ci_smoke OK, scoped suite 152/0.

**Next Pair-A operator:** (1) independently verify Chunk-1 (the deltas vs the design spec + a clean scoped pytest); (2) the **pod acceptance gate (Task 4)** is the only thing between the fix and shipping-default — BLOCKED on pod-up + user spend-go; do NOT treat the fix as the shipping default until it passes (fp8 compat + FaceDetailer-free binding are the empirical unknowns). Plan: `docs/superpowers/plans/2026-06-13-production-pulid-flux-fix.md` Chunk 2.

**Also live in our lane:** experiment graft `_prod_dual_lora_pulid.py` audited-GO+banked (pod+spend-gated); 2 data-integrity siblings to route (continuity_engine:181, character_manager:396); ⚠ CASE LANDMINE `Pulid.json`(git-tracked) vs `pulid.json`(code) — latent on case-sensitive checkouts.

Pod DOWN, no spend this session. Pair B (director2/operator2) owns video/assembly/delivery.

Cursor at send: 2026-06-13T08:54:01Z
