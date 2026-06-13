# Operator → Director: FULL tier-unification critique (user-requested; relaying for your production-driver build) — verdict = neither full-unify nor toggle-post-passes; the realism path is production-base SAMPLING + grafted max IDENTITY stack. Concrete graft + node-collision map below.

**When:** 2026-06-13T06:50:00Z · **From:** operator (online)

User asked me for a pros/cons critique of unifying the two tiers; I ran a dialectic (3 steelmanned positions, each adversarially stressed, grounded in the live code — wf_f353d3ad). Relaying the full thing because it bears directly on your production-driver build. Caught up to your 06:41:08Z (0 unread).

## The three architectures (each adversary verdict: "viable, but key assumption FAILS on a code fact")
- **Full-unify (one configurable tier):** PRO — kills the 8/22 divergent-class drift, consolidates 2 injection codebases, makes features dials. CON/BREAK — node 100 ApplyPulid vs ApplyPulidFlux (different input keys), node 17 BasicScheduler (has `model` input the IP-Adapter rewire needs) vs OptimalStepsScheduler (AYS, FLUX-required), nodes 500/501/502 RealESRGAN vs SUPIR at the SAME IDs, and a `ays_steps` vs `steps` param-key mismatch that silently defaults production to 28 steps. Forced single-choice regresses one tier on live HW. **Don't.**
- **Keep-separate (status quo):** PRO — proven path stays the stable fallback, small blast radius. BREAK — the production path **can't use the char LoRA at all** (verified: pulid.json = 22 nodes, NO LoraLoader, NO node 700, PuLID = ApplyPulid; generate_ai_broll forwards char_lora_* ONLY to the max branch, docstring "max tier only"). So the realism memory's "production pulid.json + char LoRA @0.55" recipe is UNWIRED.
- **Selective-hybrid (production base + opt-in max features):** was my lean — PRO decouples upscale from re-detail. **BREAK / NOW REFUTED by your SUPIR-off burn:** the over-cook is STRUCTURAL to the max base graph (Design-A no-LoRA+SUPIR over-cooked; this LoRA+no-SUPIR over-cooked), not the post-passes. Toggling post-passes can't fix a base-graph over-cook. Also the same 500/502 collision would corrupt _inject_post_passes on pulid.json.

## Universal blocker (confirmed by all 3 adversaries + my spot-check)
The two graphs reuse node IDs for incompatible classes: 100 (ApplyPulid vs ApplyPulidFlux), 17 (scheduler), 500/501/502 (RealESRGAN vs SUPIR). Any merge/graft must resolve this.

## Recommendation = exactly your next step, framed as the DEEPER hybrid
Not "unify," not "toggle" — **graft the max IDENTITY stack onto the production SAMPLER:**
- KEEP from production (pulid.json) — the non-over-cooking realism core: BasicScheduler + dpmpp_2m + 25 steps + PAG + RealESRGAN 500/501/502 (these are NOT the over-cook source; keep them, no SUPIR needed).
- GRAFT from max — the binding stack that gave man 0.870: swap the PuLID loader trio to Flux (PulidFluxModelLoader / PulidFluxEvaClipLoader / PulidInsightFaceLoader), node 100 ApplyPulid→ApplyPulidFlux, splice the dual (node 103, 103.model=['100',0]), insert LoraLoader node 700 (char_lora_man_v1 @0.55) upstream of both PuLID applies, prepend TOKman.
- COLLISION WARNING for your build: pulid.json's 500/501/502 are RealESRGAN — do NOT let any max-tier _inject_post_passes touch them (it'd write SUPIR params into ImageScale or pop the chain → dangling SaveImage ref). Keep the production save chain.
- The over-cook being base-structural means the win comes from the SAMPLER swap (max AYS/dpmpp_3m_sde + hires-fix@0.40 → production dpmpp_2m/25steps/PAG), while binding comes from the grafted identity stack. That's the testable hypothesis your production driver embodies.

## Two flags for the build
1. **facedetailer-off probe first** ($0.03) — concur; definitively closes whether FaceDetailer contributes before you commit to the harder build. If still over-cooked → base-graph confirmed, graft is unavoidable.
2. **Before any N=4 GO on the production render:** the binding metric is non-deterministic on noisy renders (man 0.64/0.68/0.81 on passb_q, 5 phantom detections). A clean production render should detect fewer phantoms (fewer over-cook artifacts), but pin deterministic figure-selection regardless — don't read a GO threshold off a wobbling number.

Flag me for Rule #22 when you freeze the production driver — new graph + injection code = real new surface. Pod RUNNING+BILLING.

Cursor at send: 2026-06-13T06:41:08Z
