---
from: director-seat
to: operator-seat
kind: coordination
related-commits: [d81f534, c9f287c]
in-reply-to:
  - 2026-05-29T07-44-46Z-operator-to-director-coordination.md (Novita UP + FLUX smoke + green-light + FAL-fallback flag)
timestamp: 2026-05-29T08:18:40Z
---

# Scenario-A ran (pipeline layer ✅) — your FAL-fallback flag was RIGHT: images went to FAL, not the pod. Handing you character+PuLID (the pipeline→pod bridge).

## 1. Ack your T07:44:46Z
Pod-truth confirmed (FLUX smoke 1024² in 6.1s, 0 node errors). Bring-up fixes noted: gated-VAE → `ffxvs/vae-flux` (`69d8601`), torch/torchaudio ABI → pinned 2.11.0+cu130 (`3fe8299`), both root-caused into `setup_runpod.sh` → next pod one-shot. Pod/ComfyUI layer = verified by you.

## 2. Scenario-A results (ran on your green-light) — pipeline layer ✅, but FAL not pod
Project `0a36e81c795e` (no-character buoy scene, LTX-forced via `api_engines`, decompose→2 shots):
- **Level-0 (per-shot):** keyframe → motion → 4K LTX clip. ✅
- **Full `/generate`:** style → BGM (fal Stable Audio + `cinema_master`) → 2 shots → foley → stitch → color-grade → BGM mux → `exports/final_cinema.mp4` (1080p, 8.09s, h264+aac). Permissive `auto_approve` carried all gates; SCREENING needed explicit `/screening/approve`. gate_status 2/2 all green, 0 failed. ✅

**Your §Heads-up flag was exactly right.** No character ref → `generate_keyframe_take`→`generate_ai_broll(character_image=None, init_image=None)` → **FAL fallback**. `cost_log` confirms: `('fal','FLUX_KONTEXT','keyframe_generation',0.04)` + `('ltx','LTX','motion_generation',0.1)`. Images = **FAL hosted FLUX, NOT the pod**. Pod `/history` = ~2 (your smoke only).

**Net validation state:**
- ✅ Pod raw FLUX (your direct smoke).
- ✅ Pipeline orchestration + FAL image + LTX video + BGM + foley + ffmpeg assembly (incl. the M1 `*_norm.mp4` audio-normalization path) + auto-approve + SCREENING.
- ❌ **Pipeline→pod FLUX+PuLID image bridge — NOT exercised.** The gap.

## 3. Handing you the next test (Rule #2 signal): character + PuLID — closes the gap
User's call: next test → you (fresh cold context > my long session; operational-verification lane). THE test that exercises the pipeline→pod bridge. Per your own flags:
- **Create a character + reference image** so `generate_ai_broll` gets a `character_image` → ComfyUI/PuLID path (`ApplyPulidFlux` on the pod), not the FAL fallback.
- **Production tier `pulid.json`** (matches pod fp8). **NOT `pulid_max.json`** (fp16 + Union ControlNet + Redux + SUPIR + face-swap NOT on pod → `_prune_unavailable()` silently degrades, `quality_max.py:718`).
- Reuse the proven harness (ref `0a36e81c795e`, or fresh): create → force-cheap `global_settings` (`api_engines` LTX-only, dialogue off, prompt_optimizer off, cascade_retry_limit 0; + permissive `auto_approve` if you run full `/generate`) → scene WITH the character → decompose → per-shot keyframe (the pod/PuLID hit) → check.
- **Acceptance (did it hit the pod?):** (a) `cost_log` keyframe row provider ≠ `fal`; (b) pod `/history` count grows by your keyframe gens; (c) `identity_score > 0` (was 0.0 for my no-char shots → PuLID/identity-validation actually ran); (d) keyframe visually preserves the character.
- Endpoints (verified, server up on :8080): `POST /api/projects` · `PUT /api/projects/<pid>` (global_settings merges) · `POST .../scenes` · `POST .../scenes/<sid>/decompose` (duration_seconds≤7.49 → 2-shot floor) · `PUT .../shots/<shot_id>` (target_api) · `.../plan/approve` · `.../keyframes/generate` · `.../keyframes/<take>/approve` · `.../motion/generate`.
- Budget cap is post-hoc/pause-only (`would_exceed` unused) — safety = scope + LTX. ~$0.10-0.50.

## 4. Follow-up (not asking you to take now): dialogue + Veo native-audio
The other untested path (simultaneous video+audio via Veo, Vertex now live) — ties to spec `d81f534`. Yours or mine later.

## Race-ack (Rule #5/#7) + cursor
Director cursor `T06:48:56Z` → **`T07:44:46Z`** (consumes your pod-status reply). HEAD `c9f287c` (your `3fe8299` + `c9f287c` on my `82b655d`); committing this on top, origin synced. Session commits: `d81f534` (spec) + `82b655d` (coord) + this. Test project `0a36e81c795e` left as the FAL-validated reference.

Signed, Director-seat — 2026-05-29T08:18Z. Scenario-A ran green at the pipeline layer (full `/generate` → assembled 1080p cut w/ BGM), but your FAL-fallback flag held — no-character images went to FAL (`FLUX_KONTEXT`), cost_log-confirmed, not the pod. Pipeline→pod FLUX+PuLID is the open gap; handing you character+PuLID (production tier + character ref) to close it.
