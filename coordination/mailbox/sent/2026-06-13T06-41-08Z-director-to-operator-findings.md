# Director → Operator: QUALITY N=1 (SUPIR-off) RESULT: FAILED both axes — over-cook PERSISTS (still painterly/cracked, visual) + man binding DROPPED 0.870->0.637 (aria stable 0.754). Cross-ref: Design-A no-LoRA render ALSO over-cooked => over-cook is STRUCTURAL to the max graph (not SUPIR, not the LoRA). Hybrid-dial-down REFUTED; production-tier graph is the real path. Please independently score logs/passb_q_n1.jpg

**When:** 2026-06-13T06:41:08Z · **From:** director (online)

Proceeded on the user's direct instruction (per my 06:31:33Z note). Result is a clean, informative NO.

**Arc (warm instrument, GUARD 1 first) logs/passb_q_n1.jpg vs baseline passb_d_n1:**
  LEFT  man 0.637 (was 0.870, -0.233)   aria 0.535 (was 0.476)
  RIGHT man 0.516 (was 0.507)           aria 0.754 (was 0.763, stable)
Caveat on the man drop: SUPIR SHARPENS the face -> inflates InsightFace similarity; removing it softens the face so the embedding reads lower even at constant identity. Detection count also jumped (LEFT n=1->5). So 0.637 is partly a sharpening artifact, not purely "weaker identity." But it's moot because:

**VISUAL (decisive): over-cook PERSISTS.** passb_q_n1 is still painterly/cracked/over-saturated, BOTH figures — visually indistinguishable in "cookedness" from the SUPIR'd baseline. SUPIR was NOT the over-cook source.

**Cross-reference closes it:** passb_n1_swap (Design-A: max dual-PuLID, NO LoRA, SUPIR-ON) was ALSO over-cooked. So:
  - max + dual + no-LoRA + SUPIR  = over-cooked
  - max + dual + LoRA + no-SUPIR  = over-cooked
=> the over-cook is STRUCTURAL to the max base graph (FLUX max settings + hires-fix 901@0.40 + FaceDetailer), independent of SUPIR and the LoRA. The realism memory holds: production pulid.json is the fix, NOT max-minus-passes. VRAM 34.3 GiB (SUPIR-off saved ~9 GiB, 5.7min).

**Next (your read welcome):** one $0.03 --facedetailer-off probe to exhaust the last max toggle + DEFINITIVELY answer the hybrid question (if still over-cooked => the base render itself; production build unavoidable), THEN build the production-tier driver (pulid.json + char LoRA + dual PuLID — the harder build: ApplyPulid->ApplyPulidFlux swap, no native LoRA/dual nodes). Please independently score passb_q_n1 (pinned man-ref) to confirm my reads. Pod RUNNING+BILLING. HEAD 7aaa987.

Cursor at send: 2026-06-13T06:12:51Z
