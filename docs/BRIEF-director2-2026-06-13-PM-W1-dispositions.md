# director2 W1 brief — dispositions + substantive scoping — 2026-06-13 PM

**Seat:** director2 (Pair-B: video/assembly/delivery). **Status:** in-session (user
"continue as director2", ultracode). **Push:** USER-gated.
This is the disposition record for the W1 capability-recovery workstream after the
cheap-fix tier. Companion evidence lives in committed mailbox events (cited inline)
and two workflow outputs (`wf_88755100` ⭐#2 scoping, `wf_9edc4e99` ⭐#3 design+refute).

---

## 1. What LANDED + VERIFIED this session (cheap-fix tier — DONE)

operator2 implemented; director2 independently verified (implementer≠verifier). All
real-function-driven (anti-re-sim), each Rule#13-audited. Verification report:
`coordination/mailbox/sent/2026-06-13T10-08-15Z-director2-to-operator2-verification-report.md`.

| Fix | Commit | What | Verdict |
|---|---|---|---|
| A | `366af71` | `motion_render.py:209` `scene_id=`→`shot_id=` — dead storyboard cost (swallowed TypeError) | ✅ VERIFIED |
| B | `c211213` | `phase_c_ffmpeg.py` forward `driving_video_path` + `negative_prompt` across BOTH cascade recursion sites (:176 hop, :216 quota retry) | ✅ VERIFIED |
| C | `59ad7bc` | `ltx_native.py` guard empty-200 body (was 0-byte file + false success) | ✅ VERIFIED |

Prior tier (earlier this session/handoff): W1.1 `9d90889` (empty-string negative_prompt
builder guard). B folded the negative_prompt-cascade-forward in per director2 design
ruling (`...09-50-01Z-director2-to-operator2-coordination.md`) — complementary to W1.1,
not conflicting (builder = default; forward = preserve explicit override).

---

## 2. NEW CONFIRMED bug — cascade non-termination (found via B's Rule#13 audit)

**PRE-EXISTING (not introduced by B).** `phase_c_ffmpeg.py:176` (the next-engine hop)
forwards `attempted_apis` but **omits `_cascade_retries`**, resetting it to 0 on every
hop. Site 2 (quota retry, :216) increments it. So a **multi-engine** all-fail cascade
never sees the incremented counter at its terminal quota-check → it repeats the 30s
quota-retry pass instead of `MAX_CASCADE_RETRIES=1`. Single-engine terminates (no hop
to reset) — which is why the suite never caught it.

- **EXECUTED probe** (not just traced): 2-engine all-fail `["KLING_NATIVE","SORA_NATIVE"]`,
  `time.sleep` mocked+capped → fired **7×** before the cap stopped it (would've continued);
  expected exactly 1. `result=None, capped=True`. (BaseException sentinel so the cascade's
  `except Exception` couldn't swallow the cap.)
- **Severity:** production hang (multi-minute→indefinite 30s-loop) on total video-API outage.
- **Fix:** add `_cascade_retries=_cascade_retries` to the site-1 recursive call (carry,
  don't increment — same pass). One line. The probe converts directly to a regression test
  (cap `time.sleep`, assert call_count==1) in `test_generate_ai_video_params.py`.
- **Disposition:** near-trivial behavior-fix (restores documented intent). Recommend
  fix_now via TDD once principal/operator2 picks it up — it's the highest-severity item here.

---

## 3. ⭐#3 design-call dispositions — ALL `fix_with_brief` (none `fix_now`)

The adversarial-refute pass (`wf_9edc4e99`) deepened/flipped every "trivial" fix.
Rule#23 heads-up to Pair-A sent: `...10-08-52Z-director2-to-all-coordination.md`.

### 3a. `[SHOT]` regex (`workflow_selector.py:439`) — the one-liner is INERT
The case-sensitive `\[SHOT\]` against a lowercased prompt never matches, so `shot_section`
is always "". **But adding `re.IGNORECASE` changes nothing** (director2-confirmed by reading
`classify_shot_type`): `search_text` (line 444) always concatenates the full lowercased
prompt, and the keyword scan (446–449) is dict-order/position-independent — populating
`shot_section` adds no keywords and grants no priority. **DO NOT land the one-token fix
(false confidence).** Real fix = scoped-section-only scan when a structured prompt is
detected → behavior-changing (re-routes dialogue-heavy medium/action shots currently
mis-classified `portrait`), shared-seam (affects Pair-A image params). **fix_with_brief.**

### 3b. Character shots mis-routed `landscape` (`workflow_selector.py:434/446`) — HIGH, Rule#23
Char-bearing shots with a landscape keyword (`aerial`/`drone`/`skyline`/`panoramic`/
`environment`/`scenery`) return `landscape` ⇒ pulid_weight **0.0**, identity gate off, LTX.
Fixing flips them to nonzero PuLID + KLING/wide + identity stack. Adversarial pass found
extra blast radius: silenced `generate_audio` + lost LTX-4K (`phase_c_ffmpeg:367/403`);
**"wide" is a better fallback than "medium"** (pulid 0.65, no FaceDetailer — fits aerial
geometry); a 2nd classifier `_heuristic_shot_type` (`llm/prompt_optimizer.py:161`) would
diverge; and Pair-A's just-passed Chunk-1 pod gate assumed landscape stays 0.0 — **must be
re-scoped to include a char-aerial shot before PuLID shipping-default.** **fix_with_brief,
joint director+director2 Rule#23 sign-off.**

### 3c. KLING `duration='5'` hardcoded (`phase_c_ffmpeg.py:278` + KLING_3_0 `:667`) — medium
Both KLING branches ignore the threaded `duration` (every clip 5s; dialogue >5s gets
truncated lipsync). Map to the Kling enum (≤5→"5", >5→"10") via a `_clamp_kling_duration`
helper. Adversarial caveats: (i) mapping to "10" ~doubles real cost while `API_COST_USD`
stays 5s-calibrated → **breaks the pre-spend budget gate** unless the cost table is updated;
(ii) "10" not confirmed valid for `kling-v1-6` in-repo; (iii) **KLING_3_0 also hardcodes
`negative_prompt`** (`:677`) — a second forward-bug. **fix_with_brief** (couple the cost-table
update + confirm the API enum). Pure Pair-B (no Rule#23).

---

## 4. ⭐#2 substantive W1 scoping (`wf_88755100`) — all confirmed still-broken vs HEAD

All pure Pair-B, low risk. Each has a design decision for the principal (§5).

| Item | Loc (re-verified) | Recommendation | Effort |
|---|---|---|---|
| SyncNet lip-sync scorer is a NO-OP gate | `lip_sync.py:392-445` (SyncNet import absent → duration-only heuristic; gate ~always passes) | Add a mouth-open↔audio-energy correlation scorer (retinaface+cv2+ffmpeg, **zero new deps**) as Provider 1.5; keep SyncNet stub + duration as fallbacks | M |
| Auto-RIFE not wired | `assess_motion_quality` `phase_c_ffmpeg.py:1090` + `generate_rife_interpolation` `lip_sync.py:805` exist; `_finalize_motion_take` `controller.py:1186` never calls them (RIFE manual-only; pipeline header falsely claims in-flow) | Add step 2.5 in `_finalize_motion_take` reading `global_settings.auto_rife_smoothness_threshold` (default 0.4); fix the stale header | S |
| Suno V5 BGM bypassed | `cinema_pipeline.py:632` calls `generate_fal_bgm` directly; `generate_bgm` Suno→FAL router (`audio/music.py:261`) never called | Switch to `generate_bgm`; **+ bonus bug:** thread `cost_tracker` through `generate_bgm` (dropped on its FAL fallback today) | S |
| forced-alignment → lipsync dead | `.alignment.json` written (`audio/dialogue.py:413`); `load_alignment_json` (`audio/alignment.py:271`) has ZERO consumers; no engine takes a timing param | Use alignment to trim leading/trailing silence before engine upload (the only meaningful use with current engines) | M |

---

## 5. DECISIONS FOR THE PRINCIPAL (surface, don't silently decide)

1. **SyncNet scorer choice (§4 item 1):** ship the zero-dep mouth↔audio correlation
   heuristic (catches gross sync/wrong-take failures, NOT phoneme b/p/m), or invest in real
   phoneme scoring (syncnet_python ~300MB + checkpoint, or wav2vec2 alignment)? And: the
   heuristic adds ~9–12s/shot (retinaface CPU) per scored engine attempt — acceptable, or use
   the lighter Haar mouth-box proxy? **Recommendation: ship the heuristic now** (turns a
   blind gate into a real one cheaply); revisit phoneme-grade later if drift complaints appear.
2. **Auto-RIFE default-on vs opt-in (§4 item 2):** default-on at smoothness<0.4 adds a
   ~$0.03–0.05 RIFE call per choppy take. **Recommendation: default-on** (brief says
   "auto-RIFE"; restores the pipeline's own advertised behavior) with the threshold as a
   per-project knob + cost recorded.
3. **Suno V5 as default BGM (§4 item 3):** AUTO mode tries Suno first (~$0.10 + ~60s) when
   `SUNO_API_KEY` is set, FAL fallback intact. **Recommendation: reconnect to the router**
   (Suno is the higher-quality path that's currently unreachable; FAL safety net preserved).
   Confirm `SUNO_API_KEY` is set in prod and the cost/latency is acceptable.
4. **Landscape fix (§3b):** confirm the fallback target (**"wide" recommended** over "medium")
   and accept that it's a Rule#23 joint fix that re-scopes Pair-A's Chunk-1 gate.
5. **Sequencing:** my recommendation for the next implementation tier, leverage-ordered:
   **cascade non-termination (§2, highest severity, near-trivial)** → Suno reconnect (S) →
   auto-RIFE (S) → SyncNet scorer (M) → landscape Rule#23 brief (M) → forced-alignment (M)
   → KLING-duration+cost-table (the [SHOT] deeper rework is lowest-leverage).

---

## 6. NEXT pickups (ordered) for the next director2

1. Get the principal's §5 steer; then brief + sequence the next implementation tier
   (implementer = operator2 on resume; director2 verifies — same split that worked here).
2. Land the **cascade non-termination** fix (§2) first — confirmed, near-trivial, highest severity.
3. Co-author the **landscape Rule#23 brief** with Pair-A's director (gate re-scope).
4. W2 delivery (subtitles on live WhisperX alignment, auto-SeedVR2 4K, LUT-at-assembly) +
   W4 Sora succession (verify the Sept-2026 EOL externally first) remain queued.

## 7. Process notes / sharp edges (held)
- **Live 4-seat session all PM** — HEAD moved ~10× under me (Pair-A determinism + pod
  Task-4 burn + operator2 A/B/C). `git log -1` before every commit; explicit pathspec always
  (per-seat index auto-stages peer files — a bare commit would sweep them).
- **Phantom index:** session-start `git status` showed `MM`/`D`+`??` ghosts; all matched HEAD
  (`git diff --quiet HEAD`). Don't "revert" them.
- **`origin/main == HEAD`** at session start — principal had pushed everything; push of new
  commits stays USER-gated.
- **Adversarial-verify earns its cost:** all 3 ⭐#3 "quick fixes" came back fix_with_brief;
  the `[SHOT]` one-liner is a literal no-op. Verify findings before acting on them.
- **Cross-lane:** Pair-A Task-4 pod gate PASSED (`f21d9a4`, PuLID 0.620→0.878); pod was
  BILLING during the burn (USER-gated, their lane).
