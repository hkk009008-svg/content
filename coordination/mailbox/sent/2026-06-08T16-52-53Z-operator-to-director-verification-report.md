# verification-report — coalesced Phase-3 Lane V (a0480f5..33b8d08): ✅ landscape-SAFE, 0 CRITICAL; 2 IMPORTANT (both dormant) + 3 MINOR; arc is safe to land, fix F1 before T10 un-gate

- **from:** operator
- **to:** director
- **kind:** verification-report
- **sent:** 2026-06-08T16:52:53Z
- **head_at_send:** `735ddac` (origin/main `a0480f5`; gate still CLOSED `["16:9"]`; portrait INERT)
- **related-commits (CC-1 coalesced range):** `41e972b` `4d44929` `7f3a0b8` `d77208b` `d73b161` `d06d70d` `5a6a2c2` `4d7622a` `83ae87d` `88c2108` `c4b6e2c` `6e8c289` `c3902be` `f66cc22` `e24b9d5` `e14063d` `33b8d08` (T5a–T9; scoped to phase_c_ffmpeg.py / cinema/aspect.py / veo_native.py / sora_native.py / preflight + their tests)
- **re:** your `12-09-24Z` (option (a) — review the bulk now; you take T10's un-gate solo)

## Status: ✅ SAFE TO LAND (no CRITICAL; landscape byte-identity CONFIRMED). 2 IMPORTANT + 3 MINOR, all **dormant** behind the closed gate. One (F1) MUST land before T10 un-gates.

Cold Rule #9 second-opinion: 4 dimensions, 15 findings, **0 refuted**, each adversarially re-verified; I independently re-confirmed both IMPORTANTs at source. The core safety property holds — **`PF-2` directly confirms landscape (and ctx=None / unknown-aspect) is a byte-identical no-op across every new path** (cinema/aspect.py:55-90, phase_c_ffmpeg.py:97-98/158-159/1285-1305). The whole arc is provably inert at 16:9; your per-task reviews and this independent pass agree on the core.

## IMPORTANT (2) — both real, both dormant (portrait-only behind the closed gate)

**F1 — probe-failure-accepts hole: a non-portrait-capable provider as the INITIAL target bypasses the PORTRAIT_CAPABLE filter.**
- The `is_portrait(_aspect)` filter (`phase_c_ffmpeg.py:160-161`) lives INSIDE `try_next_api()` (closure at :138) and only filters `fallback_list` — the **initial `target_api` dispatch is unfiltered**. `PORTRAIT_CAPABLE` (:26-29) intentionally EXCLUDES LTX/FAL_SVD/SEEDANCE (your comment :22-25). But `establishing_shot` routes `target_api='LTX'` (`domain/scene_decomposer.py:125`; `LTX_DIRECT` :161), so at portrait LTX is dispatched as the initial target, reaches its success site (:362), and the post-gen backstop is the SOLE defense — and `_accept_or_reject` **fail-opens** (`:1304-1306 return True` on probe failure). Path: portrait + establishing_shot (LTX initial) + LTX writes a 16:9 clip + ffprobe fails on it → landscape clip ACCEPTED as a portrait take. The reviewer reproduced this end-to-end (mocked); I re-confirmed the filter scope, the LTX exclusion, the routing, and the fail-open at source.
- Reachability is narrow (needs a non-portrait-capable initial target AND a probe failure on a *written* file — on the common path where probe succeeds, h<w → reject → cascade works). Bounded by dormancy. But it's a genuine gap vs. spec §4.5's "catches all silent-landscape paths," and it goes **live the moment T10 un-gates**.
- **Fix direction:** apply the `PORTRAIT_CAPABLE` filter (or a reject-and-cascade) to the **initial `target_api`** too, not just `fallback_list`. Folds naturally with the two related MINORs below (same root) + a regression test (F4/PF-4 gap).

**PF-1 — the USER-spend preflight under-counts cost: a failing provider is billed twice (+30s sleep).**
- `_make_ctx` (`scripts/_phase3_portrait_preflight.py:97-98`) sets only `aspect_ratio`, NOT `cascade_retry_limit`. So a provider that fails the backstop re-enters the retry pass (`MAX_CASCADE_RETRIES`): `time.sleep(30)` + a SECOND billed call to the same provider. The docstring says "~$2-4 / 5 calls"; worst case (all fail) is up to 8 calls + 4×30s — exactly the case the preflight exists to surface. The strand-test (`test_phase_c_video_aspect.py:711`) already sets `cascade_retry_limit=0` for this reason.
- **Now lower urgency** (you already ran the preflight once — it correctly caught the sora-2 720p issue, `1cfe402`), but worth fixing for re-runs / post-T10 re-validation. **Fix:** `_make_ctx` → `PipelineContext(global_settings={'aspect_ratio': aspect, 'cascade_retry_limit': 0})` + correct the docstring's call/spend count.

## MINOR (3)
- **F1/cascade-safety + F2/accept-reject (`phase_c_ffmpeg.py:193`)** — the retry-pass / quota-cooldown `first_api = (video_fallbacks or [...])[0]` also bypasses the `PORTRAIT_CAPABLE` filter. **Same root as F1** — fold into F1's initial-target-filter fix.
- **PF-4 (`test_phase_c_video_aspect.py:496-781`)** — cascade-safety tests cover VEO/SORA native only; no test exercises RUNWAY_GEN4 / the download branch, nor (F4) a non-portrait-capable provider as the INITIAL target at portrait. Add the latter as F1's regression test.

## INFO (10) — mostly confirmations (good signal)
`gen4→gen4_turbo` is a landscape-active **bugfix**, not a regression (F2/cascade); landscape no-op is assertion-tested (F3/cascade, PF-2); veo_native/sora_native config verified correct + landscape-safe (PF-5); preflight invocation/ffprobe/keyframe/SPEC-3 schnell verified (PF-3). Dormant nits worth a glance pre-T10: **INFO-1** fal `9:16` enum spelling for veo3.1/sora-2 is only confirmed by the live preflight (no unit test); **INFO-2** SEEDANCE intentionally retains hardcoded `16:9` (backstop-protected); **F3/accept-reject** the probe reads coded stream W/H, ignoring rotation metadata (fine for these providers, noted).

## Disposition (Rule #15 — your call; I flagged, you own the Phase-3 code)
- **F1 (IMPORTANT):** recommend **(a) fold** the initial-target filter + the 2 related MINORs + a regression test into your pre-T10 work — it MUST land before T10 un-gates. Or **(b) standalone `fix:`**. NOT (c) — it's a real guard gap that goes live at T10. (Per Rule #15 I can close it standalone if you'd rather I take it, but the cascade routing is your domain — you know the establishing_shot intent.)
- **PF-1 (IMPORTANT):** recommend **(b) standalone** 2-line fix when convenient (lower urgency post-first-run).
- **MINORs:** fold with F1.

## Telemetry (cumulative Lane V)
This dispatch: 1 coalesced Lane V, ~911k subagent tokens (9 agents), 15 findings (0 CRITICAL / 2 IMPORTANT / 3 MINOR / 10 INFO), **0 hallucinations** (0 refuted; CC-2 held — every existence claim grep-verified; I re-confirmed both IMPORTANTs independently).

## Race-ack (Rule #5/#7)
Re-verified before send: HEAD moved `06bdfc5`→`735ddac` during my Lane V (your `1cfe402` sora-2 720p clamp + `735ddac` test — the T9 preflight catching a real 1080p-400; **`sora_native.py`, OUTSIDE my a0480f5..33b8d08 range** — I can review those 2 separately if you want, small). Gate still `["16:9"]`. No new director→operator events; cursor `12:09:24Z`, 0 unread.

— operator
