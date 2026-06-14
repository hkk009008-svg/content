# Director → All: Pair-A ADR-024 realism burn DONE — N=1 "double-man" CORRECTED; Route-B favored; pod LEFT UP

**When:** 2026-06-14T17:42:12Z · **From:** director (online → wrapping)

**Pair-A pivoted to option C (ADR-024 dual-char pod-realism burn), user-driven; NO Wave-2 code this session.** Relaunched ComfyUI on pod 07ed667 (502→200, census 1106), Rule #22 $0-cleared, burned an **8-config sweep** (strength 0.55–0.95 × man-weight 0.85/1.0, seed 990011; render/score artifacts are local/gitignored).

**Finding:** REALISM = WIN (clean production sampler renders photoreal dual-char). Clean dual-binding is blocked by the **global man-LoRA**.

**@whoever next owns the Wave-3 plan — CORRECTION to `docs/superpowers/plans/2026-06-15-dual-char-attn-mask-binding.md` §2 (added a §9 addendum + corrected `[[realism_production_plus_char_lora]]`):** the "double-man at default" was a ComfyUI **CACHE HIT** (`passb_prod_n1_00046.png`), NOT the default graph. Fresh at strength 0.55: **distinct woman binds (aria-L 0.757) + man UNDER-binds (man-R 0.490).** man-R climbs to **0.850 at strength 0.95** but BLEEDS onto aria (two bearded men; visual NO-GO). man-weight is a dead lever. ⇒ the man **needs a LoRA** → **Route A (drop LoRA + masked PuLID) will UNDER-bind; favor Route B (aria LoRA + mask both).**

**⚠ POD 07ed667 LEFT UP + BILLING** — surfaced to the user to stop (cannot stop it from here).

**Wave-2 ack:** Pair-A queue untouched (`idgate-failopen` = cross-lane Tier-A co-sign owed); user directed realism then "wrap".

Cursor: 2026-06-14T16:38:57Z
