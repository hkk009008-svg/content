# Director transplant handoff — 2026-06-13 (PM): the over-cook is STRUCTURAL to the max base graph (every post-pass toggle failed) → PRODUCTION-TIER HYBRID driver BUILT + dry-verified, ready to burn — pod LIVE+BILLING, operator ONLINE (full convergence)

**Supersedes** `docs/HANDOFF-director-transplant-2026-06-13-design-d-breakthrough-man-binds-pod-live.md`
(its ⭐#1 advanced: Design-D placement via masking = NO-GO → pivoted to QUALITY →
3 over-cook probes → root-caused → production-tier hybrid driver built).

## Ground truth (verified at wrap, 2026-06-13T07:09Z UTC)

- **HEAD `c5d0a80`**, push USER-gated as always. Branch many commits ahead of origin.
- **Smoke OK** (`scripts/ci_smoke.py` → OK; PROGRAM-MANUAL carries ~55 ADVISORY
  doc-anchor drifts, fix-on-touch, NOT a gate). **Suite 2244 passed / 2 skipped**
  (re-counted this session, `env -u GIT_INDEX_FILE .venv/bin/python -m pytest -q`).
- **Mailbox: director cursor `2026-06-13T07:03:19Z`, 0 unread.** Wrap reply
  `07:09:20Z` sent (rides this commit). **OPERATOR IS ONLINE** and fully converged
  — they independently scored every render + ran their own tier-unification
  dialectic; their conclusions match ours.
- **POD 07ed667 RUNNING + ComfyUI UP + BILLING.** Read-only `/system_stats`→200
  early-session. **Bills until the user stops it in the Novita console** — flag at
  pickup. Pod-work auth is session-scoped (re-obtain). Spend this session ~$0.09
  (3 × N=1 burns). Both char LoRAs intact.

## ⭐ #1 PICKUP — production-tier hybrid driver is BUILT + dry-verified; burn it

**`scripts/_prod_dual_lora_pulid.py` (committed `c5d0a80`) — NOT yet burned (Rule
#22 + spend gated).** It grafts the PROVEN identity stack onto the PROVEN photoreal
sampler chain — the only config the data points to for photorealism + binding:

- **Base = `pulid.json`** (production 22-node graph), KEPT untouched: BasicScheduler
  + dpmpp_2m + sgm_uniform + 20 steps + PAG + RealESRGAN (500/501/502). This is the
  clean, non-over-cooking sampler chain that ships photoreal portraits.
- **Graft (copied VERBATIM from `pulid_max.json`):** nodes 99/100/101/700 — the
  Flux PuLID loader trio (`PulidFluxModelLoader`/`PulidFluxEvaClipLoader`), node 100
  `ApplyPulidFlux`, and the LoRA `LoraLoader` (700). The node IDs 97/99/100/101/93/
  112/11 are IDENTICAL across both graphs, so copied input links resolve with NO
  remapping, and node 100 inherits the proven `start_at=0.0` (NOT pulid.json's
  SDXL-era `start_at=0.3`, which would miss the coarse-identity window and suppress
  binding — adversary-flagged, avoided).
- **Then:** LoRA 700 → `char_lora_man_v1.safetensors` @0.55, `122.clip→['700',1]`
  (LoRA CLIP/TOKman patch reaches the prompt), splice node 103 (the man,
  `103.model=['100',0]`, man face on new node 95), prepend `TOKman`, PAG (301)
  rewired to 103.
- **COLLISION-SAFE by construction:** loads `pulid.json` directly + deep-copies the
  4 identity nodes; **NEVER calls `_inject_post_passes` / `_prune_unavailable`**, so
  the RealESRGAN 500/501/502 chain is untouched (operator's collision warning:
  pulid.json 500/502 are RealESRGAN, max's are SUPIR at the SAME IDs — a max
  post-pass injection would corrupt the prod save chain). $0 dry-build PASS, 11
  checks (chain 112→700→100→103, start_at=0.0, over-cook nodes 600/780/900/901/950
  ABSENT, RealESRGAN 500 present, PAG rewired).
- **Money-path = `render_leg` UNCHANGED** (operator SAFE); `build_prod_dual_lora` is
  pure offline graph assembly guarded by 6 pre-submit asserts + the /prompt
  rejected-graph guard ($0 worst case).

**Sequence:** (1) flag the operator for Rule #22 (real new graph — they offered to
pre-stage); (2) burn `PYTHONPATH=. .venv/bin/python scripts/_prod_dual_lora_pulid.py
--n 1` (~$0.03, seed 990011); (3) read **arc FIRST** (man LEFT ≥~0.75, cf 0.870 max
baseline) then **VISUAL — photoreal skin is the PRIMARY GO**; (4) if GO → production-
tier N=4 GO bar. Spend USER-gated each burn; show every render in Preview.

**Two OPEN design questions for the first prod burn:**
1. **FaceDetailer (node 600) is OMITTED** (pulid.json lacks it). Operator's
   fd-off→NO_FACE finding says it's an identity AID — but that was on the OVER-COOKED
   max base. The clean production base may bind without it. Isolate the variable:
   first burn WITHOUT it; if the man reads weak/NO_FACE, add node 600 to the graft
   next iteration. (`--man-weight 1.0` is the built-in asym lever if the man
   under-binds.)
2. **Binding metric is non-deterministic on over-cooked renders** (operator: man
   0.64/0.68/0.81 ±0.17 across warm invocations of the SAME over-cooked image — 5
   phantom face-detections, "largest-OK-face" varies). A CLEAN production render
   should detect fewer phantoms, but **pin deterministic figure-selection /
   phantom-filter before any N=4 binding threshold** (re-triggered 0.487
   junk-man-column fragility; warming the ref is NOT the fix — deterministic
   selection is).

## What landed this session (director seat, chronological)

1. **Design-D + masking placement (`48ad08b`)** — built `_max_passBd_masked_lora_pulid.py`
   (Design D + attn_mask swap). Validation workflow (`wf_13f32597`, proceed-with-guard)
   + GUARD 1 (arc-first) + GUARD 2 ($0 wiring trace). Burned N=1 → **masking is
   PLACEMENT-INERT for a bound identity** (man stayed LEFT, aria stayed RIGHT, arc
   identical to baseline; even PuLID-only aria didn't move). **Design-D+masking = NO-GO
   for placement.** Binding win intact. Operator independently confirmed.
2. **Quality pivot — SUPIR-off (`c3ce4b0`, `_max_passBe_quality_lora_pulid.py`)** —
   user chose quality. Burned: SUPIR-off → still over-cooked + man read dropped
   (0.637, but DOUBLY confounded: SUPIR-sharpening + phantom-detection noise, so NOT
   cleanly "binding weakened"). User overrode the operator-SAFE handshake ("proceed
   with the burn") — sound, money-path was byte-identical (operator retroactively
   confirmed SAFE).
3. **FaceDetailer-off probe (same driver `--facedetailer-off`)** — burned → STILL
   over-cooked (worse) + LEFT went NO_FACE (FaceDetailer is an identity AID, not the
   over-cook source).
4. **Production-tier hybrid driver (`c5d0a80`)** — see ⭐#1. Designed by
   `wf_963a4a8a` (Lens A found the production no-op; Lens C ranked the hires-fix;
   adversary hardened the build). Built + $0 dry-verified, NOT burned.
5. **comfyui-mastery doc fix (folded into `48ad08b`)** — added the `ApplyPulidFlux`
   entry to `nodes-face-identity.md` (the FLUX production node was undocumented).

## KEY FINDINGS (the realism characterization)

- **The over-cook is STRUCTURAL to the max base graph** — proven by 3 probes + the
  operator's independent scores: max+dual+LoRA+SUPIR-on (Design D), max+dual+no-LoRA+
  SUPIR-on (Design A), max+dual+LoRA+SUPIR-off+FD-off all over-cooked. No post-pass
  toggle clears it. Root cause (`wf_963a4a8a` Lens C, RANK 1): the **hires-fix
  re-diffusion (node 901 — a 2nd sampler pass @denoise 0.40 on a 1.5× upscaled
  latent)** + the heavier max sampler (OptimalStepsScheduler/28 steps vs production
  BasicScheduler/20). The fix is the **sampler chain**, not removing passes.
- **`pulid.json`'s PuLID is a FLUX/SDXL NO-OP** (`wf_963a4a8a` Lens A, high conf,
  CODE-ANALYSIS — not yet empirically pod-confirmed): node 100 is `ApplyPulid` (the
  SDXL node) on a FLUX UNet; its cross-attention patches target U-Net layers FLUX's
  DiT lacks → **zero face lock**. The production tier's photoreal output is plain
  FLUX txt2img + PAG + RealESRGAN. **⚠ DATA-INTEGRITY FLAG:** production renders
  logged `COMFYUI_PULID` may carry zero identity. Worth verifying + fixing on its own
  thread (separate from the realism goal). NOT yet acted on.
- **The realism memory was misleading:** "production pulid.json + char LoRA @0.55 =
  realism + identity" — but production has NO LoRA node + a no-op PuLID. The realism
  is from the clean sampler; the identity needs the FLUX-PuLID + LoRA graft (= ⭐#1).
  Memory `realism_production_plus_char_lora` corrected this session.

## Tier-unification critique (user asked; both seats converged)

**Verdict: do NOT full-unify, do NOT toggle-post-passes; graft the max IDENTITY
stack onto the production SAMPLER** (= ⭐#1). Decisive CONs for one dial-able tier:
the over-cook is base-structural (can't be dialed off), and the two graphs reuse
node IDs for incompatible classes (100 ApplyPulid vs ApplyPulidFlux; 17 scheduler;
500/501/502 RealESRGAN vs SUPIR) + a `ays_steps` vs `steps` param-key mismatch.
Operator ran an independent dialectic (`wf_f353d3ad`) reaching the same conclusion.
**TODO (carried): capture this as a `DECISIONS.md` ADR** — fully characterized, not
yet written (ran out of session at the build step).

## Two-seat state at wrap

**OPERATOR ONLINE + fully converged — clean two-seat session.** They were briefly
heads-down (consume-cadence lagged ~20 min mid-session) but caught up and
independently: confirmed the placement NO-GO, scored all 3 quality renders (with the
phantom-detection caveat), retroactively cleared c3ce4b0 SAFE, ran the tier
dialectic, and proposed the EXACT graft the prod driver implements (`06:50` event).
**Lesson reinforced (held this time):** `git log -5` before every shared-tree commit
caught their interleaved commits (`989206b dacf06a 2a62ac0`) before my freeze.
Operator's standby: Rule #22 PRE-STAGE on the frozen prod driver `c5d0a80`; then
independent phantom-aware scoring of the first prod render.

## Director backlog (carried + new)

⭐#1 production-tier burn (Rule #22 → N=1 → read → N=4) · DECISIONS.md ADR (tier
graft + over-cook-structural) · **DATA-INTEGRITY: verify the production COMFYUI_PULID
no-op** (does the live production path apply zero identity? if so it's a real bug) ·
deterministic figure-selection / phantom-detection filter for the N=4 binding metric
(operator-flagged, ties to the 0.487 fragility) · FaceDetailer-in-prod open question ·
placement (man-left vs intended-right) — DEFERRED below quality; masking dead, levers
= prompt-order / PuLID-node-swap / seed, re-measure on the clean prod render · P2-2
pod idle guardrails · carried P2/spec debts.

## Operational notes (this session)

- **Production driver is collision-safe BECAUSE it never runs the max post-pass
  helpers.** If you extend it, do NOT call `q._inject_post_passes` on the prod
  graph (it'd write SUPIR params into the RealESRGAN 500/501/502 IDs).
- **Arc scorer (`scripts/_arc_score_session.py --halves`)** is the GUARD-1
  instrument; warm it (multiple runs) — but on over-cooked renders the man column
  wobbles ±0.17 from phantom detections. Trust the VISUAL on cooked output.
- **The save_prefix collides across flag variants** — `_max_passBe_quality_lora_pulid.py`
  saved both SUPIR-off and FaceDetailer-off to `logs/passb_q_n1.jpg` (the 2nd
  overwrote the 1st). Distinct prefixes per config if you need to keep both.
- **render_leg backgrounds well** (~6 min/N=1 with post-passes; SUPIR-off ~5.7 min @
  34 GiB; FaceDetailer+SUPIR-off ~0.6 min @ 32 GiB). Run in the background.

*Last verified: 2026-06-13T07:09Z UTC — smoke OK + suite 2244/2 at c5d0a80; cursor
07:03:19Z 0 unread; prod driver dry-build PASS; pod RUNNING+BILLING; operator ONLINE.*
