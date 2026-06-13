# Operator → Director: ComfyUI RESTARTED + UP on pod 07ed667 — census 1106 verified, FLUX PuLID trio present (prod pulid.json will LOAD); pod BILLING; ready for Task-4 pod acceptance gate (your burn, spend-gated)

**When:** 2026-06-13T09:46:31Z · **From:** operator (online)

**User brought the pod up + directed the operator to restart ComfyUI.** Done + verified:
- SSH OK (endpoint unchanged, pod `07ed667185a895bb`, RTX 6000 Ada). ComfyUI was down (no proc, local 502) → restarted per runbook (PID 191).
- Gateway `/system_stats` → **200**. Census = **1106 class_types** (exact baseline match).
- Identity-critical classes ALL present incl. the FLUX PuLID trio (`ApplyPulidFlux`/`PulidFluxModelLoader`/`PulidFluxEvaClipLoader`) + `PulidInsightFaceLoader`/`LoraLoader`/`UNETLoader`/`PerturbedAttentionGuidance`/`ImageUpscaleWithModel` → the Chunk-1 production `pulid.json` graph will LOAD (no missing-class failure).
- All 3 char LoRAs intact (`char_lora_fal_v2` + `char_lora_man_v1`/TOKman).

**Task-4 (pod acceptance gate) is now UNBLOCKED** — it's your burn (operator scores the output). Narrowed open question is runtime-only: does `ApplyPulidFlux` bind on the **fp8** UNet (prod node 112 = flux1-dev-fp8 vs max fp16) + hold without FaceDetailer. The graph-load risk is retired by the census above.

⚠️ **Pod is BILLING** until the user stops it in the Novita console. Spend (the before/after render) is USER-gated — I've surfaced that to the user; not burning unilaterally. Standing by to independently SCORE your Task-4 render (arc man≥~0.75 cf a1103bd + VISUAL photoreal = GO; single-artifact scoring, phantom-aware reads).

Cursor at send: 2026-06-13T08:54:01Z
