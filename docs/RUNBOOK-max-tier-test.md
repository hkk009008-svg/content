# RUNBOOK — Running the max-tier test

*Created 2026-06-01 (operator-seat). Actionable steps to take the max-tier
(`quality_tier=max`) path from "hard-fails validation" to a finished
max-quality clip. Companion to the context doc
[HANDOFF-max-tier-provisioning-2026-06-01.md](HANDOFF-max-tier-provisioning-2026-06-01.md).*

## What this is

The max-tier test = run `scripts/run_max_harness.py` — a 3-stage chain:
**(1)** `generate_ai_broll_max` N=8 best-of keyframe on the live pod (fp16 FLUX +
PuLID LoRA-less + FaceDetailer + ReActor + SUPIR 4K; validated `pulid_max.json`
queue, **no** `prompt_outputs_failed_validation`) → **(2)** one `VEO_NATIVE`
image→video clip with synced native audio (Veo 3.1 Vertex, 8s/720p) → **(3)**
an ffprobe verdict: PASS iff the final mp4 has BOTH a video and an audio stream.

It previously hard-failed because the pod is provisioned production-only. The
offline prep below (the four prep commits are now on `main`, last being
`9850b7b`) closes the code-side gaps and makes provisioning repeatable; the
pod-side steps still need an operator with the pod up + (for gated weights) a
Hugging Face token.

## Prerequisites

- **Pod up + reachable.** ComfyUI at `COMFYUI_SERVER_URL` (`.env`); `curl
  $COMFYUI_SERVER_URL/system_stats` → HTTP 200. SSH for provisioning (password
  held by the user-principal). ⚠️ **The pod bills by the second — stop it when
  idle.**
- **Hugging Face token** (`export HF_TOKEN=hf_…`) with the licenses accepted for
  the gated weights: `black-forest-labs/FLUX.1-dev` (only if `--max-fp16`) and
  `black-forest-labs/FLUX.1-Redux-dev`.
- **Spend awareness.** Provisioning downloads are large (SUPIR + SDXL base; with
  `--max-fp16`, ~23 GB FLUX + ~10 GB T5). The run itself is GPU + (for the
  VEO_NATIVE shots) Veo API spend — the harness has a `budget_limit_usd=5`
  tripwire.

## Step 1 — Provision the pod

On the pod (after `setup_runpod.sh` has done the production install at least
once):

```bash
# fp8 first-run path (no large FLUX download; matches the precision default):
bash scripts/setup_runpod.sh --max

# OR the true-max path (adds fp16 FLUX + T5; needs HF_TOKEN):
export HF_TOKEN=hf_...
bash scripts/setup_runpod.sh --max-fp16
```

`--max` is **additive** — with no flag the script behaves exactly as the
production setup. It installs the max custom nodes (ComfyUI-SUPIR,
Impact-Pack + Impact-Subpack, Detail-Daemon) and downloads the max model
weights, idempotently.

**On-pod VERIFY items (flagged in the script — confirm these manually):**

| Item | Why verify |
|---|---|
| `inswapper_128.onnx` path | Placed at `models/insightface/`; ReActor may also want it under `custom_nodes/ComfyUI-ReActor/models/insightface/` — symlink if ReActor fails to load. |
| `face_yolov8m-seg2_60.pt` filename | Cross-check `pulid_max.json` node 600 `segm_detector_opt` against the file the `Bingsu/adetailer` repo serves. |
| SUPIR weight path | `ComfyUI-SUPIR` may read from `checkpoints/` or `supir/` depending on version (a symlink is added); confirm against the node README, and whether an SDXL base is required. |
| Gated downloads | `flux1-redux-dev.safetensors` and (for `--max-fp16`) `flux1-dev.safetensors` skip-not-abort without `HF_TOKEN`. The script prints a WARNING; provide the token + accept the license, or place them manually. |
| Aesthetic predictor | Not auto-downloaded (dest/filename unverified); the script prints a NOTE. Inspect the consuming node on-pod. |
| AYS-FLUX + StyleModelApplyAdvanced | ComfyUI **core** nodes needing a recent build — the script prints the manual `git pull` + `/object_info` checks (it does **not** auto-update core). |
| Node compat | If `ComfyUI-SUPIR` / `ComfyUI-PuLID-Flux` fail to load after a core update, check each node's GitHub for a compatible commit (not automated). |

## Step 2 — Blocker → how it's addressed → verify

The handoff's verified blockers, mapped to what now closes each:

| Blocker (node) | Addressed by | Verify on-pod |
|---|---|---|
| UNETLoader 112 wants `flux1-dev-fp16` | **fp8 re-point** (`_apply_model_precision`, default) re-points 112 → `flux1-dev-fp8`; OR `--max-fp16` provisions the fp16 file | quality_max logs `model precision: fp8 (UNet/T5 re-pointed…)`; no 112 validation error |
| DualCLIPLoader 11 wants `t5xxl_fp16` | same fp8 re-point (→ `t5xxl_fp8_e4m3fn`) / `--max-fp16` | log line above; no node-11 error |
| LoraLoader 700 wants `PLACEHOLDER_char` | **LoRA-less prune** — when no `char_lora`, node 700 is pruned and PuLID carries identity (logged); OR train a per-char LoRA (`prep/lora_training.py`) for full fidelity | log `no per-char LoRA -> running LoRA-less`; no PLACEHOLDER in the queued graph |
| AlignYourStepsScheduler 17 (FLUX) | ComfyUI **core** update (`--max` prints the steps) | `curl …/object_info/AlignYourStepsScheduler` shows a FLUX `model_type` |
| ReActorFaceSwap 610 `inswapper_128.onnx` | `--max` downloads it | file present; ReActor loads (see VERIFY note on path) |
| LatentUpscaleBy 900 param/version | ComfyUI core update | node 900 validates against the current build |
| SamplerCustomAdvanced 901 IndexError | downstream of the above | re-check after 112/11/17/900 fixed |
| SUPIR / FaceDetailer / Redux / DetailDaemon (also-missing) | `--max` installs them; **and** if any are still absent they now **prune cleanly** (F1/F1b + availability coverage, merged to `main` `5425f9e`) instead of dangling → silent production fallback | `/object_info` has the classes, OR the run logs a clean prune with no `prompt_outputs_failed_validation` |

**Why the F1/F1b backstop matters here:** F1/F1b (on `main`) ensure the
max workflow validates correctly *once the max nodes are present* — for the
no-character (landscape) and character-no-init (text-to-image) shot types the
earlier max attempt never exercised. Without them, a fully-provisioned max pod
would still dangle-and-fall-back on those shots. See
`tests/unit/test_quality_max_prune.py` (13 passing invariants).

## Step 3 — Run the test

```bash
# true-max (fp16) — run_max_harness.py DEFAULTS to fp16; needs --max-fp16 provisioning (fp16 weights):
.venv/bin/python scripts/run_max_harness.py

# fp8 path (lighter; the harness defaults to fp16, so request fp8 explicitly):
MAX_MODEL_PRECISION=fp8 .venv/bin/python scripts/run_max_harness.py
```

(Precision is read at call-time via `MAX_MODEL_PRECISION` by
`quality_max._apply_model_precision`. `run_max_harness.py` **defaults to fp16**
— the full-capability path, which needs the fp16 weights present; set
`MAX_MODEL_PRECISION=fp8` for the lighter first-run.)

Watch the run's stdout (the harness writes `logs/max_harness_keyframe.jpg` +
`logs/max_harness_final.mp4`) for: the `MAX-TIER FULL HARNESS` banner →
`[STAGE 1] generate_ai_broll_max — N=8 best-of on the pod` (queues `pulid_max.json`,
no `prompt_outputs_failed_validation`; ArcFace-scored, full N=8) →
`[STAGE 1] OK — keyframe at …` → `[STAGE 2] VeoNativeAPI generate_video — vertex …
8s/720p, audio=True` → `[STAGE 3] final ffprobe` → `VERDICT: ✅ PASS`.

## Step 4 — Success criteria

- **Stage 1 — keyframe.** `generate_ai_broll_max` returns a path and
  `logs/max_harness_keyframe.jpg` exists (pod reachable, not all candidates
  failed; **no** `prompt_outputs_failed_validation` on the pod queue). N=8 runs to
  completion — note the aesthetic scorer is absent locally, so composite is
  **ArcFace-driven** and there is **no 0.97 early-halt**; the full N=8 executes.
- **Stage 2 — Veo clip.** Requires the **Vertex** backend (native audio is
  Vertex-only; the harness ABORTs otherwise), 8s/720p, `generate_audio=True`.
- **Verdict (`ffprobe` gate).** `VERDICT: ✅ PASS` (exit 0) = `logs/max_harness_final.mp4`
  exists with BOTH a video **and** an audio stream. `⚠️ PARTIAL` (exit 1) = video but
  no audio; `❌ FAIL` (exit 4) = no usable video; `ABORT` = keyframe failed (exit 2)
  or Veo backend not Vertex (exit 3).

## What the prep branch changed (now merged to `main`)

| Commit | Change |
|---|---|
| `5a229d2` | LoRA-less max path (prune node 700 when no `char_lora`) + availability-prune test coverage |
| `4d33868` | fp8/fp16 model-precision re-point (`_apply_model_precision`) |
| `339b674` | `setup_runpod.sh --max` / `--max-fp16` provisioning path |
| `9850b7b` | scrub a fabricated `setup_runpod_max.sh` reference from the script |

Already on `main` (`5425f9e`): F1 (`a302585`) + F1b (`5425f9e`) — the
validation backstop for no-char / char-no-init max shots.
