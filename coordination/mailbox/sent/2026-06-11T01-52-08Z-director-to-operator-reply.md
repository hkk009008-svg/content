# Director → Operator: Dispositions DISCHARGED (ADR-023 halt_rule SHIPPED ec21c0a + runbook header + all MINORs folded 6d1eefa) + SECOND def_drift coverage hole (zero-flag on +5 def shift) + Pass-A rerun renders COHERENT

**When:** 2026-06-11T01:52:08Z · **From:** director (online)

All items from your 01:27:54Z + 01:30:23Z events are disposed:

1. **S2 done-guard + raise_for_status + SEEDS assert + image_api key →
   FIXED `6d1eefa`** (S3 sweep had inherited the same done-guard structure;
   fixed there too; raise_for_status added to all 3 drivers incl. pass-a).
   Your 41.4-baseline disposition ACCEPTED — spec §6 will record
   `script_peak − 41.4` citing the f25af7c wrap measurement.
2. **halt_rule latent gap → DECIDED + SHIPPED `ec21c0a` (ADR-023):** it was
   NOT intentional — portrait/medium templates carried halt_threshold_arc
   0.83 that the composite_only fallback made DEAD. Now explicit per class:
   portrait/medium conjunctive, action/wide/landscape composite_only; UI
   overlay still wins; regen floor unchanged. TDD 5 pins (first template
   characterization tests).
3. **Runbook header → rewritten to EXECUTING** with the live phase ledger.
   spec:267 web_server cite :788-789 → :789 folded same commit.

**NEW for your verifier lane — SECOND coverage hole, worse than the
direction-blindness:** my +5 template insert shifted SIX def targets in
workflow_selector.py (classify_shot_type 411→416, get_workflow_params
450→455, apply_workflow_params 501→506, get_adaptive_pulid_weight 540→545,
MOTION_FIDELITY_FLOORS 395→400, MAX templates end 370→375) — cited 20+
times across ARCHITECTURE.md + PM incl. symbol-adjacent forms like
"### 9.2 \`classify_shot_type\` keyword map ([workflow_selector.py:411-432])"
— and `check_doc_claims` flagged ZERO of them, both before and after my
hand-fix. These anchors appear entirely un-bound, not just
direction-blind. Repro: `git show ec21c0a -- ARCHITECTURE.md
docs/PROGRAM-MANUAL.md` has the full before/after pairs.

**Status:** Pass-A rerun mid-flight (cand0-2 saved, ~7 min/cand, halt check
at n=4) — cand2 eyeballed: BOTH faces coherent, Aria's trained-in wardrobe
bleeding through = LoRA active, zero disintegration. Fix holds live. Next:
S2 spike (post-Pass-A to keep the VRAM peak uncontaminated) → S3 stacking
sweep (man LoRA char_lora_man_v1 FAL-trained + pod-placed this session,
TOKman, user-funded) → local arc scores → spec §6/runbook exit records.
FAL price VERIFIED $0.08/img (was $0.04 estimate) — cost_tracker +
spec rows updated 78c1053; the 3-session dashboard ask is discharged
list-price-basis. Pod stop/keep: user authorized full pod work this
session; I notify them the moment the pod is no longer needed.

Cursor at send: 2026-06-11T01:30:23Z
