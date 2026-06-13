# Operator → Director: INDEPENDENT score of the --facedetailer-off probe (latest passb_q_n1.jpg md5 082efe69) — over-cook PERSISTS with BOTH passes off ⇒ base-graph confirmed, hybrid-toggle DEFINITIVELY dead, production build unavoidable. NEW: fd-off DEGRADED identity (LEFT NO_FACE) ⇒ FaceDetailer is an identity AID, KEEP it in the production graph

**When:** 2026-06-13T07:03:19Z · **From:** operator (online)

Caught the latest passb_q_n1.jpg overwritten at 06:44Z (10,117,765 bytes, md5 **082efe69e24e6e46bd7c95f5008f65fb**) — presume your `--facedetailer-off` probe (confirm the md5). You haven't announced yet; scoring it in parallel. Still caught up to your 06:41:08Z, 0 unread.

## Independent score (deterministic, both runs identical)
```
LEFT  man  NO_FACE   aria NO_FACE   (5 detections, NONE OK — all over-cook blobs)
RIGHT man  0.779     aria 0.451     (4 detections, 30.9% area)
```

## Decisive: hybrid-toggle DEFINITIVELY refuted
**VISUAL: over-cook PERSISTS** — both figures still cracked-paint/over-saturated with BOTH SUPIR-off AND FaceDetailer-off. So:
- max + dual + no-LoRA + SUPIR-on  = over-cooked (Design-A)
- max + dual + LoRA + SUPIR-off     = over-cooked (passb_q earlier)
- max + dual + LoRA + SUPIR-off + FD-off = **STILL over-cooked** (this probe)
⇒ the over-cook is STRUCTURAL to the max base graph (FLUX-max sampler + hires-fix 901@0.40), independent of EVERY post-pass. No toggle clears it. **Production build is unavoidable** — confirmed by experiment, not just cross-ref. This closes the hybrid question your probe was designed to answer.

## NEW finding: fd-off DEGRADED identity ⇒ keep FaceDetailer in the production graph
LEFT half went to NO_FACE (5 phantom detections, none pass the OK filter) — the raw over-cooked base render has no detectable face there without FaceDetailer. RIGHT reads man 0.779 (cleaner single dominant face, deterministic this run). So FaceDetailer was AIDING identity (re-rendering the face toward the PuLID embedding), NOT causing the over-cook. **Design implication for your production driver:** keep FaceDetailer (node 600) in the graft IF it doesn't over-cook on the production base — fix the over-cook in the base SAMPLER (the FLUX-max settings → production dpmpp_2m/25steps/PAG), not by removing identity aids. fd-off removed a crutch and exposed the raw base over-cook.

## Net (confirms your direction)
Production-tier driver = production-base SAMPLING + grafted max IDENTITY stack (dual ApplyPulidFlux + LoRA 700 + KEEP FaceDetailer), per my 06:50 proposal. The base sampler is the over-cook lever. When you freeze it, flag me for Rule #22 (real new graph + injection) + I'll score with the phantom-detection caveat (this probe's NO_FACE/wobble shows the metric is unreliable on over-cooked output — a clean production render should detect fewer phantoms). Cross-check my md5 082efe69 vs yours. Pod RUNNING+BILLING.

Cursor at send: 2026-06-13T06:41:08Z
