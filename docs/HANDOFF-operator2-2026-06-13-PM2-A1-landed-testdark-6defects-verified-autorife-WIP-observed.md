# HANDOFF — operator2 (Pair B), 2026-06-13 PM2 — READ FIRST AS OPERATOR2

**Seat:** `operator2` = Pair-B **operator** (independent verification + doc-sync + mailbox reports).
**Lane (principal-confirmed):** **VIDEO + ASSEMBLY + DELIVERY** — `phase_c_ffmpeg.py` / `phase_c_assembly.py` video paths, video-API selection (Veo/Kling/LTX/Sora/Runway/Hedra/Seedance), `lip_sync.py`, dialogue/TTS, `cinema/shots` continuity, `web_server`/`cinema_pipeline` video orchestration. Shared seams (`phase_c_assembly`, `workflow_selector`, `cinema/shots/controller.py`, `test_generate_ai_video_params.py`) → owner = whoever's change-lane the edit is in + a `-to-all-` Rule #23 heads-up. Pair A (director+operator) owns image/identity — **NOT your lane.**
Protocol: `docs/protocol/claude/four-seat-extension.md`. Pair partner = **director2** (leads recon/briefs; you verify/implement-on-GO).

---

## ⭐ SESSION OUTCOME

User: "continue as operator2" (ultracode) → landed the pre-approved A1 refine → ran a verify+discovery workflow → adversarially refuted the discoveries → surfaced a decision-ready package → user "handoff". **One commit landed (A1); a verified defect backlog is fully spec'd below, ready to implement on GO (no TDD cycle started after the stop signal, per protocol).**

### 1. A1 LANDED + INDEPENDENTLY VERIFIED — `4121a83` (ancestor of HEAD, intact)
`cinema/phases/motion_render.py` storyboard batch cost record: `shot_id=scene_id` → `shot_id=""`.
- **Why (correctness, not cleanup):** `get_video_cost()` (`cost_tracker.py:410-419`) set-unions every truthy `shot_id` and reports `len()` as `shot_count`. A scene_id riding the shot_id column made each storyboard batch a phantom "shot". A batch has no single shot; `operation="storyboard_generation"` + `video_id` already attribute it. `shot_id=""` keeps `shot_count` honest with zero tracking loss.
- **TDD:** RED `test_batch_cost_does_not_inflate_shot_count` (real `CostTracker`; got 1, expected 0) → GREEN. The existing `spent_usd==0.50` real-tracker test stays green (cost still recorded). 34/34 in-file, 85 cost_tracker tests, ci_smoke OK.
- **Verification (implementer≠verifier; director2 offline → adversarial workflow `wf_62c6c020-ed1`, 2 Sonnet skeptics):** both `CONFIRMED_CORRECT` high-conf; Rule#13 audit of ALL 12 `record_api_call` sites = clean (no other scene-id-as-shot-id); `production_reader_of_shot_count="none"` (both `get_video_cost` readers — `cost_tracker.py:439 get_cost_per_second`, `cinema_pipeline.py:916` — read dollar totals only); pytest 106/0. **A1 is locked.**

### 2. TEST-DARK SWEEP → 6 candidate defects, ADVERSARIALLY VERIFIED (`wf_62c6c020-ed1` map + `wf_d6c6051b-5c0` refute, 5+6 Sonnet)
The refute pass earned its cost: it downgraded D5 (overstated) and calibrated severities. **Disposition table (each verdict is post-refutation):**

| # | Defect | Loc | Verdict | Sev | Disposition |
|---|--------|-----|---------|-----|-------------|
| **D1** | Seedance: null `task_id` → polls `/v1/video/status/None`, NO pre-poll guard (KLING validates) → up to 120 iters before cascade | `phase_c_ffmpeg.py` SEEDANCE branch (~921-926) | CONFIRMED hi | med | **fix_now_trivial** |
| **D4** | `stitch_modules`: `concat_list.txt` at bare CWD path → cross-project collision; `os.remove` outside try → leak on ffmpeg error | `phase_c_ffmpeg.py:975,993` | CONFIRMED hi | med | **fix_now_trivial** |
| **D6** | lipsync best-of-failed: `_shutil.copyfile` OSError → logs warning but `return output_path` (truthy stale/empty path) on the SOLE talking-head fallback | `lip_sync.py:709-731` | CONFIRMED hi | low | **fix_now_trivial** |
| **D3** | FAL_SVD: char ref uploaded (+ "Injecting IP-Adapter" log) but `ref_img_url` never forwarded to `subscribe()`; `fast-svd` can't accept it anyway | `phase_c_ffmpeg.py:765,776,799-807` | CONFIRMED hi | med | **fix_with_brief** |
| **D2** | Seedance: `multi_angle_refs` never read → its multi-char cascade-slot justification is inert; comment claims "20s" but hardcodes `duration=5` | `phase_c_ffmpeg.py` SEEDANCE branch | CONFIRMED hi | med | **fix_with_brief** |
| **D5** | `assess_motion_quality` bare `import cv2` "crashes diagnosis" | `phase_c_ffmpeg.py:1111`, `controller.py:2090` | **PARTIAL → no_action** | low | **no_action** |

**D5 was REFUTED-as-overstated:** cv2 is a HARD dep (`requirements.txt:31`); `phase_c_vision.py` imports cv2 at module level and runs FIRST (`controller.py:2063`), so the motion scorer isn't uniquely vulnerable; the "other scorers degrade gracefully" comparison is FALSE (coherence + identity scorers share the same gap). Do NOT patch just the motion scorer — that's a fix_with_brief design call across all 3 scorers IF graceful degradation is ever a goal. **Don't land.** (This is the `[SHOT]`-inert lesson repeating: verify findings before acting.)

### 3. ⭐ NEXT — the 3 fix_now_trivial defects, FULLY SPEC'd (land on GO, TDD, implementer≠verifier)
USER did NOT GO before "handoff" — I offered, asked, did not land (no TDD cycle after the stop signal). All three are pure Pair-B lane, behavior-preserving on the happy path, verified-real high-conf. **Suggested order (lowest-risk first):**

- **D4 `stitch_modules` (strongest — documented sibling fix exists):** in `phase_c_ffmpeg.py:975` replace bare `list_file = "concat_list.txt"` with a scoped name — mirror `audio/dialogue.py:651` (`f"{output_filename}.concat.txt"`, derived from the absolute `final_output`). Wrap the ffmpeg call + `os.remove` (line ~984-993) in try/finally so the list file is cleaned up even on `CalledProcessError`. ~5 lines, no design decisions. RED test: two stitch calls with different clip sets in the same CWD must not collide (assert each list file has only its own clips); a forced ffmpeg failure must not leak the list file. New file `tests/unit/test_stitch_modules.py` (zero coverage today).
- **D1 Seedance null-task_id guard:** between the `task_id = resp.json().get("task_id") or resp.json().get("id")` line (~921) and the `poll_url` build (~925), add `if not task_id: raise ValueError(f"Seedance POST returned no task_id; body={resp.text[:200]}")`. The outer `except Exception` (~962) already logs + `try_next_api()` — converts a silent multi-minute hang into immediate cascade. Behavior-preserving in the happy path. RED test: POST returns 200 with no task_id/id key → assert immediate cascade, NOT 120 polls (mock `time.sleep`). New file `tests/unit/test_seedance_dispatch.py` (zero coverage).
- **D6 lipsync copyfile-fail returns None:** in `lip_sync.py` best-of-failed block (~709-731) set `_copied=False` before the `copyfile` try, `_copied=True` after success, and `return output_path if _copied else None` at ~731. Changes behavior ONLY on OSError (disk-full etc.). RED test: mock `copyfile` to raise OSError → assert returns None (caller falls through), not a truthy stale path. NOTE the deeper observation (not the fix scope): even on SUCCESS, `output_path` holds the LAST engine's output because the stash pattern (~583-593) copies but doesn't delete the original — flag for director2 if best-of-failed selection looks wrong. New/extend `tests/unit/test_lip_sync_best_of_failed.py`.

### 4. director2's tier (DO NOT touch without a brief + the principal's §5 steer)
- **D2, D3 = fix_with_brief.** D3's real question: `fal-ai/fast-svd` (SVD) animates ONE image — it can't blend a second identity image, so the fix is (a) remove the dead upload + the misleading "Injecting IP-Adapter" log, (b) swap to an identity-capable endpoint, or (c) stub-with-TODO. Design call. D2: loop `multi_angle_refs` into the Seedance payload (type/ordering/merge-vs-replace-character_id are design calls; fold the "20s vs duration=5" claim in).
- **W1 §5 principal decisions (ALL FOUR verified against HEAD this session — director2's brief holds; brief = `docs/BRIEF-director2-2026-06-13-PM-W1-dispositions.md` §5):**
  1. **SyncNet** (`lip_sync.py:392-445`) — confirmed near-no-op: `syncnet_python` import fails → ffprobe duration-match (gross only) → neutral `1.0`. Coordinator's align audit independently corroborated "falsely-green no-op feeding the 0.8 gate". director2 rec: ship the zero-dep mouth↔audio-energy correlation scorer (Provider 1.5).
  2. **auto-RIFE** — confirmed diagnose+manual-only (`_finalize_motion_take` never auto-runs `assess_motion_quality`/`generate_rife_interpolation`; only `diagnose_clip` recommends + `apply_correction` manually applies). **⚠ SEE §5 below — a peer is ACTIVELY IMPLEMENTING this in the working tree.**
  3. **Suno** (`cinema_pipeline.py:632`) — confirmed bypassed (`generate_fal_bgm` called directly). **`generate_bgm` (`audio/music.py:261`) does NOT accept `cost_tracker`** → the reconnect REQUIRES adding+threading it through `generate_suno_v5`+`generate_fal_bgm` or it loses today's cost tracking. The "bonus bug" is a prerequisite, not an extra.
  4. **Landscape misroute** — Pair-A's operator confirmed + severity-corrected: a named-character "landscape" shot early-returns at `phase_c_assembly.py:223-227` to `_fal_flux_fallback(character_image=None)`, **dropping identity entirely** (both prod + MAX tiers). Root = `classify_shot_type` (`workflow_selector.py`), upstream of BOTH image (Pair-A) and video (Pair-B: silenced audio + lost LTX-4K `phase_c_ffmpeg:367/403`). Joint Rule#23 fix; ARCHITECTURE.md §8.5 known-defect note landed by Pair-A (`547cf12`), cross-refs ADR-025. director2 rec: fallback → "wide" (not "medium").

## 5. ⚠ LIVE PEER WIP IN THE WORKING TREE (uncommitted at HEAD `e61ab10`) — DO NOT SWEEP
A peer is **actively implementing auto-RIFE (§5 #2)** in the SHARED working tree, uncommitted:
- `cinema/shots/controller.py` (+82): a new `_maybe_auto_rife(video_path, take, shot_id, settings)` method — reads `auto_rife_smoothness_threshold` (default 0.4, exactly director2's rec), runs `assess_motion_quality`, applies `generate_rife_interpolation` below threshold, records `FAL_RIFE` cost. Its own comment dispositions the cv2-guard question the same way my D5=no_action did ("best-effort enhancement; non-determinism only flips one RIFE call").
- `cost_tracker.py` (+2): `"FAL_RIFE": 0.04` cost-table entry.

**Implication:** §5 decision #2 (auto-RIFE) appears DECIDED + IN IMPLEMENTATION by another seat. When you resume, `git log` first — it may already be committed. Do NOT edit `controller.py`/`cost_tracker.py` until that lands (verify it post-commit as your lane). My A1 commit used explicit pathspec and never touched them.

## 6. COORDINATION STATE @ wrap
- HEAD `e61ab10` (Pair-A + coordinator very active this session — HEAD moved ~10×). My only commit: `4121a83` (A1) + this wrap.
- My cursor `seen/operator2.txt` advanced via `consume-events operator2` (was 10:23:49Z). Wrap broadcast = `operator2 → all` (status).
- **Pair-A (director-1 + operator-1) ONLINE** — wrapping PuLID Step-5 doc close-out (ADR-025 + `547cf12` §8.5); Step-5 COMPLETE+VERIFIED per `735adb9`. Coordinator (5th, read-only) wrapped. director2 (my pair lead) was offline at my start; the auto-RIFE WIP suggests a Pair-B seat is active — verify who via presence/git on resume.
- ✅ **Pod 07ed667 STOPPED by user** (billing resolved). Pair-A's pod-gated N=4/experiment burns are re-blocked (their lane).
- ci_smoke OK (57 advisory PROGRAM-MANUAL doc-anchor drifts, non-gating). Push USER-gated, $0 spent.

## 7. SHARP EDGES (this session)
- **git status shows BOTH stale-index phantoms AND real uncommitted peer WIP — distinguish them.** `git diff --no-index <(git show HEAD:f) f` is the index-free truth: IDENTICAL = phantom (ignore), real diff = peer WIP (do NOT touch/sweep). This session `cinema/shots/controller.py`+`cost_tracker.py` looked like phantoms in `git status` but were real peer auto-RIFE WIP. ALWAYS explicit pathspec on commit; never `commit -a`. (Extends `[[operational_sharp_edges_git_tooling]]` / `[[project_da_skip_worktree_workflow_pollution]]`.)
- **Verify findings before acting (the refute pass):** 6 scout findings → 1 (D5) was overstated and dropped on adversarial refutation. Single-scout assertions are NOT facts. The map→refute pipeline is the right shape for surfacing defects to the principal. (Same lesson as the `[SHOT]`-inert one-liner.)
- **Mailbox tooling = `coordination/bin/send-event <from> <to> <kind> <subject>` (body on stdin) + `coordination/bin/consume-events operator2`.** Both stage via explicit pathspec, never commit. `coordinator` is a valid `<from>` (send-only), never a `<to>`. Kinds validated against `scripts/check_coordination.py` (wired into ci_smoke).
- `env -u GIT_INDEX_FILE` for pytest only (GIT_INDEX_FILE breaks temp-repo tests); main-seat commits go through the per-seat index (NO `env -u` on commits).
- Two background workflows this session: `wf_62c6c020-ed1` (verify A1 + map test-dark), `wf_d6c6051b-5c0` (refute 6 defects). All agents on Sonnet per standing directive.
