# Production PuLID SDXL→FLUX correctness fix — design

- **Date:** 2026-06-13
- **Status:** COMPLETE — implementation shipped (`a1103bd`/`f05c83b`/`c5199de`/`a924055`/`7b54af9`); pod acceptance gate PASSED 2026-06-13 (arc 0.6205→0.8779, seed 990011, 18.2 GiB; artifact `logs/prod_pulid_acceptance_20260613.json`). Shipping default. Decision record: ADR-025.
- **Author:** director seat
- **Related:** ADR-024 (production-tier identity graft); `scripts/_prod_dual_lora_pulid.py`
  (proven FLUX graft, experiment-tier)

## Problem

The default production image tier renders portraits through `pulid.json`, whose
PuLID stack is the **SDXL-era nodes running on a FLUX UNet**:

- node 99 `PulidModelLoader` (`ip-adapter_pulid_sdxl_fp16.safetensors`)
- node 100 `ApplyPulid` (`start_at=0.3`, `method="fidelity"`)
- node 101 `PulidEvaClipLoader`

`ApplyPulid` patches U-Net cross-attention layers; FLUX's DiT (node 112 =
`flux1-dev-fp8.safetensors`) has no such layers, so the face-identity injection is a
**structural no-op** — the production tier's realism is plain FLUX txt2img + PAG +
RealESRGAN, carrying little/no reference-face identity. Renders are nonetheless
tagged `COMFYUI_PULID` (`phase_c_assembly.py:413`): cost attribution is correct
(ComfyUI ran) but the identity-provenance claim is wrong.

**Evidence:** the node-class mismatch is CONFIRMED by direct inspection of
`pulid.json`; the *functional* no-op was **empirically confirmed by the acceptance
gate** below — the PuLID-OFF baseline (identity bypassed) scored arc 0.6205 while the
fixed FLUX-native graph scored 0.8779 (+0.257), i.e. the SDXL-on-FLUX path carried
~no reference-face identity, exactly as the `wf_963a4a8a` Lens A analysis predicted. The correct
FLUX node set already runs on the same pod (the max tier `pulid_max.json` uses
`PulidFluxModelLoader` / `ApplyPulidFlux` / `PulidFluxEvaClipLoader` +
`pulid_flux_v0.9.1.safetensors`), and a proven graft exists in
`scripts/_prod_dual_lora_pulid.py` (experiment-tier; bypasses `phase_c_assembly`).

## Goal & success criteria

The default production tier's single PuLID actually locks the reference face on FLUX,
with no other behavior change. Done when:

1. `pulid.json` nodes 99/100/101 are the FLUX-native classes; node 100 is wired
   `pulid_flux` / `fusion` / `use_gray` with `start_at=0.0` and `model:["112",0]`.
2. Per-shot `pulid_start_at` no longer re-suppresses the coarse-identity window at
   runtime.
3. A regression test pins the corrected node classes (closes the test-dark gap).
4. **Acceptance gate (pod):** on a fixed reference face + seed, the post-fix identity
   score rises materially over the pre-fix baseline (toward the experiment's ~0.87
   single-face range), confirming the bug was real and the fix works on the
   production fp8 graph.

## Scope

**In scope** (scope A — minimal correctness): the SDXL→FLUX node correction for the
single production PuLID + the runtime `start_at` alignment that makes it bind + a
regression guard + the pod acceptance check.

**Out of scope** (explicit):

- LoRA / dual-identity production support (ADR-024 experiment track;
  `scripts/_prod_dual_lora_pulid.py`).
- `COMFYUI_PULID` tag split (SDXL vs FLUX provenance).
- Per-class FLUX re-tuning of `pulid_weight` / `pulid_end_at` / `fusion` beyond
  `start_at` (post-validation follow-up).
- SDXL `.safetensors` pod-disk reclamation (pod management, not code).
- The sibling data-integrity surfaces the operator flagged (`continuity_engine` /
  `character_manager` / scorer `_get_embedding`) — separate lanes.

## Design

### Component 1 — Graph correction (`pulid.json`)

Edit three node dicts in place (rollout R1):

| Node | From | To |
|---|---|---|
| 99 | `PulidModelLoader`, `pulid_file: ip-adapter_pulid_sdxl_fp16.safetensors` | `PulidFluxModelLoader`, `pulid_file: pulid_flux_v0.9.1.safetensors` |
| 100 | `ApplyPulid` | `ApplyPulidFlux` |
| 101 | `PulidEvaClipLoader` | `PulidFluxEvaClipLoader` |

Node 100 input surgery (preserve every link except the renamed one):

- rename `pulid: ["99",0]` → `pulid_flux: ["99",0]`
- **drop** `method: "fidelity"`
- **add** `fusion: "mean"`, `fusion_weight_max: 1.0`, `fusion_weight_min: 0.0`,
  `train_step: 1000`, `use_gray: true`
- `start_at: 0.3` → `0.0`
- **keep** `model: ["112",0]` (direct from the UNETLoader — there is no LoRA node 700
  in scope A; do **not** copy max's `model:["700",0]`), and keep `weight`, `end_at`,
  `eva_clip: ["101",0]`, `face_analysis: ["97",0]`, `image: ["93",0]`.

Unchanged: node 97 (`PulidInsightFaceLoader`, `{provider: "CUDA"}` — byte-identical in
both graphs), node 112 (FLUX fp8 UNet), the RealESRGAN chain (500/501/502), PAG (301),
the sampler chain, and the no-character bypass.

### Component 2 — Param alignment (`workflow_selector.py`)

- `WORKFLOW_TEMPLATES`: set `pulid_start_at: 0.0` for portrait / medium / wide / action
  (currently 0.2 / 0.25 / 0.35 / 0.3). Landscape unchanged (`pulid_weight: 0.0` — PuLID
  off; routes to Kontext). **Rationale:** `apply_workflow_params` writes
  `pulid_start_at` onto node 100 at runtime; without this change the JSON's new `0.0`
  is overwritten back to the SDXL-era value on every render, re-suppressing the
  coarse-identity window — making the node swap net-zero. This is the crux of the fix,
  not optional tuning.
- Fix the stale docstring (`workflow_selector.py:512`): `ApplyPulid` / `method` →
  `ApplyPulidFlux` / `fusion`.
- **No change** to: `apply_workflow_params` body (writes `weight` / `start_at` /
  `end_at`, all valid on `ApplyPulidFlux`); `pulid_weight` / `pulid_end_at` (valid on
  both schemas — flagged for empirical re-tune, out of scope); the no-character bypass
  in `phase_c_assembly.py` (class-agnostic — pops node IDs 93/97/99/100/101).

### Component 3 — Regression guard (new test)

A unit test (`tests/unit/test_pulid_production_flux.py`, matching the repo's
`tests/unit/` convention) that loads the real `pulid.json` and asserts:

- nodes 99/100/101 `class_type` are the FLUX variants (`PulidFluxModelLoader`,
  `ApplyPulidFlux`, `PulidFluxEvaClipLoader`);
- node 100 has input key `pulid_flux` (not `pulid`) and no `method` key;
- node 100 `model` link is `["112",0]` (guards against a dangling LoRA reference).

This closes the **test-dark** gap: no current test asserts node classes, which is why
the SDXL-on-FLUX misconfiguration shipped silently and undetected.

### Component 4 — Acceptance gate (pod, empirical) — PASSED ✅ 2026-06-13

Before/after on a fixed reference face + seed (operator-run, user-directed):

- PuLID-OFF baseline (identity bypassed): arc **0.6205** — confirmed low (a different
  generic woman; coincidental prompt-match, not the reference identity).
- PuLID-ON (fixed FLUX-native graph): arc **0.8779** (+0.257) — aria identity LOCKED,
  at the ~0.87 single-clean-face ceiling.

All four confirmation targets satisfied: (a) the bug is real (OFF baseline low) ✓;
(b) the fix works (+0.257 material lift) ✓; (c) **fp8 compatibility** — node 112
`flux1-dev-fp8` bound to 0.8779, retiring the fp8-vs-fp16 escalation ✓; (d) the clean
production base binds **without FaceDetailer** (figure read, no NO_FACE) ✓. Seed
990011, peak VRAM 18.2 GiB, both renders visually photoreal. Read with the
deterministic arc scorer (post `d48b58b`). Artifact
`logs/prod_pulid_acceptance_20260613.json` (instrument `scripts/_prod_pulid_acceptance.py`, `a43358f`).

## Data flow

Unchanged. `generate_ai_broll(quality_tier="production")` → load `pulid.json` →
`classify_shot_type` + `apply_workflow_params` (writes `weight`/`start_at`/`end_at` to
node 100 **by ID** — class-agnostic) → submit to the pod → poll → download →
`ImageGenResult(..., "COMFYUI_PULID")`. The fix changes node *contents*, not the Python
control flow; no caller signature changes; the cascade fallback (Kontext → FLUX-Pro →
schnell → Pollinations) is untouched.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| **fp8 incompatibility** — `ApplyPulidFlux` is trained against fp16; prod's node 112 is fp8 | The acceptance gate is the test. The experiment driver (`_prod_dual_lora_pulid.py`) runs the **same** fp8 prod graph, so its pending burn is the first evidence. If fp8 degrades the lock, the fallback is to point node 112 at an fp16 FLUX UNet — but **no fp16 FLUX UNet artifact is in scope A**, so the gate-failure path needs a follow-up ADR + a pod-side model asset before that fallback is actionable. |
| **start_at undone at runtime** | Component 2 lowers the template values — without it the swap is net-zero. |
| **Partial node swap** — upgrading 100 without 99/101 dangles `pulid_flux`/`eva_clip` links | All three swap atomically in one edit; the regression test (Component 3) pins it. |
| **`method` stale write** — a future contributor wiring `method` to node 100 | Docstring fixed; `apply_workflow_params` confirmed not to write `method`. |
| **weight semantics differ** SDXL↔FLUX (prod portrait `pulid_weight=1.0` vs experiment 0.85) | Keep current per-class weights as a starting point; flag for empirical re-tune (out of scope). The acceptance gate will surface over/under-lock. |

## Rollout & rollback

In-place (R1) — **COMPLETE.** Implemented + committed (`a1103bd`/`f05c83b`/`c5199de`);
the regression test passes offline; the pod acceptance gate PASSED 2026-06-13 (above).
The fix is now the **shipping default**. Push remains USER-gated. Rollback = `git revert`
the `pulid.json` + `workflow_selector.py` change (two files; no schema, no migration, no
data backfill).

## Cross-refs

ADR-024; `scripts/_prod_dual_lora_pulid.py`; `pulid.json` / `pulid_max.json`;
`phase_c_assembly.py:178-261,413`; `workflow_selector.py:24-32,506-542`;
`.claude/skills/comfyui-mastery/references/nodes-face-identity.md`.
