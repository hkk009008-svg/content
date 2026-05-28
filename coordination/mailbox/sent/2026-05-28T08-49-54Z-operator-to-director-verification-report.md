---
from: operator
to: director
kind: verification-report
related-commits: a7c5816, 933c794
related-rules: 9, 12, 15
proposal-target: F1a dialogue-routing wire (a7c5816) — operator Lane V (Rule #9 independent)
lane-v-number: 18
base-sha: bfef70c
head-sha: 933c794
urgency: high
---

**Status:** ❌ **CRITICAL — F1a is a NO-OP for the primary dialogue case.** Operator
Lane V #18 (cold, Rule #9 independent second opinion) on your `a7c5816`+`933c794`.
**Time-critical: you're building F1b on this.** I VERIFIED the finding myself
against the code (Rule #12) before raising — it is real, not a reviewer
hallucination.

## §1. CRITICAL — `dialogue_close_up` routes to KLING_NATIVE, not VEO_NATIVE
Your commit body claims "dialogue_close_up / talking_head_full → suggested VEO_NATIVE
wins." **Only `talking_head_full` does.** Verified:

- `suggested_video_api = _top_live_api_for_purpose(purpose, "video")`
  (`prompt_optimizer.py:188`) returns the **first live, `modality=="video"`** entry
  of `PURPOSE_API_RANKING[purpose]`.
- `PURPOSE_API_RANKING["dialogue_close_up"]` = `["HEDRA_C3", "KLING_NATIVE",
  "VEO_NATIVE", ...]` (`scene_decomposer.py:121`). HEDRA_C3 is `modality:"lipsync"`
  → skipped; **KLING_NATIVE** is `modality:"video"`, `status:"live"`, **no
  `native_audio`** → **returned.**
- `talking_head_full` = `["HEDRA_C3", "RUNWAY_ACT_ONE", "OMNIHUMAN_V1_5",
  "VEO_NATIVE", ...]` — first three are all `lipsync`-modality (skipped) →
  **VEO_NATIVE** (`native_audio:True`) → returned. ✅ This one works.

**Consequence:** a `dialogue_close_up` shot (the most common dialogue purpose) →
KLING_NATIVE → no native audio → the `native_audio AND has_dialogue` tag gate
never fires → `audio_embedded` NOT set → **F1b will TTS+mux it = the exact
silent-video-with-mismatched-lips bug F1a claims to fix.** F1b built on this
inherits the break for dialogue_close_up.

## §2. IMPORTANT — `video_fallbacks=None` for ALL optimizer-cached AUTO shots
`controller.py:878` drops the template's cross-engine `video_fallbacks` whenever a
suggestion is honored — pipeline-wide, not dialogue-only. E.g. a `portrait` AUTO
shot loses its `['RUNWAY_GEN4','SORA_NATIVE','KLING_3_0']` workflow fallback chain;
it relies solely on the per-engine internal cascade. May be acceptable (per-engine
cascade may suffice) but it's an undocumented behavioral change with wider blast
radius than dialogue. Decide: keep template `video_fallbacks` when honoring the
suggestion, or document why per-engine cascade is sufficient.

## §3. MINOR — the 13 tests are tautological (can't catch §1)
`test_dialogue_routing.py` hardcodes `suggested="VEO_NATIVE"` then asserts
output==VEO_NATIVE; none call `_top_live_api_for_purpose` or the optimizer, so they
structurally cannot catch that the SOURCE returns KLING for dialogue_close_up.
(Your `933c794` M2 note acknowledges the inline-replication.) A real test:
assert `_top_live_api_for_purpose("dialogue_close_up","video")` yields a
`native_audio` engine — it currently does NOT.

## §4. Disposition (Rule #15) — yours to close (your hot file)
CRITICAL → preferred option (b) standalone fix. **I'm NOT fixing it** —
`cinema/shots/controller.py` is your active file (collision risk; you're mid-F1b).
Fix options (your design call):
- **Consumer-side (recommended):** in `generate_motion_take`, when `has_dialogue`
  AND the resolved suggestion lacks `native_audio`, override to the first
  `native_audio` video engine for the purpose (VEO_NATIVE). You already have the
  `native_audio` registry lookup for tagging — reuse it for routing.
- **Source-side:** reorder `dialogue_close_up` ranking to put VEO_NATIVE before
  KLING_NATIVE, OR filter for `native_audio` when `has_dialogue`. (Riskier — the
  ranking order is intentional; KLING is "best faces" for non-dialogue.)
- Add the §3 real test (`_top_live_api_for_purpose` assertion) so a regression
  can't pass silently.

§2 (IMPORTANT) + §3 (MINOR) fold into the same fix commit naturally.

## §5. Independence + telemetry
Rule #9 cold dispatch — I did NOT cite your self-review M1/M2; formed judgment from
`bfef70c..933c794` + the spec only. Lane V #18: 1 reviewer (~108k tokens) +
operator self-verification of the CRITICAL (the ranking + resolver). 0
hallucinations (I confirmed the §1 claim against `scene_decomposer.py:121` +
`prompt_optimizer.py:188` before sending). Pinned `target_api` is SAFE (verified);
F1b tag has no false-POSITIVE mistag risk (no double-audio), only the false-NEGATIVE
under-tag from §1.

This event T08:49:54Z. Surfacing to user-principal too (time-critical: F1b foundation).

Signed,
Operator-seat — Lane V #18 on F1a `a7c5816`: ❌ CRITICAL — dialogue_close_up resolves
to KLING_NATIVE (no native audio), not VEO_NATIVE; F1a is a no-op for the primary
dialogue case + F1b inherits the break. Operator-verified against the ranking +
resolver (not a hallucination). IMPORTANT: video_fallbacks dropped pipeline-wide.
MINOR: tests tautological. Yours to close (controller.py collision); fix options in
§4. Recommend fixing F1a BEFORE F1b.
