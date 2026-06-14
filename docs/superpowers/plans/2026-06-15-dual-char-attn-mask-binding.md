# Experiment Plan — Dual-Character Binding via Spatial `attn_mask` Confinement

> **Status:** planned (coordinator Session-10, 2026-06-15) for a future **Pair-A** pod session.
> **Lane:** Pair-A (image / identity / realism). **Wave:** 3 (capability levers, pod-gated, best-effort).
> **Prereqs:** pod STARTED + ComfyUI UP (gateway 200) + user spend authorization. Builds on the
> 2026-06-15 ADR-024 N=1 result ([[realism_production_plus_char_lora]]).

## 1. Goal

A single production-tier image with **two distinct, correctly-placed photoreal identities**:
the woman (aria, `char_b9c8bcfe9af0`) on the **left**, the man (`p12_fresh_face_man.jpg`) on the
**right** — both binding strongly, with the clean production photoreal look (no max-tier over-cook).

**GO criteria (visual is PRIMARY per the project's "visual verdict overrides embeddings" rule):**
1. **Visual:** left figure reads as the woman, right figure reads as the man, both photoreal skin, no over-cook. (This is the criterion the N=1 failed.)
2. **Arc (secondary GUARD):** `aria-LEFT ≥ ~0.75` **AND** `man-RIGHT ≥ ~0.75` (cf. man-0.870 max baseline; thresholds per `ai-video-gen` identity table). Pin **deterministic figure-selection** before any N=4 GO (the binding metric is non-deterministic on over-cooked renders — `_arc_score_session.py --halves`).

## 2. What the N=1 established (don't re-derive)

ADR-024 graft (`scripts/_prod_dual_lora_pulid.py`, seed 990011, `logs/passb_prod_n1_00046.png`):
- **Realism = WIN.** The graft (FLUX identity stack on the clean production sampler) renders production-grade photoreal — it sidesteps the structural max-tier over-cook (hires-901 + 28-step sampler). This half is solved.
- **Dual-binding = FAIL.** BOTH figures bound to the **man** (a double-man; the woman never rendered). **Root cause:** the man identity is applied **three GLOBAL ways** — `char_lora_man_v1` model-patch (node 700) + the `TOKman` trigger in the prompt (global CLIP) + the man PuLID (node 103) — while the woman has **only** a PuLID. A global LoRA + trigger beats a single local PuLID everywhere on the canvas. This is the [[project_secondary_char_needs_lora]] problem (PuLID-alone too weak for the 2nd identity).

## 3. The lever — and why asymmetric weights are NOT it

**Asymmetric PuLID weights will not fix this** — the man's dominance comes from the **global** LoRA + trigger (they patch the whole model/CLIP), not from PuLID weight. Two routes actually address it:

- **Route A (THIS plan — cheap, no training): spatial `attn_mask` confinement + drop the global man LoRA/trigger.** `ApplyPulidFlux` has an **optional `attn_mask: MASK`** input (verified against the pod's `/object_info`, 2026-06-15). Confine aria's PuLID to the LEFT half and the man's PuLID to the RIGHT half, and **remove the global man LoRA (node 700) and the `TOKman` trigger** so neither identity has a global advantage. Pure dual *masked* PuLID on the clean production sampler.
- **Route B (fallback — needs training): train an aria LoRA** so both characters have equal-strength LoRAs, then mask both PuLIDs. More robust but requires a pod-side / FAL LoRA train (cf. `scripts/_fal_lora_train.py`, ~9 min). Only pursue if Route A under-binds.

Start with **Route A** — it's graph-wiring only (squarely `comfyui-mastery`), no training, and directly tests whether spatial confinement alone separates the identities.

## 4. Graph construction (Route A)

New driver `scripts/_prod_dual_masked_pulid.py` — fork `scripts/_prod_dual_lora_pulid.py` and change:
- **Base:** production `pulid.json` (clean sampler — BasicScheduler + dpmpp_2m + sgm_uniform + 20 steps + PAG + RealESRGAN; NO hires/SUPIR/FaceDetailer). Keep the $0 pre-submit guards that abort on any over-cook node (600/780/900/901/950).
- **DROP node 700 (man LoRA)** and **drop the `TOKman` prefix** from the node-122 prompt. Prompt = neutral: `"a woman with short dark wavy hair on the left and a middle-aged man with a grey beard on the right, ..."` (+ the production photorealism style suffix).
- **Dual masked `ApplyPulidFlux`:**
  - node 100 = aria PuLID, `image=<aria_ref>`, `weight≈0.9`, `start_at=0.0`, `end_at≈0.9`, **`attn_mask=<LEFT mask>`**.
  - node 103 = man PuLID (spliced after 100), `image=<man_ref>`, `weight≈0.9`, `start_at=0.0`, `attn_mask=<RIGHT mask>`. Rewire node 100's model-consumer (PAG node 301) → 103 (same splice the prior driver did).
- **Masks (node wiring):** two options —
  - (a) pre-make two PNGs at **1344×768** (the node-102 `EmptyLatentImage` generation resolution — NOT the 2688×1536 RealESRGAN output): `mask_left.png` = white left half / black right, `mask_right.png` = inverse. Upload via `s2._upload` and load with **`LoadImageMask`** (channel=`red`) → feed each PuLID's `attn_mask`.
  - (b) build them in-graph with **`SolidMask` + `MaskComposite`** (no upload). (a) is simpler/deterministic; prefer it.
  - Mask geometry: a hard 50/50 vertical split is the v1; if seams/bleed appear, soften with a feathered boundary or a slight center gap. `attn_mask` is resampled into PuLID attention space, so it tracks the generation latent, not the upscaled output.

## 5. Protocol

1. **N=1 visual smoke** (fresh seed — see cache gotcha §6): render, retrieve, eyeball — woman-left? man-right? both photoreal? If the masks are mis-sized you'll see one identity bleed across the seam or a blank half.
2. If visual GO → **N=4 seed-robustness** (`SEEDS[:4]`), with deterministic figure-selection pinned, then `_arc_score_session.py --halves --artifacts 'logs/passb_masked_n*.jpg'` → check `aria-LEFT` and `man-RIGHT` both ≥ ~0.75.
3. **Record per R-MEASURE:** commit the driver + the masks + the arc numbers to `logs/`; GO → improvement note, HOLD/inconclusive → row `DEFERRED` with the artifact (Wave-3 acceptance bar — a HOLD does not block).

## 6. Preconditions & gotchas

- **Pod:** must be STARTED + ComfyUI UP (gateway `/system_stats` → 200) + **user spend authorization** (render spend is USER-gated, never burned unilaterally). Re-confirm SSH only if you need to place assets pod-side; the burn itself runs via the HTTP gateway. Verify census = 1106 + `ApplyPulidFlux` present (it was, 2026-06-15).
- **⚠ ComfyUI cache-hit false-fail (cost me the N=1 read):** `render_leg` polls `/history`; a fully-cached prompt returns `status=success` with **empty `outputs`** → it false-fails "completed with NO images" even though the file was written. **Mitigations:** (a) use a **fresh seed** each run to force a cache miss; (b) if it false-fails, the image still exists — fetch `FLUX_PuLID_<NNNNN>_.png` (next counter) via `GET {gateway}/view?filename=...&type=output`. Consider hardening `render_leg` to also accept cached outputs / fall back to `/view` by counter.
- **Mask resolution:** 1344×768 (node 102), NOT the output size. A wrong-size mask is the most likely v1 failure.
- **Don't re-add a global vector:** if you bring the man LoRA back (Route B territory), you reintroduce the global-dominance bug unless aria gets an equal LoRA. Keep Route A LoRA-free.

## 7. Assets

| Asset | Path / source | Status |
|---|---|---|
| aria ref | `domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg` | exists |
| man ref | `logs/p12_fresh_face_man.jpg` | exists |
| left/right masks (1344×768) | to create (`logs/mask_left.png`, `logs/mask_right.png`) | TODO |
| driver | `scripts/_prod_dual_masked_pulid.py` (fork of `_prod_dual_lora_pulid.py`) | TODO |
| pod nodes | `ApplyPulidFlux`(+attn_mask), `LoadImageMask`, `SolidMask`, `MaskComposite` | present on pod |

## 8. Cost / risk

Pod-gated, best-effort (Wave-3). N=1 smoke ≈ one render; N=4 ≈ four. Risk is low-spend, graph-only (no training in Route A). If Route A under-binds after weight/mask tuning, escalate to Route B (aria-LoRA train) as a separate decision — that's the heavier investment and a fresh spend gate.

## 9. Empirical addendum — director-1 fresh 8-config sweep (2026-06-15)

After this plan was authored, director-1 relaunched ComfyUI fresh and burned a clean **8-config sweep** of `_prod_dual_lora_pulid.py` (seed 990011; artifacts local/gitignored: `logs/sweep_s*_mw*.jpg`, montage `logs/sweep_montage.jpg`, scores `logs/halves_rescore_20260615.json`). It **corrects §2's N=1 reading and re-weights the routes:**

- **§2's "default = double-man" was a CACHE HIT, not the default graph.** Fresh at the documented default (strength 0.55, man-weight 0.85): a **distinct woman who binds (aria-LEFT 0.757)** + a **man who UNDER-binds (man-RIGHT 0.490)** — NOT a double-man. The `passb_prod_n1_00046.png` double-man was a stale cache of a *higher-strength* render.
- **Strength series (man-weight 0.85):** man-RIGHT 0.490→0.495→0.514→0.519→**0.850** at strength 0.55→0.65→0.75→0.85→**0.95**; aria-LEFT 0.757→0.748→0.702→0.696→**0.659**. The **double-man bleed is a strength-0.95 behavior** (man binds 0.850 but overwrites aria — visual NO-GO).
- **man-weight is a dead lever** (man flat ~0.49 from 0.85→1.0; aria degrades). §3's "asymmetric PuLID weights won't fix it" is confirmed empirically.
- **⇒ Route A risk:** the man **needs a LoRA to cross 0.75** (PuLID-alone floors ~0.49 even at man-weight 1.0). Dropping the man LoRA entirely (Route A) will likely leave him **under-bound** — masking confines *where* each PuLID acts but can't make the man's PuLID-alone bind. **Recommend going to Route B sooner** (aria LoRA so both identities have equal-strength LoRAs, then mask both PuLIDs), or a Route-A+masked-man-LoRA hybrid. The crux is spatial confinement of the man's *global LoRA*, which `attn_mask` (a PuLID input) does not address.
