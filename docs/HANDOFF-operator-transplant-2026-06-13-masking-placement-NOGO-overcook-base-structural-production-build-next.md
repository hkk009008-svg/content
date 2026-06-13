# Operator transplant handoff — 2026-06-13 (PM): Design-D binding HOLDS (man 0.870) → masking PLACEMENT-INERT (NO-GO) → over-cook STRUCTURAL to the max base graph (every post-pass toggle ruled out by experiment) → **production-tier hybrid driver `_prod_dual_lora_pulid.py` BUILT + FROZEN (c5d0a80), operator Rule #22 PRE-STAGE = SAFE, NOT burned.** Pure verification seat; clean two-seat convergence all session.

**Seat:** operator · **Session:** 2026-06-13 ~05:24Z → ~07:12Z
**HEAD at operator wrap:** `2a62ac0`. **CURRENT HEAD = `c5d0a80`** (director's wrap landed 3 min after mine — run `git log --oneline -6` on arrival; HEAD may advance further if a seat resumes). My commits (all coord/verification — NO code touched): `588bdef` `eda2e4a` `99aea9d` `529c75b` `989206b` `dacf06a` `2a62ac0`. **~42 ahead of origin, push USER-gated.**
**Gates:** ci_smoke **EXIT=0 OK** (firsthand at wrap). Suite **2244 passed / 2 skipped** (director recount at c5d0a80). PROGRAM-MANUAL ~55 advisory doc drifts (fix-on-touch).
**Cursor: 2026-06-13T07:09:20Z, 0 unread** (consumed the director's wrap reply).
**Director: WRAPPED `c5d0a80`** (symmetric — user "handoff" to both). They built the production driver, OFFLINE after. No two-seat blindness this session — I proved them live via heartbeat, came online + announced, and we converged independently on every finding.
**Pod 07ed667: RUNNING + BILLING** (user stops in Novita console). Session pod spend ~$0.09.

## ⭐ #1 PICKUP — the production driver is FROZEN and Rule-#22-cleared; the next director BURNS it
`scripts/_prod_dual_lora_pulid.py` @ **c5d0a80** (`git show c5d0a80 --stat` to confirm) — the realism path, NOT yet burned. It implements the operator graft proposal:
- **KEEP** the production sampler chain (loads `pulid.json` directly: BasicScheduler + dpmpp_2m + sgm_uniform + **20 steps** [baseline; `workflow_selector.py` overrides to 25 for close-up/landscape] + PAG + RealESRGAN 500/501/502 — the non-over-cooking core).
- **GRAFT** the proven identity stack: copy nodes 99/100/101/700 VERBATIM from `pulid_max.json` (Flux PuLID loader trio + node 100 `ApplyPulidFlux` + LoRA 700 @0.55), splice node 103 man (`103.model=['100',0]`), TOKman prompt, `start_at=0.0` (NOT the SDXL 0.3 bug).
- **COLLISION-SAFE by construction:** never calls `_inject_post_passes`/`_prune_unavailable`, so the RealESRGAN 500/501/502 chain is untouched (my node-ID collision warning is moot here).
- **FaceDetailer (600) is OMITTED — and is an ABORT guard** (`_prod_dual_lora_pulid.py:120` aborts if any of 600/780/900/901/950 present). This SUPERSEDES my earlier "keep FaceDetailer" note: the director chose isolate-one-variable. **OPEN QUESTION for the first burn: does the CLEAN production base bind the man WITHOUT FaceDetailer?** (My fd-off=NO_FACE finding was on the OVER-COOKED max base — may not apply to a clean base; pulid.json ships clean portraits. If the man reads weak/NO_FACE, the next iteration adds node 600 back.)

**OPERATOR RULE #22 PRE-STAGE = SAFE** (done this session, the director invited it): money-path = `render_leg` UNCHANGED (my prior SAFE) + 2 timeout'd `s2._upload` calls; `build_prod_dual_lora` is pure offline graph assembly (no network); **6 pre-submit asserts fail $0 before `/prompt`** (node-presence, node-99 PulidFluxModelLoader, 100/103 both ApplyPulidFlux, start_at≠0.0 SDXL-bug guard, over-cook-node-present abort, RealESRGAN-500 intact) + `render_leg`'s rejected-graph guard. No new spend path; only carried advisory = idempotency (deliberate re-run re-spends ~$0.03/seed). **Re-confirm the c5d0a80 blob is unchanged before the burn, then it's cleared.**

**First burn (next director, on user spend-go):** `PYTHONPATH=. .venv/bin/python scripts/_prod_dual_lora_pulid.py --n 1` (~$0.03, seed 990011 → `logs/passb_prod_n1.jpg`). Read **arc FIRST** (man ≥~0.75 cf baseline 0.870) + **VISUAL photoreal = the PRIMARY GO** (does the production sampler kill the over-cook while the graft holds the binding?). Then N=4. GO bar = STRICT intended-slot `binding_ok` ≥3/4 BOTH + visual two-distinct + photoreal. **Operator: independently score it** (single-artifact, phantom-aware — see #2).

## ⭐ #2 — INSTRUMENT DEBT: fix deterministic figure-selection before any N=4 GO threshold
The binding metric is **non-deterministic on over-cooked/noisy renders**: man read 0.637/0.683/0.805 across 3 warm invocations of the same `passb_q_n1.jpg` (±0.17). Cause = the over-cooked half throws **5 phantom face detections** (vs a clean render's 1) and "largest-OK-face" selection varies per invocation. NOT cold-start (warming the ref does NOT fix it — it's FIGURE selection, not the ref). aria (1-detection ref) is rock-stable.
**Fix target:** `identity/validator.py` `classify_detection` + `_figure_read_score` (introduced 312f6d2) — add deterministic tie-breaking / confidence-threshold pruning so phantoms don't win largest-OK. See `logs/halves_rescore_20260613.json` for the 5-detection pattern. A clean production render should detect fewer phantoms, but pin it before any binding GO threshold (this is the 0.487 "junk man-column" fragility resurfacing).

## ⭐ #3 — DATA-INTEGRITY: production pulid.json PuLID is a FLUX NO-OP (director's wf_963a4a8a Lens A)
`pulid.json` node 100 = `ApplyPulid` (SDXL-era node) — on FLUX it's ~ZERO face-lock; production COMFYUI_PULID renders have effectively been **plain FLUX txt2img with no real identity lock.** This is (a) WHY the c5d0a80 graft swaps to `ApplyPulidFlux` (mandatory, not optional), and (b) a **latent production data-integrity bug** for any shipped COMFYUI_PULID render — verify + fix in the production path proper (the graft driver is a Pass-B experiment, not yet the production codepath). Cross-check the director's wf_963a4a8a Lens A before acting.

## Established facts (all operator-verified this session)
- **Design-D binding HOLDS:** man **0.870** (LoRA @0.55 + dual ApplyPulidFlux + TOKman), aria 0.763 — two distinct identities. **VERIFY-BEFORE-TRUSTING:** the 0.870/0.763 baselines for `passb_d_n1.jpg`/`passb_dm_n1.jpg` have NO surviving `halves_rescore` JSON (the file now holds only the fd-off `passb_q_n1.jpg`, which I overwrote) — re-run `scripts/_arc_score_session.py --halves --artifacts logs/passb_d_n1.jpg` to reproduce before treating as GO ground truth.
- **Masking = NO-GO for placement** (`48ad08b`): `attn_mask` is placement-INERT for a bound id (arc identical to baseline, md5 differs; even PuLID-only aria didn't move). Placement is a prompt-order/seed problem, DEFERRED (composition, not a blocker).
- **Over-cook STRUCTURAL to the max base graph** (3 configs all over-cooked: Design-A no-LoRA+SUPIR; SUPIR-off; SUPIR-off+FD-off) ⇒ selective-hybrid "toggle post-passes" DEFINITIVELY refuted; the lever is the base SAMPLER (FLUX-max + hires-fix 901@0.40), which is exactly what c5d0a80 swaps out.
- **Production tier CANNOT use the char LoRA** (verified: pulid.json no LoraLoader/no node 700; `generate_ai_broll` forwards `char_lora_*` only to the max branch) — so a naïve "pivot to production" loses the LoRA; the graft is the fix.

## Sharp edges (this session)
1. **Single-artifact scoring only.** `--halves --artifacts logs/passb_prod_n1.jpg` (single path OR single glob) is correct; `--artifacts a.jpg b.jpg` (multiple paths) cross-contaminated the man reads once. Score one render per invocation.
2. **Verify against the committed blob** (`git show <sha>:path`), not the working tree, when auditing a frozen driver — peer WIP can sit on top.
3. **Renders overwrite by save_prefix** — the fd-off probe overwrote `passb_q_n1.jpg`; md5 + size are the only way to tell which render you're scoring. Capture md5 for cross-seat cross-check.
4. **A render can land in the watcher-arm gap** — arm the render watcher BEFORE the director burns, or snapshot mtimes; I missed the fd-off probe's arrival and caught it only by a manual state check.
5. **`md5`/`stat -f` are BSD-form on macOS** (`md5 <f>`, `stat -f %m/%z`), not GNU.
6. **Two-seat convergence worked** — director + operator independently reached the LoRA-bleed insight, the placement-inert verdict, AND over-cook-base-structural. Lean into independent scoring; the check IS the value.

## What this session did (chronological)
R-START (smoke OK, proved director live, came online 588bdef) → verified Design-D firsthand → Rule #22 pre-stage adversarial audit `wf_9519de54` = SAFE, freeze-before-audit handshake, final SAFE on 48ad08b (99aea9d) → masking N=1 independently confirmed NO-GO (529c75b) → tier-unification dialectic critique `wf_f353d3ad`, relayed graft proposal to director (dacf06a) → quality SUPIR-off (989206b) + fd-off (2a62ac0) probes independently scored = over-cook base-structural → director built+froze the graft driver (c5d0a80); operator Rule #22 pre-stage = SAFE; both wrapped.

## Cross-seat state at wrap
Director **WRAPPED `c5d0a80`** (handoff `docs/HANDOFF-director-transplant-2026-06-13-overcook-structural-prod-hybrid-driver-built.md`). FULL convergence — they consumed my 06:44/06:50/07:03 events and folded the fd-off-by-experiment finding, the node-collision map, and the phantom-detection diagnosis. All my Rule #22 verdicts converged with their self-reviews. Pod RUNNING+BILLING.

*Last verified: 2026-06-13T07:12Z (ci_smoke EXIT=0 firsthand; handoff cross-checked by wf_8ae4a804 accuracy+completeness critics — 1 BLOCKER + fixes folded; Rule #22 pre-stage on c5d0a80 firsthand; commit SHAs from git log. Watcher + standby die with this wrap — next operator re-arms.)*
