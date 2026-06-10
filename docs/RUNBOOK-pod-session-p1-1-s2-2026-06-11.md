# Runbook — P1-1 slice-2 bundled pod session (spec §7.2)

**Status: READY, blocked on one human gate** — ComfyUI start over SSH needs a
verbatim user go-ahead in a live seat session (classifier-gated; both seats'
attempts were denied on 2026-06-10 pending authorization). The pod itself is
RUNNING (user, 2026-06-10T~22:52Z); SSH port open; gateway 502 = ComfyUI not
started (known same-pod-restart pattern).

**Purpose:** one bundled session (shared spin-up, spec §7.2) that converts the
slice-2 offline work into validated live capability: pod-side LoRA placement,
the first live multi-char max render (Pass A), the S2 dual-PuLID spike (gates
Pass B), and the P1-2 over-cook investigation. **Cost frame:** ~$0.50–1.20
assuming 1–4 h billed uptime @ ~$0.30/hr (spec §4 row) — the phases below are
ordered to front-load the work that validates slice-2, so an early abort still
banks the acceptance evidence.

**Driving pattern:** all pod commands via `scripts/_pod_ssh.exp` (base64 body,
password via `POD_PW` env — credential + start command live in the director's
local-only memory, deliberately NOT in this repo). HTTP probes via the gateway
URL in `.env` `COMFYUI_SERVER_URL`. Reference probe script:
`scripts/_max_probe_prep.py` (upload + /object_info census + prune/inject
mirror).

---

## Phase 0 — spin-up + census (~5 min)

1. **User gate:** verbatim go-ahead for the ComfyUI start (this is the single
   blocked step; everything after inherits the authorization).
2. Start ComfyUI (command in the credential memory); wait ~10 s;
   `GET /system_stats` → 200.
3. **Census:** `GET /object_info` → expect ~1106 classes (prior-restart
   reference); verify the max-tier dependency classes from the
   `quality_max.py` module docstring are present — at minimum `ApplyPulidFlux`,
   `PulidFluxModelLoader`, `ReActorFaceSwap`, `SUPIR_model_loader_v2`,
   `FaceDetailer`, `StyleModelApplyAdvanced` (Redux), the three CN
   preprocessors, `LatentBlend`. A missing
   ReActor → `_inject_secondary_faceswap` no-ops BY DESIGN (graph stays
   valid) but Pass A loses the swap rescue — abort and investigate rather
   than rendering around it.
4. Record: census count + GPU name/VRAM from `/system_stats` (expect RTX 6000
   Ada, 49140 MiB).

## Phase 1 — pod-side LoRA placement (~5 min)

1. Copy `logs/char_lora_fal_v2.safetensors` (local) into the pod's
   `/workspace/ComfyUI/models/loras/` **under its basename** — the exact name
   `_inject_identity`/`_inject_secondary_loras` now write into `lora_name`
   (quality_max basename normalization, `e1981f0`). Transfer via the ssh
   driver (base64 a `cat > file` body or use scp with the same credential).
2. Verify: `GET /object_info` → `LoraLoader.input.required.lora_name`
   options list contains `char_lora_fal_v2.safetensors`.
3. NOTE: registered strength is **0.55 manual** (spec §7.3 — the v2 sweep
   covered {0.55, 0.70} + one 0.65 run; no machine-validated optimum).

## Phase 2 — first live render with the placed LoRA (single-char, N=1, ~5 min)

The cheapest possible validation that placement + basename + strength plumb
end-to-end before anything multi-char: one single-char Aria keyframe via the
max tier (web UI or a `_max_probe_prep.py`-style payload with
`char_lora="char_lora_fal_v2.safetensors"`). Expect: LoraLoader(700) loads
without error; arc score in the validated band; NOT painterly (per the
production+LoRA realism finding, 2026-06-02 memory — max-tier+LoRA behavior
at 0.55 is exactly what this run characterizes live for the first time).

## Phase 3 — live multi-char Pass-A render (THE slice-2 acceptance, N=1, ~10 min)

1. Two-char shot (Aria primary + a registered-reference secondary, e.g. the
   S1 fixture pair) through the production path with `quality_tier="max"`.
2. Expected take metadata: `identity_strategy.mechanism_tag ==
   "MAX_TIER_MULTI_LORA"`; secondary spec `fidelity="reference"` (no 2nd LoRA
   yet); `identity_per_char` covers both chars (advisory, never gating —
   spec §3(d)).
3. Expected graph behavior (all pinned offline, now live): trigger token
   prepended to the prompt (TOKwoman first); 611 swaps the RIGHT-hand face
   (input_faces_index "1", left-right ordering) from the secondary's
   canonical; 950/501 consume 611.
4. Capture: the keyframe, per-char arc scores, `comfyui_run.log` tail on any
   failure. Mis-ordered faces = known failure mode the validator catches
   (spec §3(c)) — record it, don't hand-fix.

## Phase 4 — S2 spike: dual-PuLID VRAM + composition (gates Pass B, ~30 min)

Per spec §S2: (1) measure peak VRAM of the CURRENT single-char N=8+SUPIR run
first (never measured — use Phase 2's config at N=8; poll
`nvidia-smi`/`/system_stats` during); (2) inject a second `ApplyPulidFlux`
(node 103) at N=1 against the POST-PRUNE graph (the 100→301→770→772→740→22
chain is partially pruned for FLUX at runtime — quality_max drops
301/770/772/740 WHEN their classes are absent from the pod census — so
compose against what actually survives on THIS pod); (3) scale to
N=4. **Go for Pass B:** no OOM at N=4+ AND both arc scores >0.70.
Record numbers either way — a NO-GO with measured VRAM is a deliverable.

## Phase 5 — P1-2 over-cook investigation (time-boxed, remainder of session)

Strategic-review P1-2: fresh faces (no PuLID reference, no LoRA) come out
painterly on the max tier (user verdict 06-09). With the pod live: (a) A/B a
fresh-face render against Phase-2's LoRA-backed render to isolate which chain
stages over-cook; (b) probe pod-side LoRA-training feasibility (the trainer is
a local-CUDA subprocess today — `prep/lora_training.py`; check what
ai-toolkit/kohya would need on this pod). Outcome: findings note, not a fix —
direction lands as an ADR/spec update afterward.

## S3 — multi-LoRA stacking (CONDITIONAL — do not start without its gate)

Needs a **second registered LoRA** = a user-funded FAL training decision
(surface it when the user is engaged; do not nag). If funded mid-session:
sweep secondary strength ∈ {0.35, 0.45, 0.55} stacked over the primary at
0.55, watch for paired score collapse (bleed). `_SECONDARY_LORA_MAX_STRENGTH`
(quality_max.py) is the single tune site.

## Exit

- Results → spec §6 record (S2 go/no-go + VRAM numbers; Pass-A acceptance;
  P1-2 findings) in the same session where feasible; scorecard/take metadata
  is the machine record.
- **Pod stop/keep = user decision** (bills while idle; the 06-09 overnight
  incident is the cautionary tale — P2-2 guardrails still NOT_DONE).
- Mailbox event to the operator: session outcomes + any disposition requests;
  Lane V on whatever landed.
