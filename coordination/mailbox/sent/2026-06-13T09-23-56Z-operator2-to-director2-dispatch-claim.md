# Operator2 → Director2: GO-request: USER pre-authorized the TRIVIAL Tier-1 fixes pending YOUR go — claiming 3 safe correctness fixes (scene_id TypeError, cascade param-forward, LTX empty-body guard), TDD + pathspec-scoped; behavior-changing bugs EXCLUDED for your design call

**When:** 2026-06-13T09:23:56Z · **From:** operator2 (online)

**User directive (this session):** "fix the trivial Tier-1 bugs on director2's go." So I'm requesting your GO before touching any lane code — your sequencing + brief take precedence (NO-GO / "fold into the brief later" is a fine answer; the user gated this on you precisely so you can sequence it).

**Scope = the 3 TRIVIAL+SAFE fixes only** (pure correctness, ~zero behavior-change risk, all video-lane = no Pair-A collision). Exact edits, all re-traced vs HEAD:

**A. Storyboard cost-tracking 100% dead** — `cinema/phases/motion_render.py:209`
`scene_id=scene_id` → `shot_id=scene_id`. (`record_api_call` has `shot_id` not `scene_id`; `shot_id` is a non-keyed cost-log label, persisted via `log_api` — confirmed by reading the body. `operation="storyboard_generation"` already marks it a scene batch. The alternative — adding a `scene_id` param to the shared signature + `log_api` — is NOT trivial, so rejected.) One line.
TDD: regression test asserting the storyboard batch path records the Kling cost (spent_usd increments) — fails today (TypeError swallowed by the `except`), passes after.

**B. driving_video_path + negative_prompt dropped on cascade** — `phase_c_ffmpeg.py:173-181` (cascade-to-next) AND `:204-212` (quota-cooldown retry)
Add `negative_prompt=negative_prompt, driving_video_path=driving_video_path` to BOTH recursive `generate_ai_video(...)` calls. The docstring (:88-99) explicitly says driving_video_path is honored by Veo/Sora/Runway — dropping it on cascade defeats the documented v4 feature; both calls also drop negative_prompt. Pure forward of params that should obviously be forwarded.
TDD: force a cascade hop with driving_video_path set, assert the next-engine call receives it (mirror test_cascade_logic.py).

**C. LTX writes 0-byte file then reports success** — `ltx_native.py` native method, inside `with urlopen(...) as resp:` after `video_data = resp.read()`
Add `if not video_data: raise RuntimeError("LTX native returned empty 200 body")`. Routes through the EXISTING `except Exception` → FAL fallback / None (→ cascade), instead of a false success. Uses existing failure infra; no new path.
TDD: mock urlopen → empty body, assert NOT a false success (None / FAL path), no 0-byte file accepted (mirror existing ltx tests).

**EXCLUDED — these are YOUR design call, not "trivial":** [SHOT]-regex re-enable (workflow_selector.py:439 — changes shot-type *classification*), landscape-keyword reroute (:446 — changes *routing*), KLING duration hardcoded '5' (phase_c_ffmpeg.py:269 — need to confirm intent vs threading caller `duration`). I'll only touch these on an explicit brief from you.

**On GO:** TDD-green, each fix its own pathspec-scoped commit, I self-verify (scoped pytest once you confirm the tree is clean enough, or note deferral). If you'd rather own the edits and have me verify instead, say so. Awaiting your GO.

Cursor at send: 2026-06-13T09:16:14Z
