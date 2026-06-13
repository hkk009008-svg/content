# HANDOFF — operator2 (Pair B), 2026-06-13 — READ FIRST AS OPERATOR2

**Seat:** `operator2` = Pair-B **operator** (independent verification + doc-sync + mailbox reports).
**Lane (principal-confirmed FINAL):** **VIDEO + ASSEMBLY + DELIVERY** — `phase_c_ffmpeg.py`/`phase_c_assembly.py` video paths, video-API selection (Veo/Kling/LTX/Sora/Runway/Hedra/Seedance), `lip_sync.py`, dialogue/TTS, `cinema/shots` sequence continuity, `web_server`/`cinema_pipeline` **video** orchestration. Shared seams (`phase_c_assembly`, `workflow_selector`) → owner = whoever's change-lane the edit is in + a `-to-all-` Rule #23 heads-up. Pair A (director+operator) owns image/identity — **NOT your lane; do not verify their image commits.**
Protocol: `docs/protocol/claude/four-seat-extension.md` (ACCEPTED). Pair partner = **director2** (leads recon/briefs; you verify).

---

## ⭐ IMMEDIATE NEXT — 3 trivial Tier-1 bug-fixes: USER-AUTHORIZED "proceed now", STAGED but NOT yet implemented

The user said **"fix the trivial Tier-1 bugs on director2's go"** then **"proceed now"** (principal override of the director2-GO gate) — then **"handoff"** before I started implementing. So these are **fully authorized, fully specified, ZERO code written yet** (clean break — nothing half-done). Implement TDD (RED→GREEN, watch each fail first), each its own **explicit-pathspec** commit. All 3 target files were CLEAN vs HEAD (`git diff --quiet HEAD -- <f>`) at wrap; **re-verify + `git log -1` before each commit** (4 live seats move HEAD constantly).

**A. Storyboard cost-tracking is 100% DEAD** — `cinema/phases/motion_render.py:209`
`scene_id=scene_id` → `shot_id=scene_id`. `cost_tracker.py:296 record_api_call(self, api_name, cost_usd=None, operation="", shot_id="", video_id="")` has **no** `scene_id`/`**kwargs` → guaranteed `TypeError` every call, swallowed by the wrapping `except Exception: logger.warning("storyboard batch: cost record skipped")`. `shot_id` is a non-keyed cost-log label (persisted via `log_api`), so `shot_id=scene_id` is the minimal safe fix; `operation="storyboard_generation"` already marks it a scene batch. (Adding a `scene_id` param to the shared signature + `log_api` = NOT trivial; rejected.)
RED: assert the storyboard batch path records the KLING_NATIVE cost (spent_usd increments / `log_api` invoked). Fails today (TypeError swallowed), passes after. Mirror `tests/unit/test_cost_tracker.py` + `test_f2b_storyboard_mode.py`.

**B. `driving_video_path` silently dropped on cascade** — `phase_c_ffmpeg.py` (re-grep `return generate_ai_video(`; ~:173-181 cascade-to-next + ~:204-212 quota-cooldown retry; verified still-dropped after 9d90889)
Add `driving_video_path=driving_video_path` to BOTH recursive calls. Docstring (~:88-99) says driving_video_path is honored by Veo/Sora/Runway — dropping it on any cascade hop silently loses performance-capture motion (engines fall back to image-only, no log). **Optional same-edit:** also forward `negative_prompt=negative_prompt` — NEUTRAL for None/empty callers (shot_type is forwarded so the shot-type negative rebuilds identically) and PRESERVES a caller's custom negative through cascade. Low-risk; include or note it.
RED: force a cascade hop with driving_video_path set; assert the next-engine `generate_ai_video` receives it (mirror `test_cascade_logic.py`).

**C. LTX writes 0-byte file then reports SUCCESS** — `ltx_native.py` native method (~:256-263)
Inside `with urllib.request.urlopen(req, timeout=600) as resp:` after `video_data = resp.read()`, add `if not video_data: raise RuntimeError("LTX native returned empty 200 body")` before writing. Routes through the EXISTING `except Exception` → FAL fallback / None (→ cascade) instead of a false success. RED: mock urlopen→empty body; assert NOT a false success (None / FAL path), no 0-byte file accepted. Mirror `test_ltx_native.py` (21 tests).

**EXCLUDED — director2 design call, NOT trivial** (do not touch without director2 brief): `[SHOT]`-regex re-enable (`workflow_selector.py:439` case mismatch — changes shot-type *classification*), landscape-keyword reroute (`:446` — changes *routing*), KLING duration hardcoded `'5'` (`phase_c_ffmpeg.py:269` — confirm intent vs threading caller `duration`).

On completion: send director2 a verification-report; the broader brief (below) takes precedence for everything after.

---

## SESSION ARC (what I did)
1. **Onboarded** operator2 (R-START: ci_smoke OK; consumed `all` broadcasts; cursor → 09:16:14Z). Standup + lane ack to director2 (`b324f5d`).
2. **Lane-health baseline** — Workflow `wf_40a9025b` (12 read-only subsystem finders → adversarial refute of every bug-claim; **inspect-only**, no pytest — tree dirty w/ Pair-A image WIP). 10/10 bug-claims confirmed; **I personally re-traced the 7 highest-impact vs HEAD — all hold.** Delivered to director2 (`6db4739`). Full structured output was at `/private/tmp/claude-501/.../tasks/wj938fjuj.output` (**ephemeral tmp — the durable record is the `6db4739` findings event**).
3. **GO-request** dispatch-claim for the 3 trivial fixes (`ce70495`); user said proceed-now; Rule #23 heads-up to director2 (`fd5770b`).

## BASELINE — 8 distinct confirmed bugs (full detail in the `6db4739` findings event)
- **CONVERGENCE (locked):** `driving_video_path` cascade-drop + `negative_prompt` handling were independently found by BOTH my baseline and director2's recon (wf_b7ee29cf).
- **Tier-1:** (A) storyboard cost-tracking dead [above]; (C) LTX 0-byte false-success [above]; `[SHOT]` regex dead (case); landscape mis-route; KLING duration hardcoded `'5'`.
- **Tier-2 latent:** Kling storyboard duration overflow (`kling_native.py:362-364`); `stitch_modules` CWD `concat_list.txt` race (`phase_c_ffmpeg.py:951` + per-project daemon threads `web_server.py:1606`); lip_sync best-of returns stale path on restore failure.
- **Test-dark:** Seedance + FAL_SVD branches, `stitch_modules`, cascade param-forwarding, `assess_motion_quality` all untested; `test_cascade_retries_max_is_two` documents threshold 2 but code is `MAX_CASCADE_RETRIES=1`; kling `generate_storyboard` non-idempotent.
- **Doc-drift:** ARCHITECTURE.md §9.4 engine-dispatch table line numbers ALL stale; §9.7 "12 functions"→16; §2 "59 routes"→66, PERFORMANCE_REVIEW gate claim stale; SORA EOL undocumented.

## ⚠ CORRECTION carried for director2 (don't mis-record)
director2's recon flagged `negative_prompt=''` bypass via an `is None` guard at phase_c_ffmpeg.py. **That finding was REAL and is now FIXED** by **`9d90889 fix(video): empty-string negative_prompt must still build shot-type negatives`** (guard is now `if not negative_prompt:`, with a comment referencing `controller.py:1600`). It no longer reproduces against HEAD because it was *fixed*, **not** because director2 misread. (Caught via `git log -5` — HEAD moved under me mid-session.)

## director2's headline (their recon, for context — Pair-B capability direction)
"Lane is live end-to-end, but a large fraction of SOTA capability is **BUILT-but-DEAD/UNWIRED or SILENTLY-BROKEN**" (PROGRAM-MANUAL §5 full-capability). Examples they verified: SyncNet lip-sync scorer is an import-guarded no-op; `record_generated`/`log_appearance` have zero prod callers (temporal img2img + wardrobe continuity dead); subtitles absent; auto-RIFE/auto-SeedVR2 only via manual `apply_correction`. **director2 was surfacing a ranked opportunity map to the USER for a direction steer; the scoped brief lands after the user picks.** When it arrives, verify it against the baseline (esp. cover test-dark paths before extending).

## COORDINATION STATE @ wrap
- HEAD `3fa3b4a`. My cursor `seen/operator2.txt` = **09:16:14Z**, unread 0. My commits: `b324f5d`, `6db4739`, `ce70495`, `fd5770b`.
- All 4 seats LIVE at wrap (heartbeats ~09:30Z): director (Pair-A, resumed), director2 (my partner), operator (Pair-A), operator2 (me).
- Pair-A activity (NOT your lane, awareness only): PuLID SDXL→FLUX Chunk-1 done; `Pulid.json`→`pulid.json` case-rename landed (`a924055`/`3a74960`/`3fa3b4a`); pod acceptance gate still the only PuLID remainder (pod DOWN). Pushes USER-gated (~70+ ahead).

## SHARP EDGES (this session)
- **D-a stale per-seat index phantom is REAL and scary** — after peer commits, `git status` showed `RM pulid.json -> Pulid.json` (would REVERT Pair-A's rename!), `D` on existing events, `MM` on skill docs. These are **phantoms from a stale `index-operator2`**, NOT real changes. Trust `git diff --quiet HEAD -- <file>` (working-tree vs HEAD blob), not `git status`. Fix: `git read-tree HEAD` (safe when you have no real staged work — reseeds only YOUR index). NEVER commit with phantom index state; **always explicit pathspec.**
- **Live tree moves every ~1-2 min** — `git log -1` before EVERY commit; consume the mailbox before acting.
- **No pytest on the dirty shared tree** — inspect tests, don't execute, until the tree is clean (or scope to your touched test files and verify they don't transitively import the dirty modules). For the 3 fixes' TDD, the touched test files are your regression evidence.
- ci_smoke OK at wrap (55 advisory PROGRAM-MANUAL doc-anchor drifts, non-gating).
