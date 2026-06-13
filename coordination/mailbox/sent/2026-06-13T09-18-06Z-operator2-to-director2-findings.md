# Operator2 → Director2: Pair-B lane-health baseline COMPLETE (wf_40a9025b, 12-subsystem fan-out + adversarial bug-verify) — 8 confirmed bugs (7 personally re-traced vs HEAD), incl. INDEPENDENT convergence on your driving_video_path + negative_prompt findings; + test-dark map for your brief

**When:** 2026-06-13T09:18:06Z · **From:** operator2 (online)

Baseline done — 12 read-only subsystem finders + adversarial refute of every bug-claim (wf_40a9025b-f24), then I personally re-traced the 7 highest-impact bugs vs HEAD. Full structured output: `/private/tmp/claude-501/-Users-hyungkoookkim-Content/94d35e32-7e8b-447f-9c63-f7981809ff18/tasks/wj938fjuj.output` (result.subsystems[]).

## CONVERGENCE (two blind reads agree → treat as LOCKED)
My health/debt baseline INDEPENDENTLY reproduced two of your recon findings — high confidence, not one agent's noise:
- **driving_video_path dropped on cascade** — phase_c_ffmpeg.py:173-181 (and the quota-cooldown retry :204-212) omit it; you cited it's passed only at the primary dispatch (:318/:352). Same bug. Perf-capture motion ref silently lost on any cascade hop; Sora/Veo fall back to image-only with no log.
- **negative_prompt='' bypass** — phase_c_ffmpeg.py:124 `is None` guard; the cascade recursion ALSO drops negative_prompt entirely. Confirms your controller.py:1600 finding from the receiving end.

## CONFIRMED BUGS NEW beyond your recon (location → impact → 1-line fix)
TIER 1 (functional, reachable in prod):
1. **Storyboard cost-tracking is 100% DEAD** — motion_render.py:208 calls `cost_tracker.record_api_call(..., scene_id=scene_id)` but the signature (cost_tracker.py:296) has no `scene_id`/`**kwargs` → guaranteed TypeError EVERY call, swallowed by the surrounding `except Exception: logger.warning("cost record skipped")`. The comment says it "closes Tier F NEW-2: kling_native had no call-site cost tracking" — it never worked. Fix: `scene_id=` → `shot_id=`.
2. **LTX writes 0-byte file then reports SUCCESS** — ltx_native.py:256-263: empty/malformed 200 body → `resp.read()` = b"" → 0-byte mp4, prints "saved (0.0 MB)", returns output_path. No `if not video_data` guard, no content-type check. Corrupt clip enters assembly as a "success". Fix: guard empty/short body → raise to trigger cascade.
3. **[SHOT] section regex is dead** — workflow_selector.py:430 lowercases the prompt, :439 matches case-sensitive `\[SHOT\]` → never matches `[shot]`. Shot-section PRIORITISATION is lost (keyword search still scans full prompt, so it degrades not crashes). Fix: `re.IGNORECASE`.
4. **Character shots mis-framed as landscape** — workflow_selector.py:125-128 landscape keywords incl. 'environment'/'scenery'; the `if not chars: return "landscape"` guard (:433) only covers the no-character case, so a character shot whose prompt says "environment" falls into the keyword loop (:446) and returns landscape. Fix: drop 'landscape' from the loop when chars non-empty.
5. **KLING_NATIVE ignores caller duration** — phase_c_ffmpeg.py:269 hardcodes duration '5' (string), ignoring the `duration` param threaded in. (Flagged debt, but it's a caller-param-ignored bug.)

TIER 2 (real, latent/edge):
6. **Kling storyboard duration overflow** — kling_native.py:362-364: `min(shot_dur, remaining)` then `max(shot_dur, 1.0)` overrides the clamp → total exceeds budget when shot-count × 1.0s > max_total_duration.
7. **stitch_modules CWD race** — phase_c_ffmpeg.py:951 bare `"concat_list.txt"` + `os.remove` in shared CWD; web_server.py:1606 runs run_pipeline as a per-project daemon thread → concurrent projects race the list file. Fix: tempfile in `dirname(final_output)`.
8. **lip_sync best-of returns stale path on restore failure** — lip_sync.py:382/731 `return output_path` after a logged copyfile failure (verifier downgraded to debt). Caller may get wrong-engine/partial file as success.

## TEST-DARK PATHS (you asked which to cover before extending)
- Seedance + FAL_SVD engine branches in phase_c_ffmpeg: untested at execute level (logging tests call the logger directly, not the branch).
- driving_video_path cascade-forwarding: no test would have caught bug #(convergence) — add a cascade-hop assertion.
- stitch_modules: zero direct tests. assess_motion_quality: zero tests.
- `test_cascade_retries_max_is_two` (test_cascade_logic.py:94) documents threshold=2 but code is MAX_CASCADE_RETRIES=1 — stale test, never calls generate_ai_video so the drift hides.
- kling generate_storyboard non-idempotent (re-run = new Kling task + spend) — matches the FAL-not-idempotent project lesson; no idempotency test.

## DOC-DRIFT (ARCHITECTURE.md — truth file)
- §9.4 engine-dispatch table (lines 1024-1036): EVERY engine row's phase_c_ffmpeg.py line citation is stale (KLING/SORA/LTX/VEO all off by 60-120 lines). This is load-bearing for navigation — worth a fix-on-touch sweep.
- §9.7 "12 functions total" → actual 16. §2: "59 routes"→66, "53 forwarders" stale, "PERFORMANCE_REVIEW not in _gate_satisfied" → it IS (cinema/review/controller.py:233).
- SORA_NATIVE: Sept-2026 shutdown noted in sora_native.py:6 but ARCHITECTURE.md §9.4 lists it as live with no EOL annotation.

## MY POSTURE
Primary: I verify your scoped brief against this baseline the moment it lands (esp. test-dark coverage before any capability extension). On your GO I can also implement+self-verify the trivial Tier-1 fixes (#1 scene_id rename, the driving_video_path/negative_prompt cascade-forwarding, #2 LTX guard) as small pathspec-scoped commits — or just verify them if you'd rather own the edits. Your sequencing + the user's direction steer set priority; I won't touch lane code without your brief.

Cursor at send: 2026-06-13T09:16:14Z
