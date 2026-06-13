# HANDOFF — Full max-tier provisioning + max-quality run

*Author: director-seat · 2026-06-01 · Scope: provision the GPU pod for TRUE max-tier
(`quality_tier=max`) and produce a max-quality clip. Production tier already works
end-to-end; this is purely the max-tier provisioning gap.*

---

## UPDATE — 2026-06-01 (operator prep: blockers narrowed + F1/F1b backstop)

**Actionable runbook: [RUNBOOK-max-tier-test.md](RUNBOOK-max-tier-test.md).**
Start there to run the test; this doc is the context/blocker analysis behind it.

Since this snapshot, offline prep on branch `feat/max-tier-provisioning`
(4 commits) plus the F1/F1b fixes on `main` have closed or narrowed every
code-side blocker below:
- **git state corrected:** `8cf0f07` is now in `origin/main` — `main` =
  `origin/main` = `5425f9e` (the F1/F1b merge carried it up). The "UNPUSHED"
  lines in *State at handoff* and the *Verification* footer are superseded.
- **LoRA (node 700):** LoRA-less prune path added (`5a229d2`) — runs PuLID-only
  without a trained LoRA; training remains the full-fidelity option.
- **fp16 models (112/11):** fp8 re-point (`4d33868`) lets the fp16-canonical
  workflow run on the fp8 pod; `--max-fp16` provisions true fp16.
- **Max nodes (SUPIR/Impact/Redux/AYS/DetailDaemon/ReActor):**
  `setup_runpod.sh --max` installs them (`339b674`); and if any are still absent
  they now prune cleanly (F1/F1b, `5425f9e`) instead of silently falling back.

The blocker table + provisioning plan below remain the authoritative *analysis*;
the runbook turns them into ordered steps with a verify column.

---

## TL;DR

- **Production tier is fully working** — Veo native-audio E2E proven (consistent
  character + synced audio + assembled video). See "What works" below.
- **Max-tier hard-fails on the current pod** — `pulid_max.json` fails ComfyUI
  validation because the pod is provisioned **production-only** (fp8 models, no
  per-char LoRA, SD-only AlignYourSteps, ReActor model + SUPIR/FaceDetailer/Redux
  absent). It is **not graceful degradation** — the workflow can't even queue.
- **Your job:** close the provisioning gap (table below), then re-run
  `scripts/run_veo_dialogue_max.py`.
- **Two bug fixes already shipped this session** (composite gate) — don't redo them.

---

## State at handoff (all verified)

- **git:** HEAD = `8cf0f07` (tier-aware composite default) *at handoff time*.
  **SUPERSEDED (see UPDATE above):** `8cf0f07` is now in `origin/main`; `main` =
  `origin/main` = `5425f9e`. *(Original claim: 1 ahead of `origin/main` =
  `d55d487`, unpushed.)*
  - `c917bc1` fix(auto-approve): composite→identity fallback (pushed, in `d55d487`)
  - `8cf0f07` fix(auto-approve): tier-aware default 0.97 max / 0.60 production (local)
- **Tests:** `pytest tests/unit/` → 1282 passed / 3 skipped / 0 failed; `§15 ci_smoke` OK.
- **Pod (Novita):** RTX 6000 Ada, 48 GB VRAM, **100 GB disk** (instance + network),
  ID `07ed667185a895bb`. Driver **550.54.14 → CUDA 12.4 max** (so torch is pinned to
  **cu124**, auto-detected by `setup_runpod.sh` since `bf7293c`; cu130 would fail here).
  - SSH: `ssh -p 38597 root@35.164.116.189` (password held by user-principal).
  - ComfyUI: `https://07ed667185a895bb-8188.us-ca-1.gpu-instance.novita.ai`
    (= `.env` line 26 `COMFYUI_SERVER_URL`). `/system_stats` → HTTP 200 at handoff.
  - ⚠️ **Pod bills by the second — stop it when not provisioning/running.**

### What works (do NOT re-investigate)
- **Two-women problem = SOLVED.** Root cause was a weak reference (dim/dramatic
  `canonical.jpg` → PuLID identity ~0.45). Fix: use a **clean, frontal, evenly-lit
  reference** — `domain/projects/cfd3f0967eb3/characters/char_b9c8bcfe9af0/lighting_outdoor.jpg`
  (identity jumped to 0.6–0.79; both shots consistent). The max run-harness already
  points at it.
- **Composite-gate bug = FIXED** (`cinema/auto_approve.py`): `_best_take_composite`
  falls back to `identity_score` when `composite` absent (`c917bc1`), and the
  `image_min_composite` default is tier-aware — **0.97 for max** (composite IS written
  there), 0.60 for production (`8cf0f07`). So in max-tier the 0.97 gate gates on the
  real composite. No further gate work needed.
- **Production Veo E2E:** `scripts/run_veo_dialogue_gated.py` (`quality_tier=production`)
  produces a finished consistent-character video. Use it as the known-good baseline.

---

## The max-tier blockers (verified from `logs/veo_e2e_max.log`)

The max attempt (`scripts/run_veo_dialogue_max.py`, project `5cd9401154f8`) reached
`[quality_max] portrait | N_max=8` then failed `prompt_outputs_failed_validation`
**8×** (once per best-of attempt). Exact node errors:

| Node (id) | `pulid_max.json` wants | Pod has | Provisioning action |
|---|---|---|---|
| `UNETLoader` (112) | `FLUX1/flux1-dev-fp16.safetensors` | **fp8 only** | DL fp16 FLUX (~24 GB) → `models/diffusion_models/FLUX1/`, **OR** re-point node 112 to the fp8 file |
| `DualCLIPLoader` (11) | `t5xxl_fp16.safetensors` | **fp8 only** | DL t5xxl fp16 → `models/clip/`, **OR** re-point to `t5xxl_fp8_e4m3fn.safetensors` |
| `LoraLoader` (700) | a per-char LoRA (`PLACEHOLDER_char.safetensors`) | **none trained** | Train a character LoRA (see `prep/lora_training.py` / `api_train_lora` in `web_server.py`) **OR** confirm/patch `quality_max.py` to run LoRA-less |
| `AlignYourStepsScheduler` (17) | `model_type: FLUX` | node present but **SD1/SDXL/SVD only** | Upgrade the AYS node to a FLUX-capable build (node-version mismatch, not just missing) |
| `ReActorFaceSwap` (610) | `inswapper_128.onnx` | **not installed** | Install `inswapper_128.onnx` into ReActor's models dir |
| `LatentUpscaleBy` (900) | `upscale_method` (required) | present but **param/version mismatch** | Reconcile `pulid_max.json` node 900 with the pod's node version |
| `SamplerCustomAdvanced` (901) | valid `samples` | inner-validation `IndexError` | Downstream of the above — recheck after fixing |

**Also missing** (from a live `/object_info` audit, even if not in the error list —
`_probe_node_availability` strips them pre-queue): **`SUPIR_model_loader_v2` / `SUPIR_sample`**
(4K restore), **`FaceDetailer`** + **`UltralyticsDetectorProvider`** (Impact Pack),
**`StyleModelApplyAdvanced`** (FLUX Redux), **`DetailDaemonSamplerNode`**.

> **Key insight for the next director:** `setup_runpod.sh` is **production-tier only**
> (it installs cubiq PuLID + balazik PuLID-Flux + IPAdapter + ReActor *node* + InsightFace,
> and downloads **fp8** FLUX/T5). `pulid_max.json` was authored against **fp16 models +
> newer node versions + a per-char LoRA** that the script never provisions. So max-tier
> provisioning = (a) fp16 models (or re-point the workflow to fp8), (b) the heavy max
> nodes (SUPIR/Impact-Pack/Redux), (c) node-version alignment (AYS-FLUX, LatentUpscaleBy),
> (d) ReActor weights, (e) a character LoRA. It is a real, multi-step provisioning task —
> NOT a "flip `quality_tier=max`" toggle.

---

## Suggested provisioning plan

1. **Decide model precision.** fp16 (true max quality, ~24 GB FLUX + ~10 GB T5 DL) vs
   re-point `pulid_max.json` nodes 11/112 to the existing fp8 files (faster, slightly
   lower ceiling). The 100 GB disk supports fp16.
2. **Install the missing max nodes** on the pod (`/workspace/ComfyUI/custom_nodes`):
   `ComfyUI-SUPIR` (Kijai) + SUPIR weights, ComfyUI Impact Pack (FaceDetailer +
   UltralyticsDetectorProvider + a bbox detection model), FLUX Redux
   (`StyleModelApplyAdvanced` + redux model), a FLUX-capable AlignYourSteps,
   DetailDaemon; and ReActor's `inswapper_128.onnx`. (See `OPERATIONS.md` §5 max-tier
   node list + §6 model list.) Extend `setup_runpod.sh` with a `--max` provisioning
   path so this is repeatable (currently it's production-only).
3. **Character LoRA.** Determine whether `quality_max.py` *requires* the per-char LoRA
   (node 700 `PLACEHOLDER_char`) or can run without. If required, train one via the
   LoRA path; if optional, patch the workflow to skip it.
4. **Re-run** `scripts/run_veo_dialogue_max.py` (already set: `quality_tier=max`,
   hair-pinned prompt "short dark wavy bob", `ip_adapter_weight=0.95`, clean ref,
   `image_min_composite=0.60` explicit). Watch `logs/veo_e2e_max.log` for `queue_prompt`
   success → N=8 best-of (`seed=… composite=…`) → SUPIR 4K → 2 `VEO_NATIVE` shots → video.
5. **Verify:** no `prompt_outputs_failed_validation`; N=8 best-of runs; composite
   ~0.92–0.97 (the real 0.97 gate engages); final video at higher res; compare fidelity
   to the production baseline (`domain/projects/aa777d858e71/exports/final_cinema.mp4`).

---

## Run harnesses (untracked scratch — `scripts/`)
- `run_veo_dialogue_max.py` — **the max variant** (quality_tier=max, hair-pinned, ip 0.95). Your entry point.
- `run_veo_dialogue_gated.py` — production, real keyframe gate (known-good baseline).
- `run_veo_dialogue_test.py` — original bypass-gates E2E (proved the Veo path).
- All are headless (`CinemaPipeline(pid, headless=True)`), VEO_NATIVE-forced via
  `api_engines`, screening off, `budget_limit_usd=5` tripwire, single 1-shot Mara
  dialogue. None are committed (decide whether to keep).

## Source map
- Max-tier orchestration + N=8 best-of + halt thresholds: `quality_max.py`
- Max workflow JSON: `pulid_max.json` (repo root)
- Pod bootstrap (production-only): `scripts/setup_runpod.sh`
- Auto-approve gate (fixed this session): `cinema/auto_approve.py`
- Tier routing: `workflow_selector.py` (`MAX_QUALITY_TEMPLATES`)

## Open items / reminders
- `8cf0f07` is **unpushed** (1 ahead of origin). Push needs explicit auth (direct-to-main soft-block).
- Pod is **billing** — stop it between provisioning sessions.
- Untracked: the 3 `run_veo_dialogue_*.py` harnesses + `logs/`.
- Optional, not blocking: tighter production fidelity is achievable *now* without max-tier
  (hair-pin + ip 0.95 at `quality_tier=production`) if you want a quick win first.

---

*Verification (per ADR-013 / Rule #1–3):*
- git state: `git rev-list --left-right --count origin/main...HEAD` → `0  1` (HEAD ahead 1).
- blockers: `logs/veo_e2e_max.log` tail (`prompt_outputs_failed_validation` node errors, verbatim above).
- node inventory: live `curl <pod>/object_info | grep -oE '<node>'` (2026-06-01).
- tests: `.venv/bin/python -m pytest tests/unit/ -q` → 1282 passed / 3 skipped; `scripts/ci_smoke.py` → OK.
- pod: `curl <pod>/system_stats` → HTTP 200; driver/CUDA from `nvidia-smi` on the pod (550.54.14 / 12.4).
