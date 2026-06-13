# Operator Transplant Handoff — 2026-06-02 (max-tier LIVE-validated end-to-end on the pod)

*Last verified: 2026-06-02. Shared tree on `feat/max-tier-provisioning`@`912d562`;
`main`=`origin/main`=`5425f9e`. Pod `07ed667` ComfyUI UP (HTTP 200). ⚠️ POD IS BILLING.*

## READ FIRST — pickup state (≤2 min)

- **Branch `feat/max-tier-provisioning` @ `912d562`** — 7 commits off `main` (`5425f9e`).
  NOT merged, NOT pushed. The shared tree is checked out ON this branch.
- **`main` = `origin/main` = `5425f9e`** (F1/F1b, pushed last session).
- **★ MAX-TIER IS PROVEN WORKING ON THE LIVE POD.** A full 4K image
  (`logs/max_out_FLUX_MAX_00019_.png`, 3840×2160) generated end-to-end through the
  complete stack: fp16 FLUX + PuLID + LoRA-less + FaceDetailer + ReActor + SUPIR 4K.
- **Pod `07ed667` ComfyUI is RUNNING** (pid 336). **The pod bills by the second —
  stop it in the Novita console when done.**
- Working tree clean (only untracked scratch: `scripts/_*.py`, `scripts/_pod_ssh.exp`,
  `logs/`). Pytest `tests/unit/test_quality_max_prune.py` 13 passed; §15 smoke OK.
- **Mailbox/coordination:** D-a inactive this session (CLAUDE_SEAT unset);
  pathspec-commit used throughout. No new mailbox events sent this session
  (director's F1 hand-off from last cycle closed via commits — see "Prior context").

## The user's running goal

"Prepare for max tier test" → escalated live to "make the max-tier test actually
run on the pod." **Done for a single image.** User then chose **"Full harness run
(N=8 + Veo)"** as the next step — that is the ★ TOP OPEN ITEM (see below). User
gave SSH access mid-session and said "ssh first" (drive the pod via SSH; run is
Mac-driven against the pod's ComfyUI over the gateway, which works).

---

## What this session shipped

### 1. F1/F1b CRITICAL fix → MERGED + PUSHED to main (`5425f9e`)
Picked up last cycle's director F1 hand-off (no-char 600/610 dangling). Ported it to
a fix branch off `main`; **my TDD reachability test surfaced F1b** — a *separate*
CRITICAL divergence on this 56-node version (char+no-init left
`600.positive/negative→[804,0]` dangling → silent max→production fallback; Rule #13
symmetric completion of the existing `22→[60,0]` rewire). User greenlit "fix both."
`a302585` (F1) + `5425f9e` (F1b), fast-forward merged to `main` + pushed.

### 2. Max-tier test prep (offline, 4 deliverables) on `feat/max-tier-provisioning`
- `5a229d2` **LoRA-less max path** — `_inject_identity` prunes node 700 when no
  `char_lora` (PuLID-only identity, logged); + availability-prune test coverage.
- `4d33868` **fp8/fp16 `_apply_model_precision`** — re-points 112/11 to fp8 by
  default; `MAX_MODEL_PRECISION=fp16` (or `params['max_model_precision']`) for true max.
- `339b674` + `9850b7b` **`setup_runpod.sh --max`/`--max-fp16`** path (additive;
  installs SUPIR/Impact-Pack+Subpack/Detail-Daemon + max weights, gated FLUX
  HF_TOKEN-guarded). `9850b7b` scrubbed a **fabricated** `setup_runpod_max.sh`/
  `compat_patches()` ref a build subagent hallucinated (no such file in the repo).
- `ea118f0` **`docs/RUNBOOK-max-tier-test.md`** + refreshed handoff/OPERATIONS.
- Full unit suite **1295 passed** at that point. User chose KEEP-AS-IS (validate on a
  pod before merge) → which is what the rest of the session did.

### 3. ★ LIVE POD VALIDATION → working 4K image (`9d7cf70` + `912d562`)
User gave SSH access. Found the pod **already heavily provisioned** (fp16 FLUX 23.8GB,
SUPIR+SDXL base, inswapper, ALL max custom nodes) but **ComfyUI was DOWN** (that's why
the gateway 502'd). Started ComfyUI, then iteratively fixed the workflow against
`/object_info` + runtime errors until a 4K image generated. **Every value was ported
from the proven 60-node `max-tier-provisioning-2026-06-01` branch** (which ran SUPIR
on this exact pod):

| Layer | Blocker → fix | Commit |
|---|---|---|
| Validation | SUPIR chain was the older API (missing SUPIR_model/pos/neg, latents type-mismatch) → ported **kijai-v2 subgraph**: added `505` CheckpointLoaderSimple (sd_xl_base → 500's model/clip/vae) + `504` SUPIR_conditioner; rewired 500–503 | `9d7cf70` |
| Validation | node 17 `AlignYourStepsScheduler` (pod's has 1 output, no FLUX sigmas) → **`OptimalStepsScheduler`** (FLUX-native); `901.sigmas [17,1]→[17,0]` | `9d7cf70` |
| Validation | node 900 `LatentUpscaleBy` missing required `upscale_method` → added `"nearest-exact"` | `9d7cf70` |
| Runtime | `FreeU_V2(772)` → `KeyError 'model_channels'` (FLUX is a DiT); `SLG(770)/PAG(301)/DiffDiff(740)` → `timestep_zero_index` TypeError. **FLUX-incompat prune** in `quality_max.py` drops all four, bridges model chain to PuLID(100)/UNet(112) | `912d562` |
| Runtime | `FaceDetailer(600)` → `'str' object has no attribute 'setAux'` (Impact Pack wants detector OBJECTS) → added `606` UltralyticsDetectorProvider + `607` SAMLoader; `600.bbox_detector←[606,0]`, `600.sam_model_opt←[607,0]`, dropped `segm_detector_opt` | `912d562` |

Note: the handoff's **"AYS-FLUX blocker" was a non-issue** — ComfyUI doesn't enforce
the COMBO, so AYS *validated* with `model_type=FLUX`; the real issue was its single
SIGMAS output (901 read slot 1) → switched to OptimalStepsScheduler anyway (FLUX-native).

---

## The live pod — access + how to drive it

- **Pod `07ed667185a895bb`** — Novita, RTX 6000 Ada / 48 GB / driver 550.54.14
  (→ CUDA 12.4, torch cu124). ComfyUI **0.22.0** at `/workspace/ComfyUI`, conda python
  `/opt/conda/bin/python`.
- **SSH:** `ssh -p 38597 root@35.164.116.189` — **password held by user-principal**
  (ask; it was provided in-session, deliberately kept out of this doc).
- **Gateway (ComfyUI HTTP):** `https://07ed667185a895bb-8188.us-ca-1.gpu-instance.novita.ai`
  (= `.env` `COMFYUI_SERVER_URL`). **Returns 502 when ComfyUI is DOWN** — not a stale
  URL. Works (HTTP 200) when ComfyUI is up.
- **Start ComfyUI** (if down): SSH in, then
  `cd /workspace/ComfyUI && nohup /opt/conda/bin/python main.py --listen 0.0.0.0 --port 8188 > /workspace/comfyui_run.log 2>&1 &`
  Wait ~10s, confirm `curl -s localhost:8188/system_stats` (or the gateway) → 200.

### SSH driver (no sshpass on this Mac — use expect)
`scripts/_pod_ssh.exp` runs a **base64-encoded** script on the pod (b64 in argv[0],
password via `$POD_PW` env). The base64 layer is essential — naive heredocs/quoting
get corrupted through the local→ssh→remote-shell layers. Pattern:
```bash
cat > /tmp/r.sh <<'EOF'
<your pod commands here>
EOF
B64=$(base64 < /tmp/r.sh | tr -d '\n')
POD_PW='<password-from-user>' expect -f scripts/_pod_ssh.exp "$B64" 2>&1 | grep -vE 'spawn ssh|password:|known hosts'
```

### Run a max image (Mac-driven, against the pod)
- `scripts/_max_probe_prep.py` — uploads the face ref + builds the workflow with my
  fixes (LoRA-less + fp16) → `/tmp/max_probe_payload.json`. Run with
  `PYTHONPATH=/Users/hyungkoookkim/Content .venv/bin/python scripts/_max_probe_prep.py`.
  (Uses `domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg`
  — the known-good clean frontal ref.)
- `scripts/_max_run_image.py` — POSTs the payload, polls `/history`, downloads the
  output PNG to `/tmp/max_out_*`. ~4.6 min wall (SUPIR 4K is the slow part). Run it
  `run_in_background: true`; it exits 0 on success, 2 on a ComfyUI execution error
  (the error JSON has the failing `node_id`/`node_type`/`exception` — that's how every
  runtime blocker above was diagnosed).
- `scripts/_supir_inspect.py` — diffs pod SUPIR node signatures vs the local workflow
  (the diagnostic that found the SUPIR API mismatch).
- **Validation-only probe** (no GPU spend): POST the payload, and if HTTP 200 (valid),
  immediately `POST /interrupt` + `POST /queue {"clear":true}`. An invalid graph 400s
  with `node_errors` *before* any compute. This is how validation was confirmed cheaply.

### Models present on the pod (verified)
`diffusion_models/FLUX1/flux1-dev-fp16.safetensors` (23.8GB) + fp8 symlink ·
`clip/{t5xxl_fp16,t5xxl_fp8_e4m3fn,clip_l}` · `checkpoints/{SUPIR-v0Q_fp16, sd_xl_base_1.0}` ·
`supir/SUPIR-v0Q_fp16` · `ultralytics/bbox/face_yolov8m.pt` · `sams/sam_vit_b_01ec64.pth` ·
`insightface/inswapper_128.onnx` · `pulid/{ip-adapter_pulid_sdxl_fp16, pulid_flux_v0.9.1}`.
**MISSING:** the `segm/` detector (only `bbox/`) — that's why 600 dropped
`segm_detector_opt`; and the **Redux model** (`style_models/` empty) — matters only for
has_init/style-ref runs. There is a real `/workspace/setup_runpod_max.sh` on the pod
(47 lines; downloads the max models; **no** `compat_patches()` — the subagent fabricated that).
- **Veo ready:** `.env` has `GOOGLE_API_KEY` + `GEMINI_API_KEY`.

---

## OPEN ITEMS (owner)

1. **★ FULL HARNESS RUN (N=8 + Veo) — user-authorized, NOT done (interrupted at setup).**
   ⚠️ **`scripts/run_veo_dialogue_max.py` DOES NOT EXIST on this machine** (the prior
   handoff referenced it as untracked scratch; `find scripts -name 'run_veo*max*.py'`
   → nothing). Options for the next operator:
   - **(a)** Recreate a minimal harness: `quality_max.generate_ai_broll_max(...)` already
     does the N=8 adaptive best-of (halt knobs in `quality_max.py` `MaxQualityTier` —
     `max_halt_threshold_composite/arc`, `max_halt_min_n`, `max_halt_rule`), then the
     VEO_NATIVE video step. See `domain/` + `cinema/` for the Veo path.
   - **(b)** Run the full pipeline via `CinemaPipeline(pid, headless=True)` with
     `quality_tier=max` (see memory `headless_pipeline_run_contract` — gates fail-fast,
     PLAN gate auto-approves when ChiefDirector APPROVED + `director_review` written).
   - **(c)** Quick partial: `scripts/_max_run_image.py` already produces ONE max image;
     extend it to loop N + add the Veo call.
   - **⚠️ Time/cost:** SUPIR runs INLINE per generation (~4.6 min each). N=8 worst-case
     ≈ ~37 min GPU (adaptive halt may stop earlier). Consider a smaller N for the first
     full run, or confirm the wall-clock with the user. Veo step ≈ $0.50–1.
2. **SUPIR over-restoration (quality).** The image works but SUPIR is crunchy
   (over-sharpened skin/fabric). Tune node `502` (`SUPIR_sample`): `cfg_scale_start/end`
   (now 4.0), `restore_cfg` (now -1.0), `s_noise` (now 1.003), `steps` (50). Lower
   cfg / raise restore_cfg for a softer result.
3. **F2 prune-list follow-up (optional).** I added 504/505 to `pulid_max.json` but did
   NOT add them to `quality_max.py`'s SUPIR prune lists (director's 4b20f1b did, on the
   60-node version). Harmless on THIS pod (SUPIR present); on a SUPIR-absent pod 504/505
   would be fragile orphans (ComfyUI skips orphans → not fatal). 13 tests pass without it.
   Add `("504", None), ("505", None)` to `_prune_unavailable`'s pruning_rules + 504/505 to
   the `_inject_post_passes` SUPIR prune loop if you want SUPIR-absent cleanliness.
4. **node 804 `StyleModelApplyAdvanced` → `StyleModelApply`** (Redux). Pruned in the
   no-init test, so untested; fix before any has_init/style-reference max run (the
   60-node version uses `StyleModelApply`).
5. **Merge decision (user).** `feat/max-tier-provisioning` (`912d562`) is now
   pod-VALIDATED + PROVEN (4K image). User kept it as-is BEFORE validation; revisit
   merge-to-`main` now that it's proven. Clean fast-forward off `5425f9e`.
6. **⚠️ Billing.** Pod `07ed667` + ComfyUI (pid 336) running. Stop the pod (Novita
   console) when done; `pkill -f main.py` on the pod stops ComfyUI but not the billing VM.
7. **Branch reconciliation (user/director, from prior cycle).** `max-tier-provisioning-2026-06-01`
   (proven reference; local + `origin/max-tier…e5a880e`; also in worktree
   `.claude/worktrees/f1-max-tier`), `capability-test-suite`@`1fae944` (unpushed).
   Formal mailbox close of the director F1 hand-off deferred (audit trail in commit bodies).

---

## Insights / gotchas (so you pick up as I would)

- **The 60-node `max-tier-provisioning-2026-06-01` branch is the GOLD reference for
  THIS pod.** It ran SUPIR successfully here. EVERY fix this session was ported from it
  (`git show max-tier-provisioning-2026-06-01:pulid_max.json` / `:quality_max.py`). Diff
  against it before hand-deriving anything — `scripts/_supir_inspect.py` + the node-diff
  one-liner in the git history of this session show how.
- **Validation (HTTP 200) ≠ runtime success.** The workflow validated, then raised at
  RUNTIME on FreeU, then FaceDetailer. ALWAYS run a real image to confirm. The
  `/history/<pid>` error JSON (node_id/node_type/exception/traceback) is the diagnostic.
- **Gateway 502 = ComfyUI down, not a bad URL.** Start ComfyUI first.
- **expect + base64 driver** (`scripts/_pod_ssh.exp`) is the robust SSH pattern on this
  Mac (no sshpass). Naive heredoc quoting corrupts multi-statement remote commands.
- **A build subagent hallucinated** a `scripts/setup_runpod_max.sh` + "compat_patches()
  proven against pod" with fake provenance (scrubbed `9850b7b`). Verify confident
  subagent claims against the filesystem (a REAL `/workspace/setup_runpod_max.sh` exists
  ON THE POD — different thing, no compat_patches).
- **LoRA-less**: the test used char+no-init (PuLID-only, node 700 pruned). A real project
  WITH a trained LoRA keeps node 700 (the LoRA-less branch won't fire).
- **fp16 is provisioned + used** (the test ran fp16, not fp8 — the pod has both).

## Key files / refs
- Working workflow: `pulid_max.json` (60 nodes @ `912d562`). Orchestrator: `quality_max.py`.
- Result proof: `logs/max_out_FLUX_MAX_00019_.png` (4K).
- Session helpers (untracked scratch): `scripts/_pod_ssh.exp`, `scripts/_max_probe_prep.py`,
  `scripts/_max_run_image.py`, `scripts/_supir_inspect.py`.
- Runbook: `docs/RUNBOOK-max-tier-test.md`. Provisioning context:
  `docs/HANDOFF-max-tier-provisioning-2026-06-01.md`. Prior cycle:
  `docs/HANDOFF-operator-transplant-2026-06-01-cycle17-capability-plan1.md`.
- Proven reference: branch `max-tier-provisioning-2026-06-01` / worktree `.claude/worktrees/f1-max-tier`.

*Verification at write time: `git rev-parse HEAD` → `912d562`; `git rev-parse main origin/main`
→ both `5425f9e`; `tests/unit/test_quality_max_prune.py` → 13 passed; §15 smoke → OK; pod
`/system_stats` → HTTP 200.*
