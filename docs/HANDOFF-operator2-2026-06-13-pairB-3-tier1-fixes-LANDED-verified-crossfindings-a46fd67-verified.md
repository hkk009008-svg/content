# HANDOFF — operator2 (Pair B), 2026-06-13 — READ FIRST AS OPERATOR2

**Seat:** `operator2` = Pair-B **operator** (independent verification + doc-sync + mailbox reports).
**Lane (principal-confirmed):** **VIDEO + ASSEMBLY + DELIVERY** — `phase_c_ffmpeg.py`/`phase_c_assembly.py`, video-API selection (Veo/Kling/LTX/Sora/Runway/Hedra/Seedance), `lip_sync.py`, dialogue/TTS, `cinema/shots` continuity, `web_server`/`cinema_pipeline` **video** orchestration. Shared seams (`phase_c_assembly`, `workflow_selector`, `test_generate_ai_video_params.py`) → owner = whoever's change-lane the edit is in + a `-to-all-` Rule #23 heads-up. Pair A (director+operator) owns image/identity — **NOT your lane.**
Protocol: `docs/protocol/claude/four-seat-extension.md`. Pair partner = **director2** (leads recon/briefs; you verify).

---

## ⭐ SESSION OUTCOME — the 3 staged Tier-1 fixes are DONE, TDD-green, and cross-verified

All 3 USER-authorized ("proceed now") Tier-1 fixes implemented TDD (RED→GREEN, each its own explicit-pathspec commit), then independently VERIFIED CORRECT by director2 (implementer≠verifier held):

- **A `366af71`** — storyboard batch cost was **100% dead**: `record_api_call(…, scene_id=scene_id, …)` raised a `TypeError` (no `scene_id` param) swallowed by the wrapping `except Exception` → `scene_id=`→`shot_id=` (`cinema/phases/motion_render.py`). RED test injects a **real CostTracker** (the old MagicMock masked the bug) → `spent_usd` 0→0.50.
- **B `c211213`** — cascade silently dropped `driving_video_path` (perf-capture → image-only) **and** an explicit `negative_prompt` (override → shot-type rebuild) on BOTH recursive calls; both now forwarded (`phase_c_ffmpeg.py`). `negative_prompt`-forward **folded in per director2's design ruling 09:50:01Z** (orthogonal to W1.1 builder fix `9d90889`). 4 real-seam tests (SORA=driving, KLING=negative, both recursion sites) + an **autouse fixture** fixing a `sys.modules` order-flake (`test_dialogue_routing`/`test_phase_c_video_aspect` register bare-stub engine modules — run-time guard, not collection-time).
- **C `59ad7bc`** — LTX empty 200-body written as a **0-byte false success** → `raise RuntimeError` before write, routes via existing except-chain to FAL/None (`ltx_native.py`). 2 tests (None + FAL branches).

**Verification:** 61 tests across the 3 fix files; 170 across the B blast-radius; ci_smoke OK. Independent adversarial-verify Workflow `wf_81bbe2c8` (6 Sonnet skeptics × 2 lenses) → all cores CONFIRMED CORRECT high-confidence, **0 critical / 0 major**.

## CROSS-VERIFICATION with director2 — two passes were COMPLEMENTARY (the win of this session)
- **director2 found a bug I MISSED** (Rule#13 audit of my B edit): **cascade non-termination** — site-1 `:176` dropped `_cascade_retries` (reset to 0 each next-engine hop) → MULTI-engine all-fail looped the 30s quota-retry indefinitely (single-engine terminated, hiding it). director2 landed the fix **`a46fd67`** (`_cascade_retries=_cascade_retries` carry at site-1). **I independently VERIFIED `a46fd67`:** re-ran my probe vs fixed code → **1 quota-retry** (vs **7** before); `test_generate_ai_video_params.py` 6 green incl. director2's W1.3 test. ✓ CORRECT.
- **My adversarial pass found 2 things director2's trace DIDN'T** (both sent in `62979b8`, **awaiting director2 disposition**):

### ⭐ DISPOSITIONED by director2 (`6909624` / `10:17:46Z` coordination event)
1. **Finding A1 (Fix A `shot_id=scene_id`) — APPROVED → `shot_id=''` is the IMMEDIATE NEXT (assigned to operator2, low-priority/no-rush).** director2 agreed it's the *more correct* value, not just cleaner: a storyboard BATCH has no single shot, and `operation="storyboard_generation"` + `video_id` already attribute it → no real attribution loss, `shot_count` stays honest. **DO THIS:** in `cinema/phases/motion_render.py` change `shot_id=scene_id` → `shot_id=""` (TDD: add a shot_count-not-inflated assertion to `test_f2b_storyboard_mode.py` — the existing `spent_usd==0.50` test stays green, it doesn't assert shot_id). My-lane, clean, ~5 min. director2 verifies on landing. *(Left undone at wrap per the user's "handoff" — no new TDD cycle after the stop signal; fully spec'd here.)*
2. **Finding B-sib (KLING_3_0 `:677` hardcoded negative_prompt) — CONFIRMED, DEFERRED, DO NOT TOUCH.** Convergent with director2's ⭐#3 KLING-duration refuter (KLING_3_0 also hardcodes `duration='5'` at `:667`). Both fold into director2's **KLING fix_with_brief** (`docs/BRIEF-director2-2026-06-13-PM-W1-dispositions.md` §3c). Behavior-changing → lands with the briefed KLING fix, not standalone.
3. **Cascade non-termination `a46fd67` — VERIFIED by operator2.** director2 implemented (I'd confirmed the bug → implementer≠verifier). My independent check: re-ran the probe vs fixed code → **1 quota-retry (was 7)**; `test_generate_ai_video_params.py` 6 green incl. director2's `test_multi_engine_all_fail_terminates_after_max_retries` (BaseException anti-hang cap + asserts `len(sleep_calls)==1`). ✓ CORRECT.
4. **Doc-drift 55→57:** director2 owns doc-sync-on-touch (deferred; `--fix` footgun noted).

## ⭐ NEXT (after dispositions land)
1. **Verify director2's incoming W1 work** (your core role). director2's W1 dispositions brief = **`5043ec3`** (`docs/...`): the 3 ⭐#3 design calls ([SHOT]-regex/landscape-route/KLING-duration) are all **fix_with_brief** ([SHOT] one-liner is **inert** — do NOT land it; landscape-route is a `workflow_selector` shared seam w/ Pair-A image params, joint sign-off); ⭐#2 = 4 substantive W1 items.
2. **Substantive W1 (director2 assigns / you verify):** SyncNet real lip-sync scorer (gate is a no-op today — pkg absent), auto-RIFE on low motion smoothness, Suno V5 BGM reconnect, forced-alignment→lipsync wiring.
3. **Test-dark coverage in our lane** (baseline `6db4739`): Seedance + FAL_SVD branches, `stitch_modules`, `assess_motion_quality`, cascade param-forwarding (now partly covered by W1.2/W1.3) — characterization tests before extending.
4. **Doc-drift:** ARCHITECTURE.md §9.4 engine-dispatch line numbers stale; PROGRAM-MANUAL doc-anchors 55→57 (my B added lines). **Do NOT run `check_doc_claims.py --fix`** (footgun: drags usage cites to defs) — director2 coordinating doc-sync; fix-on-touch carefully.

## COORDINATION STATE @ wrap
- HEAD `a46fd67`. My cursor `seen/operator2.txt` = **10:08:52Z**, unread 0. My commits this session: `366af71`, `c211213`, `59ad7bc`, `62979b8` (verification-report), + this wrap.
- director2 (pair lead) ONLINE + active (just landed a46fd67; dispositioning my findings + W1 brief). **Pair-A director + operator both WRAPPED/OFFLINE** (`bf80c38`/`75f03a8`); Task-4 PuLID pod-gate GO (`f21d9a4`, OFF 0.620→ON 0.878), shipping-default recorded.
- **⚠ Pod 07ed667 RUNNING + ComfyUI UP + BILLING** (Pair-A flagged to user at their wrap; bills until the user stops it in the Novita console — re-flag at pickup).
- ci_smoke OK (57 advisory PROGRAM-MANUAL doc-anchor drifts, non-gating). Push USER-gated.

## SHARP EDGES (this session)
- **D-a per-seat index phantoms are REAL** — after peer commits, `git diff --cached` showed `M phase_c_ffmpeg.py` / `M test_generate_ai_video_params.py` (Pair-A + director2's *committed* work as phantom-staged in my stale `index-operator2`). Fix: **`git read-tree HEAD`** before each commit (safe — my real edits are working-tree-only; never had real staged work). **ALWAYS explicit pathspec** on commit — it protected me when director2 had 64 lines of in-flight W1.3 edits in the shared `test_generate_ai_video_params.py` (my commits never swept them). Trust `git diff --quiet HEAD -- <f>`, not `git status`.
- **Shared working tree, separate indexes** — director2 was editing `test_generate_ai_video_params.py` (a file I'd extended) concurrently. Don't touch a file a peer is mid-edit on; verify their commit AFTER it lands.
- **Rule#13 param-completeness (the miss):** I edited the `:176` recursive call to add 2 params but didn't audit site-1-vs-site-2 for ALL forwarded state → missed that site-1 omits `_cascade_retries`. **When you touch a recursive/symmetric call site, diff it against its sibling for completeness, not just the args you're adding.** director2's verification caught it — exactly why implementer≠verifier exists. See `[[operator2_rule13_param_completeness_on_recursive_edits]]`.
- **Mock-masking:** a test that stubs the collaborator whose contract the bug violates (MagicMock cost_tracker) can never catch the bug; inject the real collaborator. **Real-seam > re-simulation** (director2's `test_generate_ai_video_params.py` header is the canon).
- **No pytest on a dirty shared tree** — production `.py` was clean this session (peer WIP was committed or in coordination/test files), so scoped offline unit tests were safe. Re-check before running.
- `env -u GIT_INDEX_FILE` for pytest only (GIT_INDEX_FILE breaks temp-repo tests); main-seat commits go through the per-seat index (NO `env -u` on commits).
