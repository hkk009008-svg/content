# Operator → Director: Chunk-1 PuLID SDXL->FLUX independently VERIFIED CORRECT (a1103bd/f05c83b/c5199de) + CASE LANDMINE confirmed & bounded — recommend git mv before the pod gate

**When:** 2026-06-13T09:09:46Z · **From:** operator (online)

**VERDICT: Chunk-1 (production PuLID SDXL→FLUX) is VERIFIED CORRECT.** Independent post-commit verification by the Pair-A operator, comfyui-mastery skill loaded first (R-SKILL). No code touched (verification seat).

**Graph (a1103bd, Pulid.json):**
- Nodes 99/100/101 → PulidFluxModelLoader / ApplyPulidFlux / PulidFluxEvaClipLoader. Confirmed against the PROVEN-on-pod `pulid_max.json`: the full PuLID family now matches max **node-for-node** — `{97:PulidInsightFaceLoader, 99:PulidFluxModelLoader, 100:ApplyPulidFlux, 101:PulidFluxEvaClipLoader}`.
- Node 97 (`PulidInsightFaceLoader`, cubiq-class) was CORRECTLY left unchanged — max uses the same cubiq InsightFace loader alongside the lldacing Flux nodes; the pod has both co-installed (max renders with this mix). Checked specifically as an incomplete-migration candidate — disproven.
- ApplyPulidFlux input-key set is IDENTICAL to max's (0 key divergence; lldacing PuLID_Flux_ll schema confirmed pod-valid via the working max tier). Only intentional tier-value diffs: `model=["112",0]` direct/no-LoRA (max `["700",0]`), `weight` 1 (max 0.85), `end_at` 1 (max 0.9 — overwritten per-class at runtime anyway).
- WIRING TRACED: 112(UNETLoader flux1-dev-fp8) → 100(ApplyPulidFlux) → 301(PAG, model:["100",0]) → 17/22(scheduler+guider, model:["301",0]) → 13(SamplerCustomAdvanced) → 8 → 500/502 → 9. The PuLID-patched model is genuinely consumed downstream — NOT a wiring no-op. The old bug was purely the SDXL class (couldn't bind FLUX DiT); the route was already correct, so the class fix activates the lock.

**Params (f05c83b, workflow_selector.py):** start_at→0.0 is image-tier ONLY (WORKFLOW_TEMPLATES portrait/medium/wide/action; landscape + MAX_QUALITY_TEMPLATES untouched — no Pair-B/video contamination). apply_workflow_params writes valid FLUX keys (weight/start_at/end_at) to node 100, no stale `method`. Docstring :512 updated to ApplyPulidFlux/fusion.

**Test (c5199de):** applied-start_at 0.2→0.0 is the fix, not a revert. ALL Chunk-1 tests GREEN at HEAD 96837aa: **129 passed** (test_pulid_production_flux 5/5 + test_workflow_selector + test_phase_c_assembly_portrait). ci_smoke OK. coordination clean (4 INFO).

**F1 — CASE LANDMINE confirmed + BOUNDED (your backlog item; still OPEN; gates Task-4):**
- git-tracked `Pulid.json` (capital P) vs lowercase `pulid.json` in ALL 5 code refs (phase_c_assembly:178/199/204 + scripts/_fal_lora_production:43 + scripts/_prod_dual_lora_pulid:57), the new test (:16), AND the on-disk case-preserved name. Repo-wide case audit (git ls-files vs disk) → **single mismatch, no siblings.**
- Exact pod failure mode: a case-sensitive checkout materializes `Pulid.json` → `os.path.exists("pulid.json")` is FALSE at phase_c_assembly:178 → production PuLID branch SILENTLY skipped → FAL fallthrough (the whole fix is unreachable). And the new regression test ERRORs FileNotFoundError on the pod instead of the prod code's graceful skip.
- RECOMMEND `git mv Pulid.json pulid.json` (case-only 2-step on macOS) BEFORE the pod acceptance gate. Zero-risk on macOS (case-insensitive FS, no behavior change), strictly-improving on Linux; reconciles git↔disk↔code↔test. Caveat: on-pod failure unconfirmable while pod DOWN (hinges on deploy mechanism = git-checkout [breaks] vs rsync-from-mac [masks]); the mv removes the ambiguity either way. Operator deferred unilateral execution (your lane / consequential deploy-affecting rename) — flagging for your call or the user's.

**Advisories (fold-on-touch, NON-blocking):**
- F2: apply_workflow_params default `pulid_start_at` fallback still 0.3 (SDXL-era) at workflow_selector:521 — never hit (templates always pass 0.0) but inconsistent with the FLUX fix.
- F3: the new test pins node classes/inputs but not the wiring; a future edit disconnecting 100→301 would still pass. Optional: assert graph["301"]["inputs"]["model"]==["100",0].
- F4: docstring :512 lists "fusion" as a node-100 param, but apply_workflow_params doesn't write fusion (graph default "mean"). Cosmetic.

**POD-GATE DEPENDENCY (not a finding; pod-bound):** fp8 compat (prod node 112 flux1-dev-fp8 vs max fp16) + FaceDetailer-free binding — Task-4 confirms on pod-up.

Cursor at send: 2026-06-13T08:54:01Z
