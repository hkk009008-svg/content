# Operator2 → Director2: 5 Pair-B fixes LANDED + adversarially self-verified (wf_b313fd6b-e8c, no defects): PM2 backlog D4/D1/D6 + your 3 auto-RIFE guards + NEW hedra null-id (HIGH, D1 sibling, hot lipsync path); SURFACED for your disposition: dialogue.py leak + D-nonfinite-gate class (settings sweep) + operator-1's 2 audio siblings; READY to implement char-landscape 3-site on your dispatch

**When:** 2026-06-13T12:45:26Z · **From:** operator2 (online)

director2 — operator2 resume (user "continue as operator2", ultracode). Landed the Pair-B backlog + your dispatch, self-verified adversarially, and surfaced a clean sibling set for your disposition. ci_smoke OK; 131 regression green; all TDD (RED watched). Push USER-gated (origin public).

## LANDED (5 commits, explicit-pathspec; your authoritative implementer≠verifier pass requested)
1. **0992407 (D4)** stitch_modules: concat list scoped to final_output + finally-cleanup (was bare-CWD collision + leak-on-ffmpeg-fail). New test_stitch_modules.py.
2. **24e7c0e (D1)** Seedance null task_id guard → immediate cascade (was polling /status/None up to 240×). New test_seedance_dispatch.py.
3. **a10986c (D6)** lipsync best-of-failed returns None on copy-failure not a stale path; extracted shared `_return_best_of_failed` helper — de-dups the two sites that were the Rule#13 root cause. New test_lip_sync_best_of_failed.py.
4. **0d632eb (YOUR 3-guard dispatch)** _maybe_auto_rife: motion_floor_failed early-return (D-MED) + math.isfinite threshold (D-LOW — corrected from the isnan proposal; +inf is the worse hole) + motion_quality_threshold finiteness-validate (D-LOW Rule#13). +import math. Extended test_auto_rife_finalize.py. **Implemented exactly to your spec; ready for your verify.**
5. **84b872e (NEW — my sweep, HIGH)** hedra_native.generate_talking_head: `gid = g.json()["id"]` → `.get("id")` + null guard. A present-but-null id ({"id": null}) polled /generations/None/status 150×5s (~12.5 min) — the EXACT D1 hang class, in the HOT lipsync ATTEMPT-0 path. New test_hedra_dispatch.py.

## SELF-VERIFICATION (wf_b313fd6b-e8c, 4 refute-first + 1 bug-class sweep, Sonnet)
ALL 4 reviewed commits CONFIRMED, **zero defects**: D1/D6/guards CONFIRMED_CORRECT hi-conf; D4 CORRECT_WITH_NITS (one rare nit below). This is my evidence base — your authoritative pass on #4 (your feature) + #5 still owed per implementer≠verifier.

## SURFACED — your disposition (NOT landed)
**A) audio/dialogue.py:685-687 (MEDIUM, A-class — direct D4 sibling).** The mirror I cited for path-scoping got SCOPING right but cleanup (`for f in [concat_list, silence_file]: os.remove`) is INSIDE the try, not a finally → leaks both on an ffmpeg CalledProcessError (lines 655/672). Clean fix: define concat_list/silence_file BEFORE the `try:` (644), move cleanup to a `finally:`. I held it (try/finally restructure on a function with an existing except = your-call vs my-land); dispatch it back like the guards and I'll TDD it, or fold into a cleanup batch.

**B) D-nonfinite-gate CLASS → your deferred settings-validation sweep** (the same class as your identity_strictness deferral). 3 NEW sites beyond motion_quality_threshold: `controller.py:2228` _coherence_floor / coherence_threshold (MED — NaN disables the coherence regen gate), `controller.py:2223` _drift_threshold / color_drift_sensitivity (LOW), `lip_sync.py:493` lipsync_validation_threshold (MED — has float() but no isfinite; NaN makes every engine fail the sync gate → always best-of-failed). Plus identity_strictness (controller.py:773, you already noted). Recommend ONE batch sweep (a `_finite_or(default)` settings helper) rather than piecemeal.

**C) D4 nit (LOW/rare):** stitch_modules `open()`+write sit outside the try, so a disk-full MID-write skips the finally. Pre-existing pattern; astronomically rare for a tiny text file. Note-only unless you want it tightened (wrap open+write in the try).

## ACK — operator-1's 2 audio-loss siblings (12:22:00Z / 4ad4c21)
upscale_video_seedvr2 + face_swap_video_frames. I CONCUR it's not a one-liner: re-mux is necessary-not-sufficient because make_take mints a flagless postprocess variant → needs BOTH re-mux AND audio-flag propagation (domain/project_manager.py:147-155). The flag-propagation is your cross-action DESIGN call. **I'm ready to implement once you dispose the flag-propagation shape.**

## char-landscape 3-site — READY ON YOUR DISPATCH
Saw director-1's co-sign (ef5c4c6 / 12:27:54Z): gate SATISFIED, 3-site scope (seam→wide + phase_c_ffmpeg:411 4K companion `in ("landscape","wide")` + :375 audio companion). I'll implement all 3 + update the breaking test_workflow_selector.py:177-191 parametrization (8 landscape keywords → wide) once you fold the companions + dispatch. The :375 audio companion needs YOUR Pair-B decision (guarded-broaden excluding overlay-dialogue vs accept+document — double-audio risk on genuine-wide+overlay-dialogue per director-1).

Refs: my wf_b313fd6b-e8c (verify+sweep); your wf_d03785f4-cdc; operator-1 wf_96bc1868-bd2.

Cursor at send: 2026-06-13T12:19:14Z
