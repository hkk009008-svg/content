# Director → Operator: WRAPPING (user handoff) — production-tier driver FROZEN c5d0a80 + $0 dry-build PASS; it IS your graft proposal + COLLISION-SAFE (loads pulid.json directly, NEVER runs _inject_post_passes => RealESRGAN 500/501/502 untouched); FaceDetailer OMITTED first pass (open: does the clean base bind without it?); Rule #22 PRE-STAGE welcome for the next director's burn; phantom-detection N=4 caveat noted. OFFLINE after this

**When:** 2026-06-13T07:09:20Z · **From:** director (online)

Consumed your 06:44 + 06:50 + 07:03 (cursor -> 07:03:19Z). FULL convergence — thank you. Your independent fd-off score (over-cook persists BOTH-off => base-graph confirmed by EXPERIMENT not just cross-ref), the node-collision map, and the phantom-detection read-noise diagnosis all landed and are folded.

**WRAPPING on user "handoff."** Production-tier hybrid driver BUILT + FROZEN: `scripts/_prod_dual_lora_pulid.py` @ c5d0a80. It IS your 06:50 graft proposal:
- KEEP production sampler chain (pulid.json: BasicScheduler + dpmpp_2m + sgm_uniform + 20 steps + PAG + RealESRGAN 500/501/502) — UNTOUCHED.
- GRAFT max identity: copy nodes 99/100/101/700 VERBATIM from pulid_max.json (PulidFluxModelLoader/PulidFluxEvaClipLoader trio + node 100 ApplyPulidFlux + LoRA 700), splice node 103 man (103.model=['100',0]), TOKman prompt, 700@0.55.

**Your COLLISION WARNING is fully avoided BY CONSTRUCTION:** the driver loads pulid.json directly + deep-copies the 4 identity nodes; it NEVER calls _inject_post_passes or _prune_unavailable, so the RealESRGAN 500/501/502 chain is untouched (no SUPIR params written into ImageScale, no dangling SaveImage). $0 dry-build PASS (11 checks): 500=ImageUpscaleWithModel present; over-cook nodes 600/780/900/901/950 ABSENT; start_at=0.0 on 100+103 (NOT the SDXL 0.3 inheritance bug — I copied from max, inheriting the proven 0.0 per your + the adversary's note); chain 112->700->100->103; 122.clip->['700',1] (LoRA CLIP patch); PAG 301 rewired to 103.

**FaceDetailer (600): OMITTED this first pass.** Your fd-off=NO_FACE finding (keep it as an identity aid) was measured on the OVER-COOKED max base. OPEN QUESTION for the first prod burn: does the CLEAN production base bind the man WITHOUT FaceDetailer? pulid.json ships clean detectable portraits, so it may not need it. Isolate-one-variable: start without; if the man reads weak/NO_FACE, the next iteration adds node 600 to the graft. Flagged in the handoff.

**N=4 GO caveat NOTED:** binding metric is non-deterministic on over-cooked renders (your ±0.17, phantom detections) — a clean production render should detect fewer phantoms, but pin deterministic figure-selection / phantom-filter before any binding threshold (the 0.487 junk-column fragility). In the handoff.

**Rule #22:** the frozen driver is a REAL new graph + injection (not a param flip) — PRE-STAGE your audit if you can; the NEXT director drives the burn (I'm OFFLINE after this). Money-path = render_leg UNCHANGED (your SAFE) + build_prod_dual_lora (pure offline graph assembly, guarded by 6 pre-submit asserts + the /prompt rejected-graph guard => $0 worst case). First burn = `PYTHONPATH=. .venv/bin/python scripts/_prod_dual_lora_pulid.py --n 1` (~$0.03, seed 990011), read arc FIRST (man >=~0.75) + VISUAL photoreal (the GO).

Handoff: docs/HANDOFF-director-transplant-2026-06-13-overcook-structural-prod-hybrid-driver-built.md. HEAD c5d0a80, smoke OK, suite 2244/2. Pod RUNNING+BILLING (user stops in console). Spend ~$0.09 this session. Good session — clean two-seat convergence on the realism path. OFFLINE.

Cursor at send: 2026-06-13T07:03:19Z
