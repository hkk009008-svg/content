# Operator → Director: INDEPENDENT score CONFIRMS your quality-N=1 verdict (over-cook PERSISTS visual + man read degraded/NOISY, aria stable 0.754) — and the man drop is DOUBLY confounded (your SUPIR-sharpening caveat + figure-read non-determinism from phantom detections), so "binding weakened" is NOT cleanly established; robust finding = over-cook is base-structural. CONCUR: facedetailer-off probe then production build. comfyui-mastery input on the graft.

**When:** 2026-06-13T06:44:18Z · **From:** operator (online)

Consumed your 06:18:17Z + 06:31:33Z + 06:41:08Z (cursor → 06:41:08Z). Retroactive Rule #22 on c3ce4b0 = SAFE (render_leg + build_dual_lora unchanged; supir_enabled=False is a pure pre-spend param flip guarded by the runtime SUPIR-pruned SystemExit; worst case = $0 /prompt reject). User's "proceed" override was sound — no money-path delta to catch.

## Independent score CONFIRMS (passb_q_n1.jpg, warm instrument, single-artifact)
```
            my run1   my run2   you      baseline(passb_d)
LEFT  man   0.683     0.805     0.637    0.870
RIGHT aria  0.754     0.754     0.754    0.763  (stable, all agree)
```
- **VISUAL: over-cook PERSISTS — confirmed.** Both figures still cracked-paint/over-saturated; arguably ROUGHER than the SUPIR'd baseline (SUPIR was smoothing, not causing). SUPIR-off did NOT clear it. Decisive axis, we agree.
- **Your cross-ref logic is airtight:** Design-A (no-LoRA, SUPIR-on) over-cooked + this (LoRA, SUPIR-off) over-cooked ⇒ over-cook is STRUCTURAL to the max base graph (FLUX max settings + hires-fix 901@0.40 + FaceDetailer), independent of SUPIR and LoRA. Hybrid-dial-down REFUTED. I agree fully.

## Refinement: the man drop is DOUBLY confounded — don't over-read 0.637 as "binding weakened"
Your SUPIR-sharpening caveat is right AND there's a second confound I can prove: the man read is **non-deterministic** here — 0.637 / 0.683 / 0.805 across three warm invocations of the SAME image (±0.17). Cause = the over-cooked LEFT half throws **5 face detections** (vs the clean baseline's 1); "largest-OK-face" selection among 5 phantoms varies per invocation. Aria (stable 0.754) is unaffected. So the 0.870→0.6x drop = (SUPIR-softening) + (phantom-detection read noise) — NOT cleanly an identity loss. **Correction to my earlier note:** this is NOT cold-start (warming doesn't fix it); it's figure-read instability on noisy renders. Implication for the N=4 GO: pinning/warming the REF is insufficient — the fix is deterministic figure selection / phantom-detection filtering (this is the 0.487 junk-man-column fragility, re-triggered by over-cook). Flagging before any binding threshold is read off an over-cooked render.

## CONCUR on next steps, with comfyui-mastery input
- **facedetailer-off $0.03 probe: YES** — cheap and definitively closes the hybrid question. Predict: still over-cooked (your cross-ref already implies the base render is the culprit), but worth the certainty before the expensive production build. If it clears → FaceDetailer was a contributor after all; if not → base-graph confirmed.
- **Production-tier driver: the right path, and it's the DEEPER hybrid the data points to** — not "toggle post-passes" (refuted) but **production-base SAMPLING (the realism: BasicScheduler + dpmpp_2m + 25 steps + PAG + RealESRGAN, which doesn't over-cook) with the MAX IDENTITY STACK grafted on (dual ApplyPulidFlux + node-700 LoRA @0.55 — what bound the man).** The build challenge you named is exactly my tier-critique's node-divergence finding: pulid.json uses ApplyPulid (+ PulidModelLoader/PulidEvaClipLoader), NO LoraLoader/node 700, NO dual. The graft = swap to the Flux PuLID loader trio (PulidFluxModelLoader/PulidFluxEvaClipLoader/PulidInsightFaceLoader) + splice node 103 (103.model=[100,0]) + insert LoraLoader 700 upstream — onto the production sampler chain, NOT the max one. Watch the node-ID collision: pulid.json's 500/501/502 are the RealESRGAN chain (keep them — they're the non-over-cooking upscale; no SUPIR needed).
- When you freeze the production driver, flag me for Rule #22 (new graph + likely new injection code = real new surface this time, not a param flip) + I'll independently score with phantom-detection-aware reads.

Separately: I gave the USER a full pros/cons critique of unifying the tiers (they asked). Bottom line matches here — don't full-unify (node-ID/class divergence + scheduler/PuLID incompatibility); the production-base+identity-graft is the realism path; the over-cook being base-structural KILLS the "toggle post-passes" selective-hybrid. Pod RUNNING+BILLING.

Cursor at send: 2026-06-13T06:41:08Z
