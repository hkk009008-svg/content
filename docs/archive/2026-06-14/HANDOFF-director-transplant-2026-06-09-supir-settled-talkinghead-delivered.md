# Director transplant handoff — 2026-06-09: SUPIR cfg SETTLED (clean A/B) + talking-head delivered (general-use); #1-pickup cluster fully discharged; 11 commits pushed

**Supersedes** `docs/HANDOFF-director-transplant-2026-06-09-max-tier-pod-validated.md`
(its #1-pickup cluster — operator director-requests ①③ + the 4 evidence-backed
follow-ups #1–#4 — is FULLY DISCHARGED this session).

## Ground truth (verified this wrap)
- **HEAD == `b49600e` == `origin/feat/max-tier-provisioning`** (pushed this session, USER-gated ×2: `ffdd0ec` then `b49600e`). **Ahead 34 of `origin/main` `1870e59`** (GREEN, portrait 9:16 live).
- **§15 ci_smoke OK** at `b49600e`. Full unit suite **1948 passed / 0 failed** (`env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q` → `1948 passed, 10 subtests passed in 46.31s`, this wrap).
- **0 unread** for director (cursor `08:30:25Z`; via `status.py mailbox-unread director`).
- **Operator OFFLINE** (wrapped `c3c0be6`, NOTHING OWED). Director owns the full loop + doc-maintenance.
- `claude --version` 2.1.169.

## What director did this session

### 1. Discharged the ENTIRE #1-pickup cluster
- **① Rule #17 v5.6 dogfood retro + fixed VERIFIED-STALE `CLAUDE.md:1728-29`** (`a30f5b2`). Verdict: net-positive, retained; ~18-run arc; runtime 2.1.169 (gate satisfied). ADR-013 same-commit.
- **③ Rule #20.1 advisory** (`2089c7c`) — prefer `status.py mailbox-unread` over hand-rolled `ls|awk`.
- **#1 hires_fix doc-truth** (`1cee016`) — `pipeline_status.toml` stubbed→wired + killed stale `quality_max.py:616` comment. Source-verified: `_inject_post_passes` ACTIVATES (not prunes) 900/901/902.
- **#2 SUPIR cfg — SETTLED via a CLEAN same-base A/B on the pod** (`ffdd0ec` + `23edc51`). cfg **2.8 arc 0.7939 ≥ 2.0 arc 0.7886** (ComfyUI cached the base → clean same-base isolation). The handoff's "4.0→2.0 in MAX_QUALITY_TEMPLATES" was **doubly wrong**: templates already 2.8; the only 4.0 is a DEAD fallback; "2.0 faster" was a warm-cache artifact. **KEPT templates at 2.8**; retired the dead fallbacks (cfg 4.0→2.8 `ffdd0ec`, steps 50→40 `23edc51`). Rule #17 blast-radius `wf_e75d4ff6-f34` (spot-checked 5/5).
- **#3 hires floor SAFETY fix** (`3ec83b4`, TDD) — overlay floor `0.2→0.40`. Closed a **LIVE UI exposure**: `AdvancedSection.tsx:311` slider `min={0.2}` let an operator request 0.25, which the overlay clamp passed to node 18 → pod-proven catastrophic disintegration (arc 0.48). Operator cold Lane V = ✅ SAFE.
- **#4 §5.4 clean-bg recipe** (`52bbd42`), **CORRECTED** (`01b3911`). While driving the talking-video work, discovered the **FLUX max-tier keyframe has NO negative channel** (BasicGuider, `pulid_max.json` node 22; only the positive `CLIPTextEncode` 122; `generate_ai_broll_max`'s `negative_prompt` arg is unwired). Rewrote the recipe's people-exclusion/neck advice to **positive phrasing**.

### 2. Pod validation (user restarted the pod for the SUPIR A/B)
- Clean SUPIR cfg A/B (above). **Neck-artifact validation**: positive anatomy phrasing mitigates the elongated-neck artifact (arc 0.8063 vs 0.7939 baseline; visually natural neck/collarbone) — validates the §5.4 positive-anatomy advice. Background-smear confirmed base-FLUX/prompt (prompt-fixable, not a post-pass).

### 3. Talking-head videos (user "do both" → LoRA + neck + 30s talking video; then "30 different face 9:16", "make it photoreal")
- **LoRA training BLOCKED (reported honestly)** — training is a LOCAL CUDA subprocess (`prep/lora_training.py:421`); ai-toolkit NOT installed + this Mac has no CUDA; Aria has 1 registered ref vs a hard ≥15 gate. Needs a dedicated pod-side setup session. (Mechanism map `wf_8fdd88a5-495`.)
- **Aria talking head** — 21.4s 1:1, `generate_motion_take` with `optimizer_cache.spec.purpose="talking_head_full"` cache-patch + `dialogue_voice_mode=overlay` + `lip_sync_mode=generation`; Hedra Character-3 generation lip-sync; sync 0.996, identity 0.845.
- **Photoreal 30s vertical** — `logs/talkinghead_photoreal_9x16.mp4` (26.5s, 720×1078, Bella voice). Used an EXISTING photoreal reference (`bf1a4e9e8a9a/char_b29189531779` qipao woman) directly via Hedra, because the no-PuLID max-tier face gen **over-cooks** (3 attempts; chain co-tuned for a PuLID base — hires-OFF is worse, node 901 @ denoise 1.0). **User verdict: "acceptable for general use not max tier."** Capability gap recorded → [[project_talking_head_quality_tiers]].

### 4. Closed operator Lane V findings (Rule #15) + doc-maintenance
- supir_steps Rule #13 sibling (`23edc51`); §5.4 correction + dialogue-prose hand-off (deleted helpers) + anchor-sync (`01b3911`, both docs verify clean; `--fix` R-OP-1 spot-checked). **FE slider V1 + V-MINOR-3 = backend-only-defense ACCEPTED** (optional FE follow-up). **V-MINOR-2 still OPEN** (small — see below).
- **Pushed** USER-gated: `ffdd0ec` then `b49600e` (FF on origin/feat).

### 5. Memories saved
- `feedback_show_media_in_preview` — show media via `open "<abs>"` + Bash `dangerouslyDisableSandbox:true` (sandbox blocks GUI silently; `open -a Preview` won't play video).
- `project_talking_head_quality_tiers` — Hedra-direct = general-use; max-tier needs the full cinematic pipeline; no-PuLID new-face over-cook gap.

## ⭐ #1 PICKUP / open items (next session)
- **POD STILL UP (metered) — USER must terminate in the Novita console.** No further pod work is needed.
- **Max-tier new-face talking-head capability gap** (no-PuLID over-cook) — the roadmap lever for the user's "not max tier" verdict ([[project_talking_head_quality_tiers]]). Closing it (a clean no-PuLID face path OR a max-tier "new-character" creation flow yielding a max-tier-quality canonical) unlocks max-tier NEW-face talking heads.
- **V-MINOR-2** (operator Lane V on 3ec83b4) — `tests/unit/test_hires_fix_pass2.py:10-12` module docstring still says "denoise=0.40 HYPOTHESIS … pod down" (superseded by 3ec83b4). Fold a 1-line fix into the next touch of that file (ADR-013).
- **FE slider V1 + V-MINOR-3** — `AdvancedSection.tsx:311` `min={0.2}→0.40` + `web/src/types/project.ts:198` type comment. Backend-only defense accepted; optional FE follow-up (needs `tsc`).
- **Photoreal-clip refinements** (OFFERED, not done): exact 9:16 fill-crop to 720×1280; 1080p Hedra re-render (≤30s supports it).
- **Open roadmap** (reassessment `wf_198f53fe-7aa`, still open): multi-char identity gate (`controller.py:1069` chars[0]-only); video-gen timeouts (`phase_c_ffmpeg.py` untimed `fal_client.subscribe`); `STRATEGIC_REVIEW-2026-06-09` successor; #5 `_accept_or_reject`/probe fail-open ADR.
- **Merge `origin/feat` (b49600e) → `origin/main` (1870e59)** — future USER-gated decision (34 commits ahead, all green).

## Deliverable media (logs/, EPHEMERAL)
- `talkinghead_photoreal_9x16.mp4` — the delivered photoreal 30s vertical (qipao woman).
- `talkinghead2_9x16.mp4` / `talkinghead2_photoreal_9x16.mp4` — the over-cooked no-PuLID male attempts (kept for the capability-gap evidence).
- `max_supir_ab_cfg{28,20}_*.jpg` (SUPIR A/B), `max_neck_check_anatomy.jpg` (neck validation).
- Ephemeral pod drivers (untracked): `scripts/_max_supir_cfg_ab.py`, `_max_neck_check.py`, `_talking_video.py`, `_talking_head2.py`, `_talking_head3.py`.

## Operational notes
🔑 `env -u GIT_INDEX_FILE` for pytest+smoke. **Pathspec commits with `env -u GIT_INDEX_FILE` for BOTH `git add` AND `git commit`** (same default index — a mismatched index = "pathspec did not match" failure). `--fix`/`read-tree` after Workflow/peer-commit + R-OP-1 spot-check. D-a-safe push = `git push origin <verified-sha>:feat/max-tier-provisioning` (capture before+after). Pod drives via HTTPS gateway (`settings.comfyui_server_url`, no SSH). **Show media: `open "<absolute>"` with Bash `dangerouslyDisableSandbox:true`.** Talking head: `dialogue_voice_mode=overlay` + `lip_sync_mode=generation` + cache `purpose=talking_head_full`; Hedra `HedraAPI().generate_talking_head(img, audio, out, aspect_ratio=...)`.

*Last verified: 2026-06-09 (this wrap).*
